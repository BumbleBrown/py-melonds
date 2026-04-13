/*
 * melonds_interface.cpp
 * ---------------------
 * C++ implementation of the C API declared in melonds_interface.h.
 *
 * This file is the only place that touches melonDS internals directly.
 * Everything above this layer speaks plain C and knows nothing about
 * C++ classes or the melonDS namespace.
 */

#include "melonds_interface.h"

#include "../melonDS/src/NDS.h"
#include "../melonDS/src/NDSCart.h"
#include "../melonDS/src/Args.h"
#include "../melonDS/src/GPU.h"
#include "../melonDS/src/GPU_Soft.h"
#include "../melonDS/src/SPU.h"
#include "../melonDS/src/Platform.h"
#include "../melonDS/src/Savestate.h"
#include "../melonDS/src/FreeBIOS.h"
#include "../melonDS/src/SPI_Firmware.h"
#include "../melonDS/src/RTC.h"

#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <ctime>
#include <memory>
#include <string>
#include <vector>

/* ------------------------------------------------------------------ */
/*  Internal handle struct                                              */
/* ------------------------------------------------------------------ */

struct MelonDSHandle {
    std::unique_ptr<melonDS::NDS> nds;

    std::string bios7_path;
    std::string bios9_path;
    std::string firmware_path;
    std::string rom_path;       // stored so Reset() can call SetupDirectBoot()

    uint32_t current_keys = 0;
    bool     touch_active = false;
    int      touch_x      = 0;
    int      touch_y      = 0;

    bool video_enabled = true;
    bool audio_enabled = false;

    uint32_t framebuffer[256 * 384] = {};

    static constexpr uint32_t AUDIO_BUF_PAIRS = 65536;
    int16_t  audio_buf[AUDIO_BUF_PAIRS * 2]   = {};
    uint32_t audio_write_pos = 0;
    uint32_t audio_read_pos  = 0;

    uint64_t    frame_count = 0;
    std::string last_error;

    void set_error(const char* msg) { last_error = msg ? msg : ""; }
    void clear_error()              { last_error.clear(); }
};

/* ------------------------------------------------------------------ */
/*  Internal helpers                                                    */
/* ------------------------------------------------------------------ */

static melonDS::NDS* get_nds(MelonDSHandle* h)
{
    return h ? h->nds.get() : nullptr;
}

static void apply_input(MelonDSHandle* h)
{
    auto* nds = get_nds(h);
    if (!nds) return;
    uint32_t hw_keys = (~h->current_keys) & 0xFFF;
    nds->SetKeyMask(hw_keys);
    if (h->touch_active)
        nds->TouchScreen(h->touch_x, h->touch_y);
    else
        nds->ReleaseScreen();
}

static void copy_framebuffer(MelonDSHandle* h)
{
    auto* nds = get_nds(h);
    if (!nds || !h->video_enabled) return;

    auto* soft = dynamic_cast<melonDS::SoftRenderer*>(&nds->GPU.GetRenderer());
    if (!soft) return;

    void* top = nullptr;
    void* bot = nullptr;

    soft->GetFramebuffers(&top, &bot);

    if (top) memcpy(h->framebuffer,             top, 256 * 192 * sizeof(uint32_t));
    if (bot) memcpy(h->framebuffer + 256 * 192, bot, 256 * 192 * sizeof(uint32_t));
}

static void drain_audio(MelonDSHandle* h)
{
    auto* nds = get_nds(h);
    if (!nds || !h->audio_enabled) return;

    constexpr uint32_t CHUNK = 1024;
    int16_t tmp[CHUNK * 2];

    for (;;) {
        uint32_t got = nds->SPU.ReadOutput(tmp, CHUNK);
        if (got == 0) break;

        uint32_t mask       = MelonDSHandle::AUDIO_BUF_PAIRS - 1;
        uint32_t used       = (h->audio_write_pos - h->audio_read_pos) & mask;
        uint32_t free_pairs = (MelonDSHandle::AUDIO_BUF_PAIRS - 1) - used;
        uint32_t to_copy    = (got < free_pairs) ? got : free_pairs;

        for (uint32_t i = 0; i < to_copy; i++) {
            uint32_t idx = (h->audio_write_pos + i) & mask;
            h->audio_buf[idx * 2]     = tmp[i * 2];
            h->audio_buf[idx * 2 + 1] = tmp[i * 2 + 1];
        }
        h->audio_write_pos = (h->audio_write_pos + to_copy) & mask;
    }
}

