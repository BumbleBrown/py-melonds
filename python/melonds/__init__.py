"""
melonds
-------
Python bindings for melonDS, a Nintendo DS emulator.

Basic usage:

    from melonds import MelonDSEmulator

    emu = MelonDSEmulator("game.nds", video_enabled=False, audio_enabled=False)

    while True:
        emu.press_button("A")
        emu.run_single_frame()
        value = emu.read_u32(0x02000000)

See MelonDSEmulator and Button for full documentation.
"""

from .emulator import MelonDSEmulator, Button
from .core import ffi, lib

__version__ = "0.1.0"
__all__ = ["MelonDSEmulator", "Button", "ffi", "lib"]
