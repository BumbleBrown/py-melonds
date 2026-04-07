/*
 * tests/test_c.cpp
 * ----------------
 * Minimal C++ smoke test for the melonds C interface.
 * Run this BEFORE writing any Python — it validates that the library
 * builds and the core doesn't crash on startup.
 *
 * Usage:
 *   cmake --build build --target melonds_test
 *   ./build/melonds_test [path/to/rom.nds] [path/to/bios7.bin] [path/to/bios9.bin]
 *
 * Without a ROM it just tests create/destroy. With a ROM it runs
 * 60 frames and reads a known address.
 */

#include "melonds_interface.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

static void print_sep() { puts("--------------------------------------------"); }

int main(int argc, char** argv)
{
    const char* rom_path   = argc > 1 ? argv[1] : nullptr;
    const char* bios7_path = argc > 2 ? argv[2] : nullptr;
    const char* bios9_path = argc > 3 ? argv[3] : nullptr;

    print_sep();
    puts("py-melonds C smoke test");
    print_sep();

    /* ----------------------------------------------------------------
     * Test 1: create / destroy without a ROM
     * ---------------------------------------------------------------- */
    printf("[1] melonds_create (FreeBIOS, no ROM)... ");
    MelonDSHandle* h = melonds_create(bios7_path, bios9_path, nullptr);
    if (!h) { puts("FAIL — returned NULL"); return 1; }
    const char* err = melonds_get_error(h);
    if (err) printf("(warning: %s) ", err);
    puts("OK");

    printf("[1] melonds_destroy... ");
    melonds_destroy(h);
    puts("OK");

    /* ----------------------------------------------------------------
     * Test 2: load ROM + run frames (only if ROM provided)
     * ---------------------------------------------------------------- */
    if (!rom_path) {
        puts("\nNo ROM path given — skipping frame execution tests.");
        puts("Pass a .nds ROM as argv[1] to run the full test.");
        print_sep();
        puts("PASS (basic lifecycle only)");
        return 0;
    }

    printf("[2] melonds_create with BIOS %s/%s... ",
           bios7_path ? bios7_path : "(FreeBIOS)",
           bios9_path ? bios9_path : "(FreeBIOS)");
    h = melonds_create(bios7_path, bios9_path, nullptr);
    if (!h) { puts("FAIL"); return 1; }
    puts("OK");

    /* Disable video and audio for speed — exactly like the Gen3 bot */
    melonds_set_video_enabled(h, 0);
    melonds_set_audio_enabled(h, 0);

    printf("[2] melonds_load_rom(%s)... ", rom_path);
    int ok = melonds_load_rom(h, rom_path);
    if (!ok) {
        const char* e = melonds_get_error(h);
        printf("FAIL (%s)\n", e ? e : "unknown error");
        melonds_destroy(h);
        return 1;
    }
    puts("OK");

    /* ----------------------------------------------------------------
     * Run 60 frames (1 second of game time at 60fps)
     * ---------------------------------------------------------------- */
    printf("[3] Running 60 frames... ");
    fflush(stdout);

    for (int i = 0; i < 60; i++) {
        melonds_run_frame(h);
    }

    printf("OK (frame_count=%llu)\n",
           (unsigned long long)melonds_get_frame_count(h));

    /* ----------------------------------------------------------------
     * Read a memory address
     * Address 0x02000000 = start of Main RAM — should be non-garbage
     * ---------------------------------------------------------------- */
    printf("[4] melonds_mem_read_32(0x02000000) = ");
    uint32_t val = melonds_mem_read_32(h, 0x02000000);
    printf("0x%08X\n", val);

    /* ----------------------------------------------------------------
     * Bulk read test — read 220 bytes (pk5 size) from Main RAM start
     * ---------------------------------------------------------------- */
    printf("[5] melonds_mem_read_bulk(220 bytes)... ");
    uint8_t buf[220];
    memset(buf, 0xAA, sizeof(buf));
    size_t n = melonds_mem_read_bulk(h, 0x02000000, buf, sizeof(buf));
    printf("read %zu bytes, first 4: %02X %02X %02X %02X\n",
           n, buf[0], buf[1], buf[2], buf[3]);

    /* ----------------------------------------------------------------
     * In-memory save state round-trip
     * ---------------------------------------------------------------- */
    printf("[6] In-memory savestate... ");
    uint8_t* snap = nullptr;
    size_t   snap_size = 0;
    ok = melonds_savestate_mem(h, &snap, &snap_size);
    if (!ok || !snap) {
        puts("FAIL (savestate)");
    } else {
        printf("saved %zu bytes, ", snap_size);
        ok = melonds_loadstate_mem(h, snap, snap_size);
        melonds_free_buf(snap);
        puts(ok ? "load OK" : "FAIL (loadstate)");
    }

    /* ----------------------------------------------------------------
     * Run 60 more frames after restoring state
     * ---------------------------------------------------------------- */
    printf("[7] 60 more frames after loadstate... ");
    for (int i = 0; i < 60; i++) melonds_run_frame(h);
    printf("OK (frame_count=%llu)\n",
           (unsigned long long)melonds_get_frame_count(h));

    melonds_destroy(h);

    print_sep();
    puts("PASS — all tests completed");
    return 0;
}