static melonDS::NDSArgs build_args(MelonDSHandle* h)
{
    melonDS::NDSArgs args = {};

    if (!h->bios7_path.empty()) {
        FILE* f = fopen(h->bios7_path.c_str(), "rb");
        if (f) {
            auto bios = std::make_unique<melonDS::ARM7BIOSImage>();
            fread(bios->data(), 1, bios->size(), f);
            fclose(f);
            args.ARM7BIOS = std::move(bios);
        }
    }

    if (!h->bios9_path.empty()) {
        FILE* f = fopen(h->bios9_path.c_str(), "rb");
        if (f) {
            auto bios = std::make_unique<melonDS::ARM9BIOSImage>();
            fread(bios->data(), 1, bios->size(), f);
            fclose(f);
            args.ARM9BIOS = std::move(bios);
        }
    }

    if (!h->firmware_path.empty()) {
        FILE* f = fopen(h->firmware_path.c_str(), "rb");
        if (f) {
            fseek(f, 0, SEEK_END);
            long sz = ftell(f);
            fseek(f, 0, SEEK_SET);
            std::vector<uint8_t> buf(sz);
            fread(buf.data(), 1, sz, f);
            fclose(f);
            args.Firmware = melonDS::Firmware(buf.data(), (uint32_t)sz);
        }
    } else {
        args.Firmware = melonDS::Firmware(0);
    }

    return args;
}

/* ------------------------------------------------------------------ */
/*  C API implementation                                                */
/* ------------------------------------------------------------------ */

