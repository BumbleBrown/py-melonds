"""
melonds/core.py
---------------
Low-level CFFI bindings for the melonds shared library.

This module finds and loads the compiled melonds.dll / melonds.so /
melonds.dylib, then declares the C interface so CFFI can call into it.

Most users should import MelonDSEmulator from melonds.emulator instead
of using this module directly. The ffi and lib objects are re-exported
here for callers that need raw C-level access.
"""

import os
import platform
from cffi import FFI

ffi = FFI()

# The C declarations must match melonds_interface.h exactly.
# CFFI parses this as C, so no C++ syntax is allowed here.
ffi.cdef("""
    typedef struct MelonDSHandle MelonDSHandle;

    /* Button bitmask constants */
    static const int MELONDS_KEY_A      = 1;
    static const int MELONDS_KEY_B      = 2;
    static const int MELONDS_KEY_SELECT = 4;
    static const int MELONDS_KEY_START  = 8;
    static const int MELONDS_KEY_RIGHT  = 16;
    static const int MELONDS_KEY_LEFT   = 32;
    static const int MELONDS_KEY_UP     = 64;
    static const int MELONDS_KEY_DOWN   = 128;
    static const int MELONDS_KEY_R      = 256;
    static const int MELONDS_KEY_L      = 512;
    static const int MELONDS_KEY_X      = 1024;
    static const int MELONDS_KEY_Y      = 2048;

    /* Lifecycle */
    MelonDSHandle* melonds_create(const char* bios7_path,
                                   const char* bios9_path,
                                   const char* firmware_path);
    void melonds_destroy(MelonDSHandle* handle);
    void melonds_reset(MelonDSHandle* handle);

    /* ROM */
    int melonds_load_rom(MelonDSHandle* handle, const char* rom_path);

    /* Frame */
    void melonds_run_frame(MelonDSHandle* handle);

    /* Input */
    void melonds_set_keys(MelonDSHandle* handle, uint32_t keys);
    void melonds_set_touch(MelonDSHandle* handle, int x, int y);
    void melonds_release_touch(MelonDSHandle* handle);

    /* Memory - scalar */
    uint8_t  melonds_mem_read_8 (MelonDSHandle* handle, uint32_t addr);
    uint16_t melonds_mem_read_16(MelonDSHandle* handle, uint32_t addr);
    uint32_t melonds_mem_read_32(MelonDSHandle* handle, uint32_t addr);
    void melonds_mem_write_8 (MelonDSHandle* handle, uint32_t addr, uint8_t  val);
    void melonds_mem_write_16(MelonDSHandle* handle, uint32_t addr, uint16_t val);
    void melonds_mem_write_32(MelonDSHandle* handle, uint32_t addr, uint32_t val);

    /* Memory - bulk */
    size_t melonds_mem_read_bulk(MelonDSHandle* handle,
                                  uint32_t addr,
                                  uint8_t* out_buf,
                                  size_t length);
    size_t melonds_mem_write_bulk(MelonDSHandle* handle,
                                   uint32_t addr,
                                   const uint8_t* buf,
                                   size_t length);

    /* SRAM */
    size_t melonds_sram_size(MelonDSHandle* handle);
    size_t melonds_sram_read(MelonDSHandle* handle,
                              uint8_t* out_buf,
                              size_t buf_size);
    int    melonds_sram_write(MelonDSHandle* handle,
                               const uint8_t* buf,
                               size_t size);
    int    melonds_sram_load_file(MelonDSHandle* handle, const char* path);
    int    melonds_sram_save_file(MelonDSHandle* handle, const char* path);

    /* RTC */
    void melonds_rtc_set_time(MelonDSHandle* handle,
                               int year, int month,  int day,
                               int hour, int minute, int second);
    void melonds_rtc_sync_to_host(MelonDSHandle* handle);

    /* Save states */
    int  melonds_savestate(MelonDSHandle* handle, const char* path);
    int  melonds_loadstate(MelonDSHandle* handle, const char* path);
    int  melonds_savestate_mem(MelonDSHandle* handle,
                                uint8_t** out_buf,
                                size_t* out_size);
    int  melonds_loadstate_mem(MelonDSHandle* handle,
                                const uint8_t* buf,
                                size_t size);
    void melonds_free_buf(uint8_t* buf);

    /* Video */
    void melonds_set_video_enabled(MelonDSHandle* handle, int enabled);
    void melonds_set_audio_enabled(MelonDSHandle* handle, int enabled);
    const uint32_t* melonds_get_framebuffer(MelonDSHandle* handle);
    int  melonds_get_framebuffer_rgb(MelonDSHandle* handle, uint8_t* out_buf);

    /* Audio */
    uint32_t melonds_audio_available(MelonDSHandle* handle);
    uint32_t melonds_audio_read(MelonDSHandle* handle,
                                 int16_t* out_buf,
                                 uint32_t count);
    uint32_t melonds_audio_sample_rate(MelonDSHandle* handle);

    /* Diagnostics */
    const char* melonds_get_error(MelonDSHandle* handle);
    uint64_t    melonds_get_frame_count(MelonDSHandle* handle);
""")


def _find_library() -> str:
    """
    Locate the compiled melonds shared library.

    Search order:
      1. Same directory as this file (python/melonds/).
         The CMake build copies the library here after a successful build.
      2. The MELONDS_LIB_PATH environment variable.
         Set this if you want to use a library from a custom location.
      3. A build/ directory at the repository root.
         Useful during development before installing.
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))

    if platform.system() == "Windows":
        lib_name = "melonds.dll"
    elif platform.system() == "Darwin":
        lib_name = "melonds.dylib"
    else:
        lib_name = "melonds.so"

    candidates = [
        os.path.join(this_dir, lib_name),
    ]

    env_override = os.environ.get("MELONDS_LIB_PATH")
    if env_override:
        candidates.append(env_override)

    repo_root = os.path.dirname(os.path.dirname(this_dir))
    candidates.append(os.path.join(repo_root, "build", lib_name))

    for path in candidates:
        if os.path.isfile(path):
            return path

    raise FileNotFoundError(
        f"Could not find {lib_name}. "
        "Build the project first (see README.md), or set the "
        f"MELONDS_LIB_PATH environment variable. "
        f"Searched: {candidates}"
    )


lib = ffi.dlopen(_find_library())

__all__ = ["ffi", "lib"]
