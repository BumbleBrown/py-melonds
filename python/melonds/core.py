"""
melonds/core.py
---------------
Low-level CFFI bindings for libmelonds.

This module loads the compiled shared library and exposes the raw C API
to Python. It mirrors how libmgba-py works: CFFI parses the C header,
loads the .dll/.so, and returns callable function objects.

You normally don't use this module directly — use emulator.py instead,
which wraps these calls in a clean Python class identical in spirit to
the Gen 3 bot's LibmgbaEmulator.
"""

import ctypes
import os
import platform
import sys
from cffi import FFI

ffi = FFI()

# ---------------------------------------------------------------------------
# C interface declaration — must match melonds_interface.h exactly.
# CFFI parses this as C (not C++), so no C++ syntax here.
# ---------------------------------------------------------------------------

ffi.cdef("""
    typedef struct MelonDSHandle MelonDSHandle;

    /* Key bitmask constants */
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

    /* Memory */
    uint8_t  melonds_mem_read_8 (MelonDSHandle* handle, uint32_t addr);
    uint16_t melonds_mem_read_16(MelonDSHandle* handle, uint32_t addr);
    uint32_t melonds_mem_read_32(MelonDSHandle* handle, uint32_t addr);
    void melonds_mem_write_8 (MelonDSHandle* handle, uint32_t addr, uint8_t  val);
    void melonds_mem_write_16(MelonDSHandle* handle, uint32_t addr, uint16_t val);
    void melonds_mem_write_32(MelonDSHandle* handle, uint32_t addr, uint32_t val);
    size_t melonds_mem_read_bulk(MelonDSHandle* handle, uint32_t addr,
                                  uint8_t* out_buf, size_t length);

    /* Save states */
    int  melonds_savestate(MelonDSHandle* handle, const char* path);
    int  melonds_loadstate(MelonDSHandle* handle, const char* path);
    int  melonds_savestate_mem(MelonDSHandle* handle,
                                uint8_t** out_buf, size_t* out_size);
    int  melonds_loadstate_mem(MelonDSHandle* handle,
                                const uint8_t* buf, size_t size);
    void melonds_free_buf(uint8_t* buf);

    /* Renderer / speed */
    void melonds_set_video_enabled(MelonDSHandle* handle, int enabled);
    void melonds_set_audio_enabled(MelonDSHandle* handle, int enabled);
    const uint32_t* melonds_get_framebuffer(MelonDSHandle* handle);

    /* Diagnostics */
    const char* melonds_get_error(MelonDSHandle* handle);
    uint64_t    melonds_get_frame_count(MelonDSHandle* handle);
""")

# ---------------------------------------------------------------------------
# Locate and load the shared library
# ---------------------------------------------------------------------------

def _find_library() -> str:
    """
    Find the compiled melonds shared library.
    Search order:
      1. Same directory as this file (python/melonds/)
      2. MELONDS_LIB_PATH environment variable
      3. build/ directory relative to repo root
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))

    candidates = []

    # Platform-specific filename
    if platform.system() == "Windows":
        lib_name = "melonds.dll"
    elif platform.system() == "Darwin":
        lib_name = "melonds.dylib"
    else:
        lib_name = "melonds.so"

    # 1. Same directory as core.py
    candidates.append(os.path.join(this_dir, lib_name))

    # 2. Environment variable override
    env_path = os.environ.get("MELONDS_LIB_PATH")
    if env_path:
        candidates.append(env_path)

    # 3. build/ directory (common CMake output)
    repo_root = os.path.dirname(os.path.dirname(this_dir))
    candidates.append(os.path.join(repo_root, "build", lib_name))

    for path in candidates:
        if os.path.isfile(path):
            return path

    raise FileNotFoundError(
        f"Could not find {lib_name}. "
        f"Build the project first with CMake, or set MELONDS_LIB_PATH. "
        f"Searched: {candidates}"
    )


def _load_lib():
    path = _find_library()
    return ffi.dlopen(path)


# Singleton library handle — loaded once on first import
lib = _load_lib()

# Re-export ffi so callers can allocate CFFI buffers if needed
__all__ = ["ffi", "lib"]
