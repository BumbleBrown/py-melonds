"""
melonds/core.py
---------------
CFFI bindings for the melonDS shared library.
"""

import os
import platform
from cffi import FFI

ffi = FFI()

ffi.cdef("""
    typedef struct MelonDSHandle MelonDSHandle;

    /* Lifecycle */
    MelonDSHandle* melonds_create(const char* bios7_path,
                                   const char* bios9_path,
                                   const char* firmware_path);
    void melonds_destroy(MelonDSHandle* handle);
    void melonds_reset(MelonDSHandle* handle);

    /* RTC */
    void melonds_set_rtc(MelonDSHandle* handle,
                         int year, int month,  int day,
                         int hour, int minute, int second);

    /* ROM loading */
    int melonds_load_rom(MelonDSHandle* handle, const char* rom_path);
    int melonds_load_rom_with_save(MelonDSHandle* handle,
                                    const char*    rom_path,
                                    const char*    save_path);
    int melonds_save_sram(MelonDSHandle* handle, const char* save_path);

    /* Frame execution */
    void melonds_run_frame(MelonDSHandle* handle);

    /* Input */
    #define MELONDS_KEY_A       1
    #define MELONDS_KEY_B       2
    #define MELONDS_KEY_SELECT  4
    #define MELONDS_KEY_START   8
    #define MELONDS_KEY_RIGHT   16
    #define MELONDS_KEY_LEFT    32
    #define MELONDS_KEY_UP      64
    #define MELONDS_KEY_DOWN    128
    #define MELONDS_KEY_R       256
    #define MELONDS_KEY_L       512
    #define MELONDS_KEY_X       1024
    #define MELONDS_KEY_Y       2048

    void melonds_set_keys(MelonDSHandle* handle, uint32_t keys);
    void melonds_set_touch(MelonDSHandle* handle, int x, int y);
    void melonds_release_touch(MelonDSHandle* handle);

    /* Memory access */
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

    /* Save states */
    int  melonds_savestate    (MelonDSHandle* handle, const char* path);
    int  melonds_loadstate    (MelonDSHandle* handle, const char* path);
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


def _find_library() -> str:
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []

    if platform.system() == "Windows":
        lib_name = "melonds.dll"
    elif platform.system() == "Darwin":
        lib_name = "melonds.dylib"
    else:
        lib_name = "melonds.so"

    candidates.append(os.path.join(this_dir, lib_name))

    env_path = os.environ.get("MELONDS_LIB_PATH")
    if env_path:
        candidates.append(env_path)

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


lib = _find_library()
lib = ffi.dlopen(lib)

__all__ = ["ffi", "lib"]