extern "C" {

MelonDSHandle* melonds_create(const char* bios7_path,
                               const char* bios9_path,
                               const char* firmware_path)
{
    auto* h = new (std::nothrow) MelonDSHandle;
    if (!h) return nullptr;

    if (bios7_path)    h->bios7_path    = bios7_path;
    if (bios9_path)    h->bios9_path    = bios9_path;
    if (firmware_path) h->firmware_path = firmware_path;

    try {
        melonDS::NDSArgs args = build_args(h);
        h->nds = std::make_unique<melonDS::NDS>(std::move(args));
    } catch (const std::exception& e) {
        h->set_error(e.what());
    }

    return h;
}

void melonds_destroy(MelonDSHandle* h)
{
    delete h;
}

void melonds_reset(MelonDSHandle* h)
{
    auto* nds = get_nds(h);
    if (!nds) return;
    nds->Reset();
    /*
     * Fix: call SetupDirectBoot() and Start() after Reset() so the ROM
     * actually boots. melonds_load_rom() calls all three; the original
     * melonds_reset() only called Reset() which left the CPU unstarted
     * and the direct-boot vector unset -- resulting in a black screen.
     */
    if (!h->rom_path.empty())
    {
        nds->SetupDirectBoot(h->rom_path);
        nds->Start();
    }
    h->frame_count     = 0;
    h->audio_write_pos = 0;
    h->audio_read_pos  = 0;
    h->clear_error();
}

int melonds_load_rom(MelonDSHandle* h, const char* rom_path)
{
    if (!h || !rom_path) return 0;
    auto* nds = get_nds(h);
    if (!nds) { h->set_error("NDS not initialised"); return 0; }

    FILE* f = fopen(rom_path, "rb");
    if (!f) { h->set_error("Cannot open ROM file"); return 0; }

    fseek(f, 0, SEEK_END);
    long rom_size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (rom_size <= 0) { fclose(f); h->set_error("ROM file is empty"); return 0; }

    std::vector<uint8_t> rom_data(rom_size);
    fread(rom_data.data(), 1, rom_size, f);
    fclose(f);

    auto cart = melonDS::NDSCart::ParseROM(
        rom_data.data(), (uint32_t)rom_size, nullptr, {});
    if (!cart) { h->set_error("Failed to parse ROM"); return 0; }

    nds->SetNDSCart(std::move(cart));
    nds->Reset();
    nds->SetupDirectBoot(rom_path);
    nds->Start();
    h->rom_path        = rom_path;   // store so Reset() can call SetupDirectBoot()
    h->frame_count     = 0;
    h->audio_write_pos = 0;
    h->audio_read_pos  = 0;
    h->clear_error();
    return 1;
}

void melonds_run_frame(MelonDSHandle* h)
{
    auto* nds = get_nds(h);
    if (!nds) return;
    apply_input(h);
    nds->RunFrame();
    h->frame_count++;
    drain_audio(h);
    if (h->video_enabled) copy_framebuffer(h);
}

void melonds_set_keys(MelonDSHandle* h, uint32_t keys)
{
    if (h) h->current_keys = keys;
}

void melonds_set_touch(MelonDSHandle* h, int x, int y)
{
    if (!h) return;
    h->touch_active = true;
    h->touch_x = x;
    h->touch_y = y;
}

void melonds_release_touch(MelonDSHandle* h)
{
    if (h) h->touch_active = false;
}

/* ------------------------------------------------------------------ */
/*  Memory                                                              */
/* ------------------------------------------------------------------ */

uint8_t melonds_mem_read_8(MelonDSHandle* h, uint32_t addr)
{
    auto* nds = get_nds(h);
    return nds ? nds->ARM9Read8(addr) : 0;
}

uint16_t melonds_mem_read_16(MelonDSHandle* h, uint32_t addr)
{
    auto* nds = get_nds(h);
    return nds ? nds->ARM9Read16(addr) : 0;
}

uint32_t melonds_mem_read_32(MelonDSHandle* h, uint32_t addr)
{
    auto* nds = get_nds(h);
    return nds ? nds->ARM9Read32(addr) : 0;
}

void melonds_mem_write_8(MelonDSHandle* h, uint32_t addr, uint8_t val)
{
    auto* nds = get_nds(h);
    if (nds) nds->ARM9Write8(addr, val);
}

void melonds_mem_write_16(MelonDSHandle* h, uint32_t addr, uint16_t val)
{
    auto* nds = get_nds(h);
    if (nds) nds->ARM9Write16(addr, val);
}

void melonds_mem_write_32(MelonDSHandle* h, uint32_t addr, uint32_t val)
{
    auto* nds = get_nds(h);
    if (nds) nds->ARM9Write32(addr, val);
}

size_t melonds_mem_read_bulk(MelonDSHandle* h, uint32_t addr,
                              uint8_t* out_buf, size_t length)
{
    if (!out_buf || length == 0) return 0;
    auto* nds = get_nds(h);
    if (!nds) return 0;

    if (addr >= 0x02000000 && (addr + length) <= 0x02400000) {
        memcpy(out_buf, nds->MainRAM + (addr - 0x02000000), length);
        return length;
    }

    for (size_t i = 0; i < length; i++)
        out_buf[i] = nds->ARM9Read8(addr + (uint32_t)i);
    return length;
}

size_t melonds_mem_write_bulk(MelonDSHandle* h, uint32_t addr,
                               const uint8_t* buf, size_t length)
{
    if (!buf || length == 0) return 0;
    auto* nds = get_nds(h);
    if (!nds) return 0;

    if (addr >= 0x02000000 && (addr + length) <= 0x02400000) {
        memcpy(nds->MainRAM + (addr - 0x02000000), buf, length);
        return length;
    }

    for (size_t i = 0; i < length; i++)
        nds->ARM9Write8(addr + (uint32_t)i, buf[i]);
    return length;
}

/* ------------------------------------------------------------------ */
/*  SRAM                                                                */
/* ------------------------------------------------------------------ */

static melonDS::NDSCart::CartCommon* get_cart(MelonDSHandle* h)
{
    auto* nds = get_nds(h);
    if (!nds) return nullptr;
    return nds->NDSCartSlot.GetCart();
}

size_t melonds_sram_size(MelonDSHandle* h)
{
    auto* cart = get_cart(h);
    if (!cart) return 0;
    return cart->GetSaveMemoryLength();
}

size_t melonds_sram_read(MelonDSHandle* h, uint8_t* out_buf, size_t buf_size)
{
    auto* cart = get_cart(h);
    if (!cart || !out_buf) return 0;
    size_t sz = cart->GetSaveMemoryLength();
    if (sz == 0 || buf_size < sz) return 0;
    const uint8_t* src = cart->GetSaveMemory();
    if (!src) return 0;
    memcpy(out_buf, src, sz);
    return sz;
}

int melonds_sram_write(MelonDSHandle* h, const uint8_t* buf, size_t size)
{
    auto* cart = get_cart(h);
    if (!cart || !buf) return 0;
    if (cart->GetSaveMemoryLength() != size) return 0;
    cart->SetSaveMemory(buf, (uint32_t)size);
    return 1;
}

int melonds_sram_load_file(MelonDSHandle* h, const char* path)
{
    if (!h || !path) return 0;
    auto* cart = get_cart(h);
    if (!cart) { h->set_error("No cart loaded"); return 0; }

    FILE* f = fopen(path, "rb");
    if (!f) { h->set_error("Cannot open save file"); return 0; }

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz <= 0) { fclose(f); h->set_error("Save file is empty"); return 0; }

    std::vector<uint8_t> buf(sz);
    fread(buf.data(), 1, sz, f);
    fclose(f);

    if (cart->GetSaveMemoryLength() != (size_t)sz) {
        h->set_error("Save file size does not match cart save memory size");
        return 0;
    }

    cart->SetSaveMemory(buf.data(), (uint32_t)sz);
    h->clear_error();
    return 1;
}

