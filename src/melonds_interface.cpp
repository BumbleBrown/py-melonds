#include "melonds_interface.h"

#include "../melonDS/src/NDS.h"
#include "../melonDS/src/NDSCart.h"
#include "../melonDS/src/Args.h"
#include "../melonDS/src/GPU.h"
#include "../melonDS/src/SPU.h"
#include "../melonDS/src/Platform.h"
#include "../melonDS/src/Savestate.h"
#include "../melonDS/src/FreeBIOS.h"
#include "../melonDS/src/SPI_Firmware.h"
#include "../melonDS/src/GPU_Soft.h"

#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>

struct MelonDSHandle {
    std::unique_ptr<melonDS::NDS> nds;

    std::string bios7_path;
    std::string bios9_path;
    std::string firmware_path;

    uint32_t current_keys  = 0;
    bool     touch_active  = false;
    int      touch_x       = 0;
    int      touch_y       = 0;

    bool video_enabled = true;
    bool audio_enabled = false;

    uint32_t framebuffer[256 * 384] = {};
    uint64_t frame_count = 0;
    std::string last_error;

    void set_error(const char* msg) { last_error = msg ? msg : ""; }
    void clear_error()              { last_error.clear(); }
};

static melonDS::NDS* get_nds(MelonDSHandle* h) {
    return h ? h->nds.get() : nullptr;
}

static void apply_input(MelonDSHandle* h) {
    auto* nds = get_nds(h);
    if (!nds) return;
    uint32_t hw_keys = (~h->current_keys) & 0xFFF;
    if (h->current_keys != 0)
        fprintf(stderr, "apply_input: current=%u hw=%u\n", h->current_keys, hw_keys);
    nds->SetKeyMask(hw_keys);
    if (h->touch_active)
        nds->TouchScreen(h->touch_x, h->touch_y);
    else
        nds->ReleaseScreen();
}

static void copy_framebuffer(MelonDSHandle* h) {
    auto* nds = get_nds(h);
    if (!nds || !h->video_enabled) return;

    auto* soft = dynamic_cast<melonDS::SoftRenderer*>(&nds->GPU.GetRenderer());
    if (!soft) return;

    /* Try buffer 0 first, then buffer 1 */
    void* top = nullptr;
    void* bot = nullptr;
    
    soft->GetFramebuffersDirect(&top, &bot, 0);
    uint32_t* t = static_cast<uint32_t*>(top);
    bool has_data = false;
    for (int i = 0; i < 256 * 192; i++) {
        if (t[i]) { has_data = true; break; }
    }
    
    if (!has_data) {
        soft->GetFramebuffersDirect(&top, &bot, 1);
    }

    if (top) memcpy(h->framebuffer,             top, 256 * 192 * sizeof(uint32_t));
    if (bot) memcpy(h->framebuffer + 256 * 192, bot, 256 * 192 * sizeof(uint32_t));
}

static melonDS::NDSArgs build_nds_args(MelonDSHandle* h) {
    melonDS::NDSArgs args = {};

    /* Load BIOS files if provided, otherwise FreeBIOS is already default */
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

    /* Firmware — use default stub if not provided */
    if (!h->firmware_path.empty()) {
        FILE* f = fopen(h->firmware_path.c_str(), "rb");
        if (f) {
            fseek(f, 0, SEEK_END);
            long sz = ftell(f);
            fseek(f, 0, SEEK_SET);
            std::vector<uint8_t> buf(sz);
            fread(buf.data(), 1, sz, f);
            fclose(f);
            args.Firmware = melonDS::Firmware(buf.data(), sz);
        }
    } else {
        args.Firmware = melonDS::Firmware(0);
    }

    /* Software renderer — no OpenGL needed */

    return args;
}

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
        melonDS::NDSArgs args = build_nds_args(h);
        h->nds = std::make_unique<melonDS::NDS>(std::move(args));
    } catch (const std::exception& e) {
        h->set_error(e.what());
    }

    return h;
}

void melonds_destroy(MelonDSHandle* h) { delete h; }

void melonds_reset(MelonDSHandle* h) {
    auto* nds = get_nds(h);
    if (!nds) return;
    nds->Reset();
    h->frame_count = 0;
    h->clear_error();
}

int melonds_load_rom(MelonDSHandle* h, const char* rom_path) {
    if (!h || !rom_path) return 0;
    auto* nds = get_nds(h);
    if (!nds) { h->set_error("NDS not initialised"); return 0; }

    FILE* f = fopen(rom_path, "rb");
    if (!f) { h->set_error("Cannot open ROM"); return 0; }
    fseek(f, 0, SEEK_END);
    long rom_size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (rom_size <= 0) { fclose(f); h->set_error("ROM size invalid"); return 0; }

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
    h->frame_count = 0;
    h->clear_error();
    return 1;
}

