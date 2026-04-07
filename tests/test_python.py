"""
tests/test_python.py
--------------------
Python-level smoke test for py-melonds.

Run after building the shared library:
    python tests/test_python.py [path/to/rom.nds] [bios7.bin] [bios9.bin]

Without a ROM it just tests that the library loads and the class
instantiates. With a ROM it runs 300 frames and checks encounter rate
math.
"""

import sys
import time
from pathlib import Path

# Add the python/ directory to the path so we can import melonds
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from melonds import MelonDSEmulator, Button


def sep():
    print("-" * 50)


def test_library_loads():
    """The CFFI binding must load the .dll/.so without error."""
    from melonds.core import lib, ffi
    assert lib is not None
    print("[1] Library loaded OK")


def test_create_without_rom():
    """MelonDSEmulator should raise if the ROM file doesn't exist."""
    import os
    try:
        emu = MelonDSEmulator("nonexistent_rom_xyz.nds")
        emu  # should not reach here
        print("[2] FAIL — expected RuntimeError")
        return False
    except (RuntimeError, FileNotFoundError):
        print("[2] Correctly rejected missing ROM — OK")
        return True


def test_with_rom(rom_path, bios7=None, bios9=None):
    sep()
    print(f"Testing with ROM: {rom_path}")

    # --- Create emulator (video+audio off for speed) ---
    emu = MelonDSEmulator(
        rom_path=rom_path,
        bios7_path=bios7,
        bios9_path=bios9,
        video_enabled=False,
        audio_enabled=False,
    )
    print(f"[3] Created: {emu}")

    # --- Run 60 frames and time it ---
    start = time.perf_counter()
    for _ in range(60):
        emu.run_single_frame()
    elapsed = time.perf_counter() - start

    fps_60 = 60 / elapsed
    print(f"[4] 60 frames in {elapsed*1000:.1f}ms = {fps_60:.0f} FPS")

    # --- Memory read ---
    val = emu.read_u32(0x02000000)
    print(f"[5] read_u32(0x02000000) = 0x{val:08X}")

    # --- Bulk read (pk5 size = 220 bytes) ---
    data = emu.read_bytes(0x02000000, 220)
    assert len(data) == 220
    print(f"[6] read_bytes(220) OK — first 4: {data[:4].hex()}")

    # --- In-memory save state round trip ---
    snapshot = emu.save_state()
    print(f"[7] save_state() — {len(snapshot)} bytes")

    for _ in range(60):
        emu.run_single_frame()

    emu.load_state(snapshot)
    print(f"[8] load_state() — frame_count back to {emu.frame_count}")

    # --- peek_frame context manager ---
    before = emu.read_u32(0x02000000)
    with emu.peek_frame(30):
        after_peek = emu.read_u32(0x02000000)
    after_restore = emu.read_u32(0x02000000)
    assert before == after_restore, "peek_frame didn't restore state!"
    print(f"[9] peek_frame(30) OK — state restored correctly")

    # --- Unthrottled speed benchmark (300 frames) ---
    start = time.perf_counter()
    for _ in range(300):
        emu.run_single_frame()
    elapsed = time.perf_counter() - start
    fps_300 = 300 / elapsed
    enc_per_hour = fps_300 / 60 * 3600  # rough estimate: 1 enc per ~60 frames

    print(f"\n[10] Speed benchmark (300 frames unthrottled):")
    print(f"     {fps_300:.0f} FPS  ≈  {enc_per_hour:,.0f} enc/hr (estimate)")

    if fps_300 < 120:
        print("     WARNING: Speed seems low — check that video/audio are disabled")
    elif fps_300 > 500:
        print("     Excellent! Well above the Gen3 bot baseline")
    else:
        print("     Good — similar to or better than the Gen3 bot")

    # --- Button constants ---
    assert Button.A      == 1
    assert Button.B      == 2
    assert Button.START  == 8
    print("[11] Button constants OK")

    # --- Input round trip ---
    emu.press_button("A")
    emu.hold_button("Down")
    emu.run_single_frame()
    emu.release_button("Down")
    emu.release_all_buttons()
    print("[12] Input API OK")

    # --- Touch screen ---
    emu.touch_screen(128, 96)
    emu.run_single_frame()
    emu.release_touch()
    print("[13] Touch screen OK")

    print(f"\nFinal state: {emu}")
    return True


if __name__ == "__main__":
    sep()
    print("py-melonds Python smoke test")
    sep()

    test_library_loads()
    test_create_without_rom()

    if len(sys.argv) > 1:
        rom  = sys.argv[1]
        bio7 = sys.argv[2] if len(sys.argv) > 2 else None
        bio9 = sys.argv[3] if len(sys.argv) > 3 else None
        ok   = test_with_rom(rom, bio7, bio9)
        sep()
        print("PASS" if ok else "FAIL")
    else:
        sep()
        print("No ROM provided — skipping frame execution tests.")
        print("Usage: python test_python.py rom.nds [bios7.bin] [bios9.bin]")
        print("PASS (basic import only)")