int melonds_sram_save_file(MelonDSHandle* h, const char* path)
{
    if (!h || !path) return 0;
    auto* cart = get_cart(h);
    if (!cart) { h->set_error("No cart loaded"); return 0; }

    size_t sz = cart->GetSaveMemoryLength();
    if (sz == 0) { h->set_error("Cart has no save memory"); return 0; }

    const uint8_t* src = cart->GetSaveMemory();
    if (!src) { h->set_error("Save memory pointer is null"); return 0; }

    FILE* f = fopen(path, "wb");
    if (!f) { h->set_error("Cannot open output file for writing"); return 0; }

    fwrite(src, 1, sz, f);
    fclose(f);
    h->clear_error();
    return 1;
}

/* ------------------------------------------------------------------ */
/*  RTC                                                                 */
/* ------------------------------------------------------------------ */

/* Convert integer to BCD. e.g. 23 -> 0x23 */
static uint8_t to_bcd(int val)
{
    return (uint8_t)(((val / 10) << 4) | (val % 10));
}

void melonds_rtc_set_time(MelonDSHandle* h,
                           int year, int month,  int day,
                           int hour, int minute, int second)
{
    auto* nds = get_nds(h);
    if (!nds) return;

    /*
     * melonDS RTC::StateData uses a DateTime[7] array of BCD bytes.
     * Layout confirmed from RTC.cpp::GetDateTime():
     *   [0] year offset from 2000, [1] month, [2] day, [3] day-of-week,
     *   [4] hour (24h), [5] minute, [6] second
     */
    struct tm t = {};
    t.tm_year = year - 1900;
    t.tm_mon  = month - 1;
    t.tm_mday = day;
    mktime(&t);

    melonDS::RTC::StateData state = {};
    state.DateTime[0] = to_bcd(year - 2000);
    state.DateTime[1] = to_bcd(month);
    state.DateTime[2] = to_bcd(day);
    state.DateTime[3] = to_bcd(t.tm_wday);
    state.DateTime[4] = to_bcd(hour);
    state.DateTime[5] = to_bcd(minute);
    state.DateTime[6] = to_bcd(second);

    nds->RTC.SetState(state);
}

void melonds_rtc_sync_to_host(MelonDSHandle* h)
{
    if (!h) return;
    time_t now = time(nullptr);
    struct tm* t = localtime(&now);
    if (!t) return;
    melonds_rtc_set_time(h,
        t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
        t->tm_hour, t->tm_min, t->tm_sec);
}

/* ------------------------------------------------------------------ */
/*  Save states                                                         */
/* ------------------------------------------------------------------ */

int melonds_savestate(MelonDSHandle* h, const char* path)
{
    auto* nds = get_nds(h);
    if (!nds || !path) return 0;

    melonDS::Savestate ss;
    nds->DoSavestate(&ss);
    ss.Finish();

    FILE* f = fopen(path, "wb");
    if (!f) { h->set_error("Cannot open save state file for writing"); return 0; }
    fwrite(ss.Buffer(), 1, ss.BufferLength(), f);
    fclose(f);
    return 1;
}