void melonds_run_frame(MelonDSHandle* h) {
    auto* nds = get_nds(h);
    if (!nds) return;
    apply_input(h);
    nds->RunFrame();
    h->frame_count++;
    if (h->video_enabled) copy_framebuffer(h);
}

void melonds_set_keys(MelonDSHandle* h, uint32_t keys) {
    if (h) h->current_keys = keys;
}

void melonds_set_touch(MelonDSHandle* h, int x, int y) {
    if (!h) return;
    h->touch_active = true;
    h->touch_x = x;
    h->touch_y = y;
}

void melonds_release_touch(MelonDSHandle* h) {
    if (!h) return;
    h->touch_active = false;
}

uint8_t melonds_mem_read_8(MelonDSHandle* h, uint32_t addr) {
    auto* nds = get_nds(h);
    return nds ? nds->ARM9Read8(addr) : 0;
}

uint16_t melonds_mem_read_16(MelonDSHandle* h, uint32_t addr) {
    auto* nds = get_nds(h);
    return nds ? nds->ARM9Read16(addr) : 0;
}

uint32_t melonds_mem_read_32(MelonDSHandle* h, uint32_t addr) {
    auto* nds = get_nds(h);
    return nds ? nds->ARM9Read32(addr) : 0;
}

void melonds_mem_write_8(MelonDSHandle* h, uint32_t addr, uint8_t val) {
    auto* nds = get_nds(h);
    if (nds) nds->ARM9Write8(addr, val);
}

void melonds_mem_write_16(MelonDSHandle* h, uint32_t addr, uint16_t val) {
    auto* nds = get_nds(h);
    if (nds) nds->ARM9Write16(addr, val);
}

void melonds_mem_write_32(MelonDSHandle* h, uint32_t addr, uint32_t val) {
    auto* nds = get_nds(h);
    if (nds) nds->ARM9Write32(addr, val);
}

size_t melonds_mem_read_bulk(MelonDSHandle* h, uint32_t addr,
                              uint8_t* out_buf, size_t length) {
    if (!out_buf || length == 0) return 0;
    auto* nds = get_nds(h);
    if (!nds) return 0;
    if (addr >= 0x02000000 && addr + length <= 0x02400000) {
        memcpy(out_buf, nds->MainRAM + (addr - 0x02000000), length);
        return length;
    }
    for (size_t i = 0; i < length; i++)
        out_buf[i] = nds->ARM9Read8(addr + (uint32_t)i);
    return length;
}

int melonds_savestate(MelonDSHandle* h, const char* path) {
    auto* nds = get_nds(h);
    if (!nds || !path) return 0;
    melonDS::Savestate ss;
    nds->DoSavestate(&ss);
    ss.Finish();
    FILE* f = fopen(path, "wb");
    if (!f) { h->set_error("Cannot open savestate for write"); return 0; }
    fwrite(ss.Buffer(), 1, ss.BufferLength(), f);
    fclose(f);
    return 1;
}

int melonds_loadstate(MelonDSHandle* h, const char* path) {
    auto* nds = get_nds(h);
    if (!nds || !path) return 0;
    FILE* f = fopen(path, "rb");
    if (!f) { h->set_error("Cannot open savestate for read"); return 0; }
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

int melonds_savestate_mem(MelonDSHandle* h, uint8_t** out_buf, size_t* out_size) {
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

int melonds_loadstate_mem(MelonDSHandle* h, const uint8_t* buf, size_t size) {
    auto* nds = get_nds(h);
    if (!nds || !buf || size == 0) return 0;
    melonDS::Savestate ss(const_cast<uint8_t*>(buf), (uint32_t)size, false);
    nds->DoSavestate(&ss);
    return 1;
}

void melonds_free_buf(uint8_t* buf) { free(buf); }

void melonds_set_video_enabled(MelonDSHandle* h, int enabled) {
    if (!h) return;
    h->video_enabled = (enabled != 0);
}

void melonds_set_audio_enabled(MelonDSHandle* h, int enabled) {
    if (h) h->audio_enabled = (enabled != 0);
}

const uint32_t* melonds_get_framebuffer(MelonDSHandle* h) {
    if (!h || !h->video_enabled) return nullptr;
    return h->framebuffer;
}

const char* melonds_get_error(MelonDSHandle* h) {
    if (!h || h->last_error.empty()) return nullptr;
    return h->last_error.c_str();
}

uint64_t melonds_get_frame_count(MelonDSHandle* h) {
    return h ? h->frame_count : 0;
}

} /* extern "C" */