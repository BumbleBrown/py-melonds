#pragma once

/*
 * melonds_interface.h
 * -------------------
 * Public C ABI for py-melonds.
 *
 * This is the ONLY header Python/CFFI ever sees. It contains no C++,
 * no templates, no STL — just plain C types behind extern "C". That
 * means CFFI can parse it directly without a C++ preprocessor.
 *
 * Every function takes an opaque MelonDSHandle* as its first argument.
 * The handle owns the melonDS::NDS instance and all associated state.
 * Create one with melonds_create(), destroy it with melonds_destroy().
 * Handles are NOT thread-safe — drive them from a single Python thread.
 */

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Opaque instance handle                                              */
/* ------------------------------------------------------------------ */

typedef struct MelonDSHandle MelonDSHandle;

/* ------------------------------------------------------------------ */
/*  Lifecycle                                                           */
/* ------------------------------------------------------------------ */

/*
 * melonds_create
 * --------------
 * Allocate and initialise a new emulator instance.
 *
 * bios7_path   : Path to ARM7 BIOS (bios7.bin, 16 KB).
 *                Pass NULL to use the built-in FreeBIOS.
 * bios9_path   : Path to ARM9 BIOS (bios9.bin, 4 KB).
 *                Pass NULL to use the built-in FreeBIOS.
 * firmware_path: Path to DS firmware (firmware.bin, 256 KB).
 *                Pass NULL for the built-in firmware stub.
 *
 * Returns a valid handle on success, NULL on failure.
 * Call melonds_get_error() for a description when NULL is returned.
 */
MelonDSHandle* melonds_create(const char* bios7_path,
                               const char* bios9_path,
                               const char* firmware_path);

/*
 * melonds_destroy
 * ---------------
 * Release all resources owned by the handle.
 * The pointer is invalid after this call.
 */
void melonds_destroy(MelonDSHandle* handle);

/*
 * melonds_reset
 * -------------
 * Hard-reset the emulated DS (equivalent to power-cycling).
 * The loaded ROM stays loaded.
 */
