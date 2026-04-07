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

MelonDSHandle* melonds_create(const char* bios7_path,
                               const char* bios9_path,
                               const char* firmware_path);

void melonds_destroy(MelonDSHandle* handle);

/*
 * melonds_reset
 * -------------
 * Hard-reset the emulated DS (equivalent to power-cycling).
 * The loaded ROM stays loaded.
 */
void melonds_reset(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  RTC                                                                 */
/* ------------------------------------------------------------------ */

/*
 * melonds_set_rtc
 * ---------------
 * Set the DS real-time clock to the given date/time.
 * Call this after melonds_load_rom() to sync with PC system time.
 * year: full year (e.g. 2026), month: 1–12, day: 1–31,
 * hour: 0–23, minute: 0–59, second: 0–59.
 */
void melonds_set_rtc(MelonDSHandle* handle,
                     int year, int month,  int day,
                     int hour, int minute, int second);

/* ------------------------------------------------------------------ */
/*  ROM loading                                                         */
/* ------------------------------------------------------------------ */

int melonds_load_rom(MelonDSHandle* handle, const char* rom_path);

int melonds_load_rom_with_save(MelonDSHandle* handle,
                                const char*    rom_path,
                                const char*    save_path);

int melonds_save_sram(MelonDSHandle* handle, const char* save_path);

/* ------------------------------------------------------------------ */
/*  Frame execution — the hot path                                      */
/* ------------------------------------------------------------------ */

void melonds_run_frame(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Input                                                               */
/* ------------------------------------------------------------------ */

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

void melonds_set_keys(MelonDSHandle* handle, uint32_t keys);
void melonds_set_touch(MelonDSHandle* handle, int x, int y);
void melonds_release_touch(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Memory access                                                       */
/* ------------------------------------------------------------------ */

uint8_t  melonds_mem_read_8 (MelonDSHandle* handle, uint32_t addr);
uint16_t melonds_mem_read_16(MelonDSHandle* handle, uint32_t addr);
uint32_t melonds_mem_read_32(MelonDSHandle* handle, uint32_t addr);

void melonds_mem_write_8 (MelonDSHandle* handle, uint32_t addr, uint8_t  val);
void melonds_mem_write_16(MelonDSHandle* handle, uint32_t addr, uint16_t val);
void melonds_mem_write_32(MelonDSHandle* handle, uint32_t addr, uint32_t val);

size_t melonds_mem_read_bulk(MelonDSHandle* handle,
                              uint32_t addr,
                              uint8_t* out_buf,
                              size_t   length);

/* ------------------------------------------------------------------ */
/*  Save states                                                         */
/* ------------------------------------------------------------------ */

int  melonds_savestate    (MelonDSHandle* handle, const char* path);
int  melonds_loadstate    (MelonDSHandle* handle, const char* path);
int  melonds_savestate_mem(MelonDSHandle* handle,
                            uint8_t** out_buf, size_t* out_size);
int  melonds_loadstate_mem(MelonDSHandle* handle,
                            const uint8_t* buf, size_t size);
void melonds_free_buf(uint8_t* buf);

/* ------------------------------------------------------------------ */
/*  Renderer / speed control                                            */
/* ------------------------------------------------------------------ */

void melonds_set_video_enabled(MelonDSHandle* handle, int enabled);
void melonds_set_audio_enabled(MelonDSHandle* handle, int enabled);
const uint32_t* melonds_get_framebuffer(MelonDSHandle* handle);

/* ------------------------------------------------------------------ */
/*  Diagnostics                                                         */
/* ------------------------------------------------------------------ */

const char* melonds_get_error(MelonDSHandle* handle);
uint64_t    melonds_get_frame_count(MelonDSHandle* handle);

#ifdef __cplusplus
}
#endif
