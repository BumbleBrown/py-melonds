"""
melonds/emulator.py
-------------------
High-level Python wrapper around the melonDS C bindings.
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from .core import ffi, lib


class Button:
    A      = int(lib.MELONDS_KEY_A)
    B      = int(lib.MELONDS_KEY_B)
    SELECT = int(lib.MELONDS_KEY_SELECT)
    START  = int(lib.MELONDS_KEY_START)
    RIGHT  = int(lib.MELONDS_KEY_RIGHT)
    LEFT   = int(lib.MELONDS_KEY_LEFT)
    UP     = int(lib.MELONDS_KEY_UP)
    DOWN   = int(lib.MELONDS_KEY_DOWN)
    R      = int(lib.MELONDS_KEY_R)
    L      = int(lib.MELONDS_KEY_L)
    X      = int(lib.MELONDS_KEY_X)
    Y      = int(lib.MELONDS_KEY_Y)

    _NAME_MAP = {
        "A": A, "B": B, "Select": SELECT, "Start": START,
        "Right": RIGHT, "Left": LEFT, "Up": UP, "Down": DOWN,
        "R": R, "L": L, "X": X, "Y": Y,
    }

    @classmethod
    def from_name(cls, name: str) -> int:
        return cls._NAME_MAP[name]


class PerformanceTracker:
    def __init__(self):
        self.fps_history          = deque([0], maxlen=60)
        self._frame_counter       = 0
        self._frame_counter_time  = int(time.time())
        self._last_frame_ns       = time.time_ns()

    def track_frame(self) -> None:
        now_s = int(time.time())
        if self._frame_counter_time != now_s:
            self.fps_history.append(self._frame_counter)
            self._frame_counter      = 0
            self._frame_counter_time = now_s
        self._frame_counter += 1
        self._last_frame_ns = time.time_ns()

    @property
    def current_fps(self) -> int:
        return self.fps_history[-1] if self.fps_history else 0

    @property
    def time_since_last_frame_ns(self) -> int:
        return time.time_ns() - self._last_frame_ns


class MelonDSEmulator:
    """
    Wraps a single melonDS NDS instance.

    Lifecycle::

        emulator = MelonDSEmulator("game.nds", save_path="game.sav")
        while True:
            emulator.press_button("A")
            emulator.run_single_frame()
            val = emulator.read_u32(0x02000000)
    """

    def __init__(
        self,
        rom_path: str | Path,
        bios7_path: Optional[str | Path] = None,
        bios9_path: Optional[str | Path] = None,
        firmware_path: Optional[str | Path] = None,
        save_path: Optional[str | Path] = None,
        video_enabled: bool = False,
        audio_enabled: bool = False,
    ):
        self._rom_path   = str(rom_path)
        self._bios7      = str(bios7_path)    if bios7_path    else None
        self._bios9      = str(bios9_path)    if bios9_path    else None
        self._firmware   = str(firmware_path) if firmware_path else None
        self._save_path  = str(save_path)     if save_path     else None

        self._video_enabled = video_enabled
        self._audio_enabled = audio_enabled

        self._held_inputs:    int = 0
        self._pressed_inputs: int = 0
        self._performance = PerformanceTracker()

        # Create native instance
        self._handle = lib.melonds_create(
            self._bios7.encode()     if self._bios7     else ffi.NULL,
            self._bios9.encode()     if self._bios9     else ffi.NULL,
            self._firmware.encode()  if self._firmware  else ffi.NULL,
        )
        if self._handle == ffi.NULL:
            raise RuntimeError("melonds_create() returned NULL")

        lib.melonds_set_video_enabled(self._handle, int(video_enabled))
        lib.melonds_set_audio_enabled(self._handle, int(audio_enabled))

        # Load ROM
        if self._save_path:
            ok = lib.melonds_load_rom_with_save(
                self._handle,
                self._rom_path.encode(),
                self._save_path.encode(),
            )
        else:
            ok = lib.melonds_load_rom(
                self._handle,
                self._rom_path.encode(),
            )

        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown"
            lib.melonds_destroy(self._handle)
            self._handle = ffi.NULL
            raise RuntimeError(f"Failed to load ROM '{rom_path}': {msg}")

    def __repr__(self) -> str:
        return (
            f"MelonDSEmulator(rom={self._rom_path!r}, "
            f"save={self._save_path!r}, "
            f"frames={self.frame_count})"
        )

    def __del__(self):
        if hasattr(self, "_handle") and self._handle != ffi.NULL:
            lib.melonds_destroy(self._handle)
            self._handle = ffi.NULL

    # ------------------------------------------------------------------
    # RTC
    # ------------------------------------------------------------------

    def set_rtc(self, year: int, month: int, day: int,
                hour: int, minute: int, second: int) -> None:
        """
        Sync the DS real-time clock to the given date/time.
        Call this after creating the emulator to match PC system time.
        """
        lib.melonds_set_rtc(self._handle, year, month, day, hour, minute, second)

    def sync_rtc_to_now(self) -> None:
        """Convenience: set DS RTC to the current PC date/time."""
        import datetime
        now = datetime.datetime.now()
        self.set_rtc(now.year, now.month, now.day,
                     now.hour, now.minute, now.second)

    # ------------------------------------------------------------------
    # Frame execution
    # ------------------------------------------------------------------

    def run_single_frame(self) -> None:
        combined = self._held_inputs | self._pressed_inputs
        lib.melonds_set_keys(self._handle, combined)
        self._pressed_inputs = 0
        lib.melonds_run_frame(self._handle)
        self._performance.track_frame()

    @property
    def frame_count(self) -> int:
        return int(lib.melonds_get_frame_count(self._handle))

    @property
    def current_fps(self) -> int:
        return self._performance.current_fps

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def press_button(self, button: str | int) -> None:
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._pressed_inputs |= mask

    def hold_button(self, button: str | int) -> None:
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._held_inputs |= mask

    def release_button(self, button: str | int) -> None:
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._held_inputs    &= ~mask
        self._pressed_inputs &= ~mask

    def release_all_buttons(self) -> None:
        self._held_inputs    = 0
        self._pressed_inputs = 0

    def set_inputs(self, inputs: int) -> None:
        self._held_inputs = inputs

    def touch_screen(self, x: int, y: int) -> None:
        lib.melonds_set_touch(self._handle, x, y)

    def release_touch(self) -> None:
        lib.melonds_release_touch(self._handle)

    # ------------------------------------------------------------------
    # Memory access
    # ------------------------------------------------------------------

    def read_u8(self, address: int) -> int:
        return int(lib.melonds_mem_read_8(self._handle, address))

    def read_u16(self, address: int) -> int:
        return int(lib.melonds_mem_read_16(self._handle, address))

    def read_u32(self, address: int) -> int:
        return int(lib.melonds_mem_read_32(self._handle, address))

    def write_u8(self, address: int, value: int) -> None:
        lib.melonds_mem_write_8(self._handle, address, value & 0xFF)

    def write_u16(self, address: int, value: int) -> None:
        lib.melonds_mem_write_16(self._handle, address, value & 0xFFFF)

    def write_u32(self, address: int, value: int) -> None:
        lib.melonds_mem_write_32(self._handle, address, value & 0xFFFFFFFF)

    def read_bytes(self, address: int, length: int) -> bytes:
        buf = ffi.new(f"uint8_t[{length}]")
        n   = lib.melonds_mem_read_bulk(self._handle, address, buf, length)
        return bytes(ffi.buffer(buf, n))

    # ------------------------------------------------------------------
    # Save states
    # ------------------------------------------------------------------

    def save_state(self) -> bytes:
        buf_ptr  = ffi.new("uint8_t**")
        size_ptr = ffi.new("size_t*")
        ok = lib.melonds_savestate_mem(self._handle, buf_ptr, size_ptr)
        if not ok:
            raise RuntimeError("melonds_savestate_mem() failed")
        size = int(size_ptr[0])
        data = bytes(ffi.buffer(buf_ptr[0], size))
        lib.melonds_free_buf(buf_ptr[0])
        return data

    def load_state(self, state: bytes) -> None:
        buf = ffi.from_buffer(state)
        ok  = lib.melonds_loadstate_mem(self._handle, buf, len(state))
        if not ok:
            raise RuntimeError("melonds_loadstate_mem() failed")

    def save_state_to_file(self, path: str | Path) -> None:
        ok = lib.melonds_savestate(self._handle, str(path).encode())
        if not ok:
            raise RuntimeError(f"melonds_savestate() failed: {path}")

    def load_state_from_file(self, path: str | Path) -> None:
        ok = lib.melonds_loadstate(self._handle, str(path).encode())
        if not ok:
            raise RuntimeError(f"melonds_loadstate() failed: {path}")

    # ------------------------------------------------------------------
    # Cartridge SRAM
    # ------------------------------------------------------------------

    def save_sram(self, path: Optional[str | Path] = None) -> None:
        """
        Write cartridge SRAM (in-game save data) to disk.
        If path is None, writes back to the original save_path.
        """
        target = str(path) if path else self._save_path
        if not target:
            raise RuntimeError(
                "No save path available. Pass a path or set save_path in __init__."
            )
        ok = lib.melonds_save_sram(self._handle, target.encode())
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown"
            raise RuntimeError(f"melonds_save_sram() failed: {msg}")

    # ------------------------------------------------------------------
    # peek_frame
    # ------------------------------------------------------------------

    @contextmanager
    def peek_frame(self, frames_to_advance: int = 1) -> Generator[None, None, None]:
        snapshot = self.save_state()
        for _ in range(frames_to_advance):
            lib.melonds_run_frame(self._handle)
        try:
            yield
        finally:
            self.load_state(snapshot)

    # ------------------------------------------------------------------
    # Renderer control
    # ------------------------------------------------------------------

    def set_video_enabled(self, enabled: bool) -> None:
        self._video_enabled = enabled
        lib.melonds_set_video_enabled(self._handle, int(enabled))

    def set_audio_enabled(self, enabled: bool) -> None:
        self._audio_enabled = enabled
        lib.melonds_set_audio_enabled(self._handle, int(enabled))

    def get_framebuffer(self) -> Optional[bytes]:
        ptr = lib.melonds_get_framebuffer(self._handle)
        if ptr == ffi.NULL:
            return None
        return bytes(ffi.buffer(ptr, 256 * 384 * 4))