void melonds_reset(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  ROM loading                                                         */
/* ------------------------------------------------------------------ */

/*
 * melonds_load_rom
 * ----------------
 * Load a .nds ROM image from disk.
 * Must be called before the first melonds_run_frame().
 *
 * Returns 1 on success, 0 on failure.
 */
int melonds_load_rom(MelonDSHandle* handle, const char* rom_path);

/* ------------------------------------------------------------------ */
/*  Frame execution — the hot path                                      */
/* ------------------------------------------------------------------ */

/*
 * melonds_run_frame
 * -----------------
 * Execute exactly one DS frame (≈560,190 ARM9 cycles).
 *
 * This call is SYNCHRONOUS: it returns only after the frame is
 * complete. Python owns the loop:
 *
 *   while True:
 *       lib.melonds_set_keys(h, keys)
 *       lib.melonds_run_frame(h)
 *       val = lib.melonds_mem_read_32(h, addr)
 *
 * There is no internal frame limiter — call it as fast as your CPU
 * allows for unthrottled emulation (the libmgba speed trick).
 */
void melonds_run_frame(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Input                                                               */
/* ------------------------------------------------------------------ */

/*
 * DS button bitmask (same layout as the hardware KEY register):
 *
 *   Bit 0  = A        Bit 6  = Up
 *   Bit 1  = B        Bit 7  = Down
 *   Bit 2  = Select   Bit 8  = Right     (note: right = bit 8 in keyinput)
 *   Bit 3  = Start    Bit 9  = Left
 *   Bit 4  = Right    Bit 10 = L
 *   Bit 5  = Left     Bit 11 = R
 *   Bit 6  = Up       Bit 12 = ... (use the constants below)
 *   Bit 7  = Down
 *
 * melonDS uses inverted logic internally (0 = pressed), but this API
 * uses normal logic (1 = pressed) and inverts before forwarding.
 */
#define MELONDS_KEY_A       (1 << 0)
#define MELONDS_KEY_B       (1 << 1)
#define MELONDS_KEY_SELECT  (1 << 2)
#define MELONDS_KEY_START   (1 << 3)
#define MELONDS_KEY_RIGHT   (1 << 4)
#define MELONDS_KEY_LEFT    (1 << 5)
#define MELONDS_KEY_UP      (1 << 6)
#define MELONDS_KEY_DOWN    (1 << 7)
#define MELONDS_KEY_R       (1 << 8)
#define MELONDS_KEY_L       (1 << 9)
#define MELONDS_KEY_X       (1 << 10)
#define MELONDS_KEY_Y       (1 << 11)

/*
 * melonds_set_keys
 * ----------------
 * Set the held button state for the NEXT frame.
 * Pass a bitmask of MELONDS_KEY_* values OR'd together.
 * Bits not set = released.
 */
void melonds_set_keys(MelonDSHandle* handle, uint32_t keys);

/*
 * melonds_set_touch
 * -----------------
 * Simulate a stylus press on the bottom (touch) screen.
 * x: 0–255,  y: 0–191  (DS native resolution)
 * Activates the touch flag automatically.
 */
void melonds_set_touch(MelonDSHandle* handle, int x, int y);

/*
 * melonds_release_touch
 * ---------------------
 * Lift the stylus.
 */
void melonds_release_touch(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Memory access                                                       */
/* ------------------------------------------------------------------ */

/*
 * All memory read/write functions address the ARM9 system bus.
 * The address space is 32-bit (0x00000000 – 0xFFFFFFFF).
 *
 * Useful regions for Pokémon NDS bots:
 *   0x02000000 – 0x023FFFFF  Main RAM  (4 MB) — all game data lives here
 *   0x03000000 – 0x03007FFF  Shared WRAM
 *   0x027E0000 – 0x027FFFFF  ARM7 WRAM
 *
 * Reads/writes to invalid regions return 0 / are silently ignored.
 * Use melonds_mem_read_bulk() for reading large structures at once.
 */

uint8_t  melonds_mem_read_8 (MelonDSHandle* handle, uint32_t addr);
uint16_t melonds_mem_read_16(MelonDSHandle* handle, uint32_t addr);
uint32_t melonds_mem_read_32(MelonDSHandle* handle, uint32_t addr);

void melonds_mem_write_8 (MelonDSHandle* handle, uint32_t addr, uint8_t  val);
void melonds_mem_write_16(MelonDSHandle* handle, uint32_t addr, uint16_t val);
void melonds_mem_write_32(MelonDSHandle* handle, uint32_t addr, uint32_t val);

/*
 * melonds_mem_read_bulk
 * ---------------------
 * Copy `length` bytes starting at `addr` into `out_buf`.
 * out_buf must be caller-allocated and at least `length` bytes.
 * Returns the number of bytes actually read (may be less if the
 * range crosses region boundaries).
 *
 * This is the fast path for reading Pokémon data structures
 * (220-byte pk5 / 236-byte pk4 blobs).
 */
size_t melonds_mem_read_bulk(MelonDSHandle* handle,
                              uint32_t addr,
                              uint8_t* out_buf,
                              size_t   length);

/* ------------------------------------------------------------------ */
/*  Save states                                                         */
/* ------------------------------------------------------------------ */

/*
 * melonds_savestate / melonds_loadstate
 * --------------------------------------
 * Write / read a full emulator snapshot to/from a file on disk.
 * Returns 1 on success, 0 on failure.
 */
int melonds_savestate(MelonDSHandle* handle, const char* path);
int melonds_loadstate(MelonDSHandle* handle, const char* path);

/*
 * melonds_savestate_mem / melonds_loadstate_mem
 * ----------------------------------------------
 * In-memory save states — no file I/O, much faster.
 * The caller owns the buffer. Free it with melonds_free_buf().
 *
 * melonds_savestate_mem: writes snapshot into a newly allocated buffer.
 *   *out_buf is set to the buffer pointer, *out_size to its length.
 *   Returns 1 on success.
 *
 * melonds_loadstate_mem: restores from a buffer previously produced
 *   by melonds_savestate_mem.
 *   Returns 1 on success.
 */
int melonds_savestate_mem(MelonDSHandle* handle,
                           uint8_t** out_buf,
                           size_t*   out_size);

int melonds_loadstate_mem(MelonDSHandle* handle,
                           const uint8_t* buf,
                           size_t         size);

/* Free a buffer returned by melonds_savestate_mem(). */
void melonds_free_buf(uint8_t* buf);

/* ------------------------------------------------------------------ */
/*  Renderer / speed control (mirrors libmgba's speed tricks)          */
/* ------------------------------------------------------------------ */

/*
 * melonds_set_video_enabled
 * -------------------------
 * Enable (1) or disable (0) the 2D/3D renderer.
 *
 * Disabling video activates a null/dummy renderer that skips all GPU
 * work — the single biggest speed win. Equivalent to how the Gen 3 bot
 * calls set_video_enabled(False) to reach unthrottled speeds.
 *
 * Screenshots are not possible while video is disabled.
 */
void melonds_set_video_enabled(MelonDSHandle* handle, int enabled);

/*
 * melonds_set_audio_enabled
 * -------------------------
 * Enable (1) or disable (0) audio emulation.
 * Disabling audio removes the SPU mixing overhead.
 */
void melonds_set_audio_enabled(MelonDSHandle* handle, int enabled);

/*
 * melonds_get_framebuffer
 * -----------------------
 * Returns a pointer to the combined top+bottom screen pixel data.
 * Format: RGBA8888, width=256, height=384 (top 192 rows + bottom 192).
 * The pointer is valid until the next call to melonds_run_frame().
 * Returns NULL if video is disabled.
 */
const uint32_t* melonds_get_framebuffer(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Diagnostics                                                         */
/* ------------------------------------------------------------------ */

/*
 * melonds_get_error
 * -----------------
 * Returns a human-readable description of the last error, or NULL if
 * no error has occurred. The string is owned by the handle — do not
 * free it.
 */
const char* melonds_get_error(MelonDSHandle* handle);

/*
 * melonds_get_frame_count
 * -----------------------
 * Returns the total number of frames executed since creation / reset.
 */
uint64_t melonds_get_frame_count(MelonDSHandle* handle);

#ifdef __cplusplus
}
#endif
