"""
melonds/emulator.py
-------------------
High-level Python wrapper around the melonDS C bindings.

This class is intentionally modelled after the Gen 3 bot's
LibmgbaEmulator so that porting bot logic between generations is
straightforward. The interface you call in the NDS bot will mirror
what the Gen 3 bot already does:

    emulator = MelonDSEmulator(
        rom_path="platinum.nds",
        bios7_path="bios7.bin",
        bios9_path="bios9.bin",
    )

    # Python owns the frame loop — no emulator speed limiter
    while True:
        emulator.set_inputs(held | pressed)
        emulator.run_single_frame()
        val = emulator.read_u32(0x021C489C)
        ...

Key design decisions mirroring libmgba:
  - Video disabled by default for maximum speed
  - Audio disabled by default (no timing lock)
  - run_single_frame() has NO internal sleep — caller controls speed
  - read_bytes() maps directly to Main RAM via memcpy (no per-byte overhead)
  - save_state() / load_state() work in-memory (bytes object, no disk)
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from .core import ffi, lib


# ---------------------------------------------------------------------------
# Button bitmask constants — same names as the Gen 3 bot uses
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Performance tracker (mirrors PerformanceTracker in libmgba.py)
# ---------------------------------------------------------------------------

class PerformanceTracker:
    fps_history: deque[int]

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


# ---------------------------------------------------------------------------
# Main emulator class
# ---------------------------------------------------------------------------

class MelonDSEmulator:
    """
    Wraps a single melonDS NDS instance.

    Lifecycle::

        emulator = MelonDSEmulator("game.nds")
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
        video_enabled: bool = False,   # off = fast, like Gen3 bot default
        audio_enabled: bool = False,
    ):
        self._rom_path      = str(rom_path)
        self._bios7         = str(bios7_path)  if bios7_path    else None
        self._bios9         = str(bios9_path)  if bios9_path    else None
        self._firmware      = str(firmware_path) if firmware_path else None

        self._video_enabled = video_enabled
        self._audio_enabled = audio_enabled

        # Held buttons accumulate across frames; pressed are cleared each frame
        self._held_inputs:    int = 0
        self._pressed_inputs: int = 0

        self._performance = PerformanceTracker()

        # Create the native instance
        self._handle = lib.melonds_create(
            self._bios7.encode()    if self._bios7    else ffi.NULL,
            self._bios9.encode()    if self._bios9    else ffi.NULL,
            self._firmware.encode() if self._firmware else ffi.NULL,
        )
        if self._handle == ffi.NULL:
            raise RuntimeError("melonds_create() returned NULL")

        # Apply speed settings immediately
        lib.melonds_set_video_enabled(self._handle, int(video_enabled))
        lib.melonds_set_audio_enabled(self._handle, int(audio_enabled))

        # Load ROM
        ok = lib.melonds_load_rom(
            self._handle,
            self._rom_path.encode()
        )
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown"
            lib.melonds_destroy(self._handle)
            self._handle = ffi.NULL
            raise RuntimeError(f"Failed to load ROM '{rom_path}': {msg}")

    def __del__(self):
        if hasattr(self, "_handle") and self._handle != ffi.NULL:
            lib.melonds_destroy(self._handle)
            self._handle = ffi.NULL

    # ------------------------------------------------------------------
    # Frame execution
    # ------------------------------------------------------------------

    def run_single_frame(self) -> None:
        """
        Execute one DS frame synchronously. No sleep, no limiter.
        Python controls timing — call in a tight loop for max speed.

        Mirrors LibmgbaEmulator.run_single_frame() from the Gen 3 bot.
        """
        # Combine held + pressed, then clear pressed for next frame
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
    # Input control
    # ------------------------------------------------------------------

    def press_button(self, button: str | int) -> None:
        """
        Queue a button to be pressed for exactly one frame.
        If the same button was held last frame it is first released.
        """
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._pressed_inputs |= mask

    def hold_button(self, button: str | int) -> None:
        """Hold a button across all future frames until release_button()."""
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._held_inputs |= mask

    def release_button(self, button: str | int) -> None:
        """Release a previously held button."""
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._held_inputs    &= ~mask
        self._pressed_inputs &= ~mask

    def release_all_buttons(self) -> None:
        self._held_inputs    = 0
        self._pressed_inputs = 0

    def set_inputs(self, inputs: int) -> None:
        """Set the complete held-button bitmask directly."""
        self._held_inputs = inputs

    def touch_screen(self, x: int, y: int) -> None:
        """
        Simulate a stylus press at (x, y) on the bottom screen.
        x: 0–255, y: 0–191
        """
        lib.melonds_set_touch(self._handle, x, y)

    def release_touch(self) -> None:
        lib.melonds_release_touch(self._handle)

    # ------------------------------------------------------------------
    # Memory access — mirrors LibmgbaEmulator.read_bytes()
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
        """
        Read `length` bytes from `address` and return as a bytes object.

        Uses a fast memcpy path for Main RAM (0x02000000–0x023FFFFF).
        This is the primary method for reading Pokémon data structures.

        Mirrors LibmgbaEmulator.read_bytes() from the Gen 3 bot.
        """
        buf = ffi.new(f"uint8_t[{length}]")
        n   = lib.melonds_mem_read_bulk(self._handle, address, buf, length)
        return bytes(ffi.buffer(buf, n))

    # ------------------------------------------------------------------
    # Save states — in-memory, no disk I/O (mirrors libmgba)
    # ------------------------------------------------------------------

    def save_state(self) -> bytes:
        """
        Capture a full emulator snapshot and return it as a bytes object.
        No file I/O — this is fast enough to call every few seconds.

        Mirrors LibmgbaEmulator.get_save_state().
        """
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
        """
        Restore a snapshot previously captured with save_state().

        Mirrors LibmgbaEmulator.load_save_state().
        """
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
    # peek_frame — run ahead without keeping changes (like Gen3 bot)
    # ------------------------------------------------------------------

    @contextmanager
    def peek_frame(self, frames_to_advance: int = 1) -> Generator[None, None, None]:
        """
        Context manager: run N frames ahead, yield, then restore state.

        Identical pattern to LibmgbaEmulator.peek_frame() in Gen3 bot.
        Useful for checking what will happen without committing.

            with emulator.peek_frame(30):
                # 30 frames have been run
                val = emulator.read_u32(addr)
            # state is now restored — those 30 frames never happened
        """
        snapshot = self.save_state()
        for _ in range(frames_to_advance):
            lib.melonds_run_frame(self._handle)
        try:
            yield
        finally:
            self.load_state(snapshot)

    # ------------------------------------------------------------------
    # Speed / render control (the key speedup vs Lua bot)
    # ------------------------------------------------------------------

    def set_video_enabled(self, enabled: bool) -> None:
        """
        Toggle the 2D/3D renderer. Disabling it removes all GPU work
        and is the primary speed multiplier — same trick the Gen3 bot
        uses to reach 1000+ FPS.
        """
        self._video_enabled = enabled
        lib.melonds_set_video_enabled(self._handle, int(enabled))

    def set_audio_enabled(self, enabled: bool) -> None:
        self._audio_enabled = enabled
        lib.melonds_set_audio_enabled(self._handle, int(enabled))

    @property
    def video_enabled(self) -> bool:
        return self._video_enabled

    @property
    def audio_enabled(self) -> bool:
        return self._audio_enabled

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Hard reset the emulated DS."""
        lib.melonds_reset(self._handle)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"MelonDSEmulator("
            f"rom={self._rom_path!r}, "
            f"frame={self.frame_count}, "
            f"fps={self.current_fps}, "
            f"video={self._video_enabled}, "
            f"audio={self._audio_enabled})"
        )
