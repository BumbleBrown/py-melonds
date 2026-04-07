#pragma once

/*
 * melonds_interface.h
 * -------------------
 * Public C API for py-melonds.
 *
 * This is the only header that Python/CFFI ever sees. It uses plain C
 * types throughout so CFFI can parse it directly without a C++
 * preprocessor. No C++ syntax, no templates, no STL.
 *
 * All functions take an opaque MelonDSHandle pointer as their first
 * argument. The handle owns the melonDS NDS instance and all related
 * state. Create one with melonds_create() and destroy it with
 * melonds_destroy() when you are done.
 *
 * Handles are NOT thread-safe. Drive them from a single Python thread.
 *
 * Quick start:
 *
 *   MelonDSHandle* h = melonds_create(NULL, NULL, NULL);
 *   melonds_load_rom(h, "game.nds");
 *   melonds_set_video_enabled(h, 0);
 *   while (1) {
 *       melonds_set_keys(h, keys);
 *       melonds_run_frame(h);
 *       uint32_t val = melonds_mem_read_32(h, 0x02000000);
 *   }
 *   melonds_destroy(h);
 */

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Opaque handle                                                       */
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
 * bios7_path    Path to the ARM7 BIOS image (bios7.bin, 16 KB).
 *               Pass NULL to use the built-in open-source FreeBIOS.
 * bios9_path    Path to the ARM9 BIOS image (bios9.bin, 4 KB).
 *               Pass NULL to use the built-in FreeBIOS.
 * firmware_path Path to the DS firmware image (firmware.bin, 256 KB).
 *               Pass NULL to use a minimal built-in stub.
 *
 * Returns a valid handle on success, NULL on failure.
 * Call melonds_get_error() immediately after a NULL return for details.
 */
MelonDSHandle* melonds_create(const char* bios7_path,
                               const char* bios9_path,
                               const char* firmware_path);

/*
 * melonds_destroy
 * ---------------
 * Release all resources owned by the handle.
 * The pointer must not be used after this call.
 */
void melonds_destroy(MelonDSHandle* handle);

/*
 * melonds_reset
 * -------------
 * Hard-reset the emulated DS, as if the power button was cycled.
 * The loaded ROM stays loaded and the frame counter resets to zero.
 */
