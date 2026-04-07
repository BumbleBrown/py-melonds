import sys
sys.path.insert(0, 'python')
from melonds.core import ffi, lib
from config import ROM_PATH, BIOS7_PATH, BIOS9_PATH, FIRMWARE_PATH
from pathlib import Path

SAVE_PATH = str(Path(ROM_PATH).with_suffix('.sav'))

# Bypass MelonDSEmulator and call C functions directly
h = lib.melonds_create(
    BIOS7_PATH.encode(),
    BIOS9_PATH.encode(),
    FIRMWARE_PATH.encode(),
)

lib.melonds_set_video_enabled(h, 1)
lib.melonds_set_audio_enabled(h, 0)

ok = lib.melonds_load_rom_with_save(
    h,
    ROM_PATH.encode(),
    SAVE_PATH.encode(),
)
print(f"ROM loaded: {ok}")

for i in range(30000):
    if i % 30 == 0:
        lib.melonds_set_keys(h, 1)  # A button
    else:
        lib.melonds_set_keys(h, 0)
    lib.melonds_run_frame(h)
    if i % 3000 == 0:
        anchor = lib.melonds_mem_read_32(h, 0x021C489C)
        start  = lib.melonds_mem_read_32(h, 0x021066D4)
        # Also check if RAM is changing at all
        ram0   = lib.melonds_mem_read_32(h, 0x02000000)
        print(f"  frame {i:,} | anchor=0x{anchor:08X} | start=0x{start:08X} | ram0=0x{ram0:08X}")

lib.melonds_destroy(h)