int melonds_loadstate(MelonDSHandle* h, const char* path)
{
    auto* nds = get_nds(h);
    if (!nds || !path) return 0;

    FILE* f = fopen(path, "rb");
    if (!f) { h->set_error("Cannot open save state file for reading"); return 0; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<uint8_t> buf(sz);
    fread(buf.data(), 1, sz, f);
    fclose(f);

    melonDS::Savestate ss(buf.data(), (uint32_t)sz, false);
    nds->DoSavestate(&ss);
    return 1;
}

int melonds_savestate_mem(MelonDSHandle* h, uint8_t** out_buf, size_t* out_size)
{
    auto* nds = get_nds(h);
    if (!nds || !out_buf || !out_size) return 0;

    melonDS::Savestate ss;
    nds->DoSavestate(&ss);
    ss.Finish();

    size_t sz = ss.BufferLength();
    uint8_t* buf = (uint8_t*)malloc(sz);
    if (!buf) { h->set_error("Out of memory"); return 0; }
    memcpy(buf, ss.Buffer(), sz);
    *out_buf  = buf;
    *out_size = sz;
    return 1;
}

int melonds_loadstate_mem(MelonDSHandle* h, const uint8_t* buf, size_t size)
{
    auto* nds = get_nds(h);
    if (!nds || !buf || size == 0) return 0;
    melonDS::Savestate ss(const_cast<uint8_t*>(buf), (uint32_t)size, false);
    nds->DoSavestate(&ss);
    return 1;
}

void melonds_free_buf(uint8_t* buf)
{
    free(buf);
}

/* ------------------------------------------------------------------ */
/*  Video                                                               */
/* ------------------------------------------------------------------ */

void melonds_set_video_enabled(MelonDSHandle* h, int enabled)
{
    if (h) h->video_enabled = (enabled != 0);
}

void melonds_set_audio_enabled(MelonDSHandle* h, int enabled)
{
    if (h) h->audio_enabled = (enabled != 0);
}

const uint32_t* melonds_get_framebuffer(MelonDSHandle* h)
{
    if (!h || !h->video_enabled) return nullptr;
    return h->framebuffer;
}

int melonds_get_framebuffer_rgb(MelonDSHandle* h, uint8_t* out_buf)
{
    if (!h || !h->video_enabled || !out_buf) return 0;

    const uint32_t* src = h->framebuffer;
    uint8_t* dst = out_buf;
    for (int i = 0; i < 256 * 384; i++) {
        uint32_t px = src[i];
        dst[0] = (uint8_t)((px >>  0) & 0xFF);
        dst[1] = (uint8_t)((px >>  8) & 0xFF);
        dst[2] = (uint8_t)((px >> 16) & 0xFF);
        dst += 3;
    }
    return 1;
}

/* ------------------------------------------------------------------ */
/*  Audio                                                               */
/* ------------------------------------------------------------------ */

uint32_t melonds_audio_available(MelonDSHandle* h)
{
    if (!h || !h->audio_enabled) return 0;
    uint32_t mask = MelonDSHandle::AUDIO_BUF_PAIRS - 1;
    return (h->audio_write_pos - h->audio_read_pos) & mask;
}

uint32_t melonds_audio_read(MelonDSHandle* h, int16_t* out_buf, uint32_t count)
{
    if (!h || !out_buf || count == 0) return 0;

    uint32_t available = melonds_audio_available(h);
    uint32_t to_read   = (count < available) ? count : available;
    uint32_t mask      = MelonDSHandle::AUDIO_BUF_PAIRS - 1;

    for (uint32_t i = 0; i < to_read; i++) {
        uint32_t idx = (h->audio_read_pos + i) & mask;
        out_buf[i * 2]     = h->audio_buf[idx * 2];
        out_buf[i * 2 + 1] = h->audio_buf[idx * 2 + 1];
    }
    h->audio_read_pos = (h->audio_read_pos + to_read) & mask;
    return to_read;
}

uint32_t melonds_audio_sample_rate(MelonDSHandle* h)
{
    (void)h;
    return 32768;
}

/* ------------------------------------------------------------------ */
/*  Diagnostics                                                         */
/* ------------------------------------------------------------------ */

const char* melonds_get_error(MelonDSHandle* h)
{
    if (!h || h->last_error.empty()) return nullptr;
    return h->last_error.c_str();
}

uint64_t melonds_get_frame_count(MelonDSHandle* h)
{
    return h ? h->frame_count : 0;
}

} /* extern "C" */