void melonds_reset(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  ROM loading                                                         */
/* ------------------------------------------------------------------ */

/*
 * melonds_load_rom
 * ----------------
 * Load a .nds ROM image from disk.
 * This must be called before the first melonds_run_frame().
 * Calling it again replaces the current cart and performs a reset.
 *
 * Returns 1 on success, 0 on failure.
 */
int melonds_load_rom(MelonDSHandle* handle, const char* rom_path);

/* ------------------------------------------------------------------ */
/*  Frame execution                                                     */
/* ------------------------------------------------------------------ */

/*
 * melonds_run_frame
 * -----------------
 * Execute exactly one DS frame (approximately 560,190 ARM9 cycles at
 * the DS clock rate of 33.51 MHz).
 *
 * This call is synchronous and returns only after the frame completes.
 * There is no internal frame limiter or sleep. The caller controls
 * timing. For maximum speed, call this in a tight loop:
 *
 *   while (running) {
 *       melonds_set_keys(h, keys);
 *       melonds_run_frame(h);
 *       process_memory(h);
 *   }
 *
 * After each call, audio samples are available via melonds_audio_read()
 * if audio is enabled.
 */
void melonds_run_frame(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Button input                                                        */
/* ------------------------------------------------------------------ */

/*
 * DS button bitmask values. OR these together to press multiple buttons
 * at the same time.
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
 * Set which buttons are held for the next call to melonds_run_frame().
 * Pass a bitmask of MELONDS_KEY_* values OR'd together.
 * Any button not included in the mask is treated as released.
 */
void melonds_set_keys(MelonDSHandle* handle, uint32_t keys);

/*
 * melonds_set_touch / melonds_release_touch
 * -----------------------------------------
 * Simulate the stylus on the bottom (touch) screen.
 * x: 0-255, y: 0-191 (DS native resolution).
 * The touch flag is set automatically by melonds_set_touch().
 */
void melonds_set_touch(MelonDSHandle* handle, int x, int y);
void melonds_release_touch(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Memory access                                                       */
/* ------------------------------------------------------------------ */

/*
 * All read/write functions address the ARM9 system bus.
 * Reads from unmapped or invalid regions return 0.
 * Writes to unmapped regions are silently ignored.
 *
 * DS memory map (most useful regions):
 *   0x02000000 - 0x023FFFFF   Main RAM (4 MB)
 *   0x03000000 - 0x03007FFF   Shared WRAM
 *   0x04000000 - 0x04FFFFFF   I/O registers
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
 * Copy length bytes starting at addr into out_buf.
 * out_buf must be caller-allocated and at least length bytes large.
 * Uses a fast memcpy path for Main RAM (0x02000000-0x023FFFFF).
 * Returns the number of bytes actually read.
 */
size_t melonds_mem_read_bulk(MelonDSHandle* handle,
                              uint32_t       addr,
                              uint8_t*       out_buf,
                              size_t         length);

/*
 * melonds_mem_write_bulk
 * ----------------------
 * Write length bytes from buf into memory starting at addr.
 * Uses a fast memcpy path for Main RAM, falls back to per-byte writes
 * elsewhere.
 * Returns the number of bytes actually written.
 */
size_t melonds_mem_write_bulk(MelonDSHandle* handle,
                               uint32_t       addr,
                               const uint8_t* buf,
                               size_t         length);

/* ------------------------------------------------------------------ */
/*  SRAM (in-game save data)                                            */
/* ------------------------------------------------------------------ */

/*
 * These functions operate on the cartridge SRAM -- the actual in-game
 * save data, distinct from emulator save states.
 *
 * melonds_sram_size    Returns the size of the cartridge save memory
 *                      in bytes, or 0 if no ROM is loaded or the cart
 *                      has no save memory.
 *
 * melonds_sram_read    Copy the current save data into out_buf.
 *                      buf_size must be >= melonds_sram_size().
 *                      Returns the number of bytes copied.
 *
 * melonds_sram_write   Replace the cartridge save memory with the
 *                      contents of buf. size must match exactly what
 *                      melonds_sram_size() returns.
 *                      Returns 1 on success, 0 on failure.
 *
 * melonds_sram_load_file   Load save data from a file on disk.
 *                          Returns 1 on success, 0 on failure.
 *
 * melonds_sram_save_file   Write current save data to a file on disk.
 *                          Returns 1 on success, 0 on failure.
 */
size_t melonds_sram_size(MelonDSHandle* handle);

size_t melonds_sram_read(MelonDSHandle* handle,
                          uint8_t*       out_buf,
                          size_t         buf_size);

int melonds_sram_write(MelonDSHandle*  handle,
                        const uint8_t* buf,
                        size_t         size);

int melonds_sram_load_file(MelonDSHandle* handle, const char* path);
int melonds_sram_save_file(MelonDSHandle* handle, const char* path);

/* ------------------------------------------------------------------ */
/*  Real-time clock                                                     */
/* ------------------------------------------------------------------ */

/*
 * DS games that depend on the time of day (day/night cycles, timed
 * events, etc.) read from the DS RTC hardware. These functions let
 * you control what the emulated RTC reports.
 *
 * melonds_rtc_set_time
 *   Set the RTC to a specific date and time. Fields follow standard C
 *   conventions: year is the full four-digit year, month is 1-12, day
 *   is 1-31, hour is 0-23, minute 0-59, second 0-59.
 *
 * melonds_rtc_sync_to_host
 *   Set the RTC to match the host machine's current system clock.
 *   Call this once at startup to keep the emulated clock in sync.
 */
void melonds_rtc_set_time(MelonDSHandle* handle,
                           int year, int month,  int day,
                           int hour, int minute, int second);

void melonds_rtc_sync_to_host(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Save states                                                         */
/* ------------------------------------------------------------------ */

/*
 * Emulator save states capture the complete machine state (CPU, RAM,
 * GPU, etc.) and are separate from the in-game SRAM save data.
 *
 * File-based save states are portable across sessions.
 * In-memory save states are faster and are the preferred method for
 * temporary snapshots taken during automation.
 */

int melonds_savestate(MelonDSHandle* handle, const char* path);
int melonds_loadstate(MelonDSHandle* handle, const char* path);

/*
 * melonds_savestate_mem / melonds_loadstate_mem
 * ----------------------------------------------
 * In-memory save states -- no disk I/O.
 *
 * melonds_savestate_mem allocates a buffer, writes the snapshot into
 * it, and sets *out_buf and *out_size. The caller must free the buffer
 * with melonds_free_buf() when done.
 *
 * melonds_loadstate_mem restores from a previously captured buffer.
 *
 * Both return 1 on success, 0 on failure.
 */
int melonds_savestate_mem(MelonDSHandle* handle,
                           uint8_t**      out_buf,
                           size_t*        out_size);

int melonds_loadstate_mem(MelonDSHandle* handle,
                           const uint8_t* buf,
                           size_t         size);

void melonds_free_buf(uint8_t* buf);

/* ------------------------------------------------------------------ */
/*  Video output                                                        */
/* ------------------------------------------------------------------ */

/*
 * melonds_set_video_enabled
 * -------------------------
 * Enable or disable the 2D/3D renderer. Disabling it skips all GPU
 * work, which is the main way to reach speeds much higher than
 * real-time. Screenshots are not possible while video is disabled.
 *
 * Enabled by default. Set to 0 for headless/fast operation.
 */
void melonds_set_video_enabled(MelonDSHandle* handle, int enabled);

/*
 * melonds_set_audio_enabled
 * -------------------------
 * Enable or disable the SPU audio mixer.
 *
 * When enabled, the SPU mixes audio each frame and the samples become
 * available via melonds_audio_read(). When disabled, the SPU is skipped
 * entirely and melonds_audio_read() will always return 0 samples.
 *
 * Disabled by default. Enable this when you want to hear the game or
 * need to use audio as a frame timing mechanism.
 */
void melonds_set_audio_enabled(MelonDSHandle* handle, int enabled);

/*
 * melonds_get_framebuffer
 * -----------------------
 * Returns a pointer to the combined top+bottom screen pixel data.
 *
 * Format: BGRA8888, 256 wide, 384 tall (top 192 rows then bottom 192).
 * The pointer is valid until the next call to melonds_run_frame().
 * Returns NULL if video is disabled or no frame has been rendered.
 */
const uint32_t* melonds_get_framebuffer(MelonDSHandle* handle);

/*
 * melonds_get_framebuffer_rgb
 * ---------------------------
 * Copy the current frame into caller-supplied buffer in RGB24 format
 * (3 bytes per pixel, top screen then bottom screen, row-major).
 * out_buf must be at least 256 * 384 * 3 bytes.
 * Returns 1 if a frame was copied, 0 if video is disabled.
 */
int melonds_get_framebuffer_rgb(MelonDSHandle* handle,
                                 uint8_t*       out_buf);

/* ------------------------------------------------------------------ */
/*  Audio output                                                        */
/* ------------------------------------------------------------------ */

/*
 * The DS SPU outputs stereo 16-bit PCM at 32768 Hz -- roughly 547
 * sample pairs per frame at 59.83 fps. The exact count varies slightly
 * each frame, so check melonds_audio_available() before reading.
 *
 * Format: interleaved int16_t pairs [L, R, L, R, ...], 4 bytes per pair.
 *
 * Typical usage:
 *
 *   melonds_run_frame(h);
 *   uint32_t n = melonds_audio_available(h);
 *   if (n > 0) {
 *       int16_t buf[n * 2];
 *       melonds_audio_read(h, buf, n);
 *   }
 */

/*
 * melonds_audio_available
 * -----------------------
 * Returns the number of stereo sample pairs currently sitting in the
 * SPU output buffer, ready to be drained by melonds_audio_read().
 * Returns 0 if audio is disabled or no ROM is loaded.
 */
uint32_t melonds_audio_available(MelonDSHandle* handle);

/*
 * melonds_audio_read
 * ------------------
 * Copy up to count stereo sample pairs out of the SPU buffer into
 * out_buf. out_buf must point to at least count * 4 bytes of storage
 * (count pairs * 2 channels * 2 bytes per sample).
 *
 * Returns the number of sample pairs actually copied. This will be
 * less than count if fewer samples were available.
 *
 * Samples that are read are consumed and will not be returned again.
 * Call this once per frame to drain the buffer and avoid overflow.
 */
uint32_t melonds_audio_read(MelonDSHandle* handle,
                             int16_t*       out_buf,
                             uint32_t       count);

/*
 * melonds_audio_sample_rate
 * -------------------------
 * Returns the SPU output sample rate in Hz. This is always 32768 for
 * a standard DS. Use this when configuring your audio output device.
 */
uint32_t melonds_audio_sample_rate(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Diagnostics                                                         */
/* ------------------------------------------------------------------ */

/*
 * melonds_get_error
 * -----------------
 * Returns a human-readable description of the last error, or NULL if
 * no error has occurred. The string is owned by the handle -- do not
 * free it.
 */
const char* melonds_get_error(MelonDSHandle* handle);

/*
 * melonds_get_frame_count
 * -----------------------
 * Returns the total number of frames run since the last create/reset.
 */
uint64_t melonds_get_frame_count(MelonDSHandle* handle);

#ifdef __cplusplus
}
#endif
