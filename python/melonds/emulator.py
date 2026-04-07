"""
melonds/emulator.py
-------------------
High-level Python wrapper around the melonDS C bindings.

The MelonDSEmulator class is the main entry point for anyone using
py-melonds. It wraps the low-level C calls from core.py into a clean
Python interface that mirrors the design of libmgba-py.

Basic usage:

    from melonds import MelonDSEmulator

    emu = MelonDSEmulator(
        rom_path="game.nds",
        bios7_path="bios7.bin",   # optional
        bios9_path="bios9.bin",   # optional
        video_enabled=True,
        audio_enabled=True,
    )

    # run_single_frame() handles throttling and audio playback
    # internally when throttle=True (the default)
    while True:
        emu.press_button("A")
        emu.run_single_frame()
        value = emu.read_u32(0x02000000)

Speed control:

    emu.set_throttle(True)          # run at real-time speed (default)
    emu.set_speed_factor(2.0)       # run at 2x speed with audio
    emu.set_throttle(False)         # unthrottled, no audio output

When throttle is True, run_single_frame() blocks after each frame until
the correct amount of real time has passed. If audio is also enabled and
sounddevice is available, audio playback is used as the timing source
(same approach as libmgba-py). This gives accurate, smooth timing.
If sounddevice is not installed, a time.sleep() fallback is used.

When throttle is False, run_single_frame() returns immediately after the
frame completes. Audio samples are still mixed internally if audio is
enabled, but they are discarded rather than played back. Use this mode
when you want maximum speed and do not need to hear the game.

The DS runs at approximately 59.83 fps natively. At 1x speed with audio
enabled you will hear the game exactly as it was designed to sound.
"""

from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from .core import ffi, lib

# ---------------------------------------------------------------------------
# The DS native frame rate.
# The actual value is 33513982 / 560190 = 59.8261... fps but 59.8261 is
# close enough for sleep-based timing. Audio-based timing does not use this
# constant at all -- the audio stream's blocking write() call is the clock.
# ---------------------------------------------------------------------------
_DS_FPS = 59.8261


# ---------------------------------------------------------------------------
# Button constants
# ---------------------------------------------------------------------------

class Button:
    """
    DS button bitmask values. These match the hardware KEY register layout.
    Use these with set_inputs(), hold_button(), etc.

    Example:
        emu.set_inputs(Button.A | Button.RIGHT)
    """

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

    _NAME_MAP: dict[str, int] = {
        "A": A, "B": B,
        "Select": SELECT, "Start": START,
        "Right": RIGHT, "Left": LEFT, "Up": UP, "Down": DOWN,
        "R": R, "L": L, "X": X, "Y": Y,
    }

    @classmethod
    def from_name(cls, name: str) -> int:
        """
        Return the bitmask for a button given its name string.
        Raises KeyError if the name is not recognised.
        """
        return cls._NAME_MAP[name]


# ---------------------------------------------------------------------------
# FPS tracker
# ---------------------------------------------------------------------------

class _PerformanceTracker:
    """Tracks frames-per-second over a rolling one-second window."""

    def __init__(self) -> None:
        self._history:  deque[int] = deque([0], maxlen=60)
        self._counter:  int = 0
        self._bucket:   int = int(time.time())
        self._last_ns:  int = time.time_ns()

    def record_frame(self) -> None:
        now = int(time.time())
        if now != self._bucket:
            self._history.append(self._counter)
            self._counter = 0
            self._bucket  = now
        self._counter  += 1
        self._last_ns   = time.time_ns()

    @property
    def current_fps(self) -> int:
        return self._history[-1] if self._history else 0

    @property
    def time_since_last_frame_ns(self) -> int:
        return time.time_ns() - self._last_ns


# ---------------------------------------------------------------------------
# Audio output helper
# ---------------------------------------------------------------------------

class _AudioOutput:
    """
    Manages a sounddevice output stream for DS audio playback.

    sounddevice's blocking write() call acts as the frame rate limiter
    when throttle is enabled -- the same approach used by libmgba-py.
    At speeds above 1x, fewer samples are passed per write() call so
    it returns sooner. Falls back silently if sounddevice is not available.
    """

    def __init__(self, sample_rate: int, speed_factor: float) -> None:
        self._stream:       "sounddevice.RawOutputStream | None" = None
        self._sample_rate:  int   = sample_rate
        self._speed_factor: float = speed_factor
        self._available:    bool  = False
        self._try_open()

    def _try_open(self) -> None:
        try:
            import sounddevice as sd
            device_info = sd.query_devices(kind="output")
            host_rate   = int(device_info["default_samplerate"])
            self._stream = sd.RawOutputStream(
                samplerate = host_rate,
                channels   = 2,
                dtype      = "int16",
            )
            self._stream.start()
            self._available = True
        except Exception:
            self._stream    = None
            self._available = False

    def write(self, samples: bytes) -> None:
        """
        Write a block of int16 stereo samples to the audio stream.
        This call blocks until the hardware has consumed the samples,
        which is what provides the frame timing.
        """
        if self._stream is None:
            return
        try:
            import sounddevice as sd
            self._stream.write(samples)
        except Exception:
            self.close()

    def set_speed_factor(self, factor: float) -> None:
        """Update the speed factor used when deciding how many samples to feed per frame."""
        self._speed_factor = factor

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream    = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available


# ---------------------------------------------------------------------------
# Main emulator class
# ---------------------------------------------------------------------------

class MelonDSEmulator:
    """
    Wraps a single melonDS NDS emulator instance.

    One instance corresponds to one emulated DS. Create it, load a ROM,
    and then call run_single_frame() in a loop. The class does not create
    any threads or windows.

    Parameters
    ----------
    rom_path
        Path to the .nds ROM file to load.
    bios7_path
        Path to the ARM7 BIOS image (bios7.bin). Optional -- FreeBIOS
        is used if not given.
    bios9_path
        Path to the ARM9 BIOS image (bios9.bin). Optional -- FreeBIOS
        used if not given.
    firmware_path
        Path to the DS firmware image (firmware.bin). Optional -- a
        minimal stub is used if not given.
    video_enabled
        Whether to run the 2D/3D renderer each frame. Defaults to True.
        Set to False for maximum speed when you do not need the screen.
    audio_enabled
        Whether to run the SPU audio mixer. Defaults to False for
        backwards compatibility. Set to True if you want to hear the
        game or use audio-based throttling.
    throttle
        Whether to limit emulation to real-time speed. Defaults to True.
        When True, run_single_frame() blocks after each frame so the
        game runs at its intended speed. When False it returns
        immediately and runs as fast as the CPU allows.
    speed_factor
        Speed multiplier applied when throttle is True. 1.0 is normal
        speed, 2.0 is twice as fast, 0.5 is half speed. Defaults to 1.0.
    sync_rtc
        Whether to set the emulated RTC to the host machine's current
        time at construction. Defaults to True.
    """

    def __init__(
        self,
        rom_path: str | Path,
        bios7_path:    Optional[str | Path] = None,
        bios9_path:    Optional[str | Path] = None,
        firmware_path: Optional[str | Path] = None,
        video_enabled: bool  = True,
        audio_enabled: bool  = False,
        throttle:      bool  = True,
        speed_factor:  float = 1.0,
        sync_rtc:      bool  = True,
    ) -> None:
        self._rom_path    = str(rom_path)
        self._bios7       = str(bios7_path)    if bios7_path    else None
        self._bios9       = str(bios9_path)    if bios9_path    else None
        self._firmware    = str(firmware_path) if firmware_path else None
        self._video       = video_enabled
        self._audio       = audio_enabled
        self._throttle    = throttle
        self._speed       = speed_factor
        self._held        = 0
        self._pressed     = 0
        self._perf        = _PerformanceTracker()
        self._audio_out:  "_AudioOutput | None" = None

        self._handle = lib.melonds_create(
            self._bios7.encode()    if self._bios7    else ffi.NULL,
            self._bios9.encode()    if self._bios9    else ffi.NULL,
            self._firmware.encode() if self._firmware else ffi.NULL,
        )
        if self._handle == ffi.NULL:
            raise RuntimeError("melonds_create() failed")

        lib.melonds_set_video_enabled(self._handle, int(video_enabled))
        lib.melonds_set_audio_enabled(self._handle, int(audio_enabled))

        ok = lib.melonds_load_rom(self._handle, self._rom_path.encode())
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown error"
            lib.melonds_destroy(self._handle)
            self._handle = ffi.NULL
            raise RuntimeError(f"Failed to load ROM '{rom_path}': {msg}")

        if sync_rtc:
            lib.melonds_rtc_sync_to_host(self._handle)

        if self._audio and self._throttle:
            sample_rate = int(lib.melonds_audio_sample_rate(self._handle))
            self._audio_out = _AudioOutput(sample_rate, speed_factor)

    def __del__(self) -> None:
        if hasattr(self, "_audio_out") and self._audio_out is not None:
            self._audio_out.close()
        if hasattr(self, "_handle") and self._handle != ffi.NULL:
            lib.melonds_destroy(self._handle)
            self._handle = ffi.NULL

    def __repr__(self) -> str:
        return (
            f"MelonDSEmulator("
            f"rom={self._rom_path!r}, "
            f"frame={self.frame_count}, "
            f"fps={self.current_fps}, "
            f"throttle={self._throttle}, "
            f"speed={self._speed}x, "
            f"video={self._video}, "
            f"audio={self._audio})"
        )

    # ------------------------------------------------------------------
    # Frame execution
    # ------------------------------------------------------------------

    def run_single_frame(self) -> None:
        """
        Execute one DS frame.

        When throttle is True this method blocks until the correct
        amount of real time has elapsed before returning, so the game
        runs at its intended speed. Audio samples are played through
        your speakers if audio is enabled and sounddevice is available.

        When throttle is False this method returns as soon as the frame
        is done. The game runs as fast as the CPU allows. Audio samples
        are mixed internally but discarded rather than played back.
        """
        combined      = self._held | self._pressed
        self._pressed = 0
        lib.melonds_set_keys(self._handle, combined)
        lib.melonds_run_frame(self._handle)
        self._perf.record_frame()

        if not self._throttle:
            return

        if self._audio and self._audio_out is not None and self._audio_out.available:
            self._throttle_via_audio()
        else:
            self._throttle_via_sleep()

    def _throttle_via_audio(self) -> None:
        """
        Drain the SPU buffer and write samples to the audio stream.
        The blocking write() returns only after the hardware has consumed
        the samples, which is what provides accurate frame timing.
        At speed_factor > 1.0, fewer samples are passed so it returns sooner.
        """
        n = int(lib.melonds_audio_available(self._handle))
        if n == 0:
            return

        adjusted = max(1, int(n / self._speed))

        buf = ffi.new(f"int16_t[{adjusted * 2}]")
        got = lib.melonds_audio_read(self._handle, buf, adjusted)
        if got > 0:
            raw = bytes(ffi.buffer(buf, got * 4))
            self._audio_out.write(raw)

    def _throttle_via_sleep(self) -> None:
        """
        Sleep-based fallback throttle for when sounddevice is not
        available. Less precise than audio-based timing but good enough
        for normal playback. Does not produce any audio output.
        """
        target = (1.0 / _DS_FPS) / self._speed
        elapsed = self._perf.time_since_last_frame_ns / 1_000_000_000
        remaining = target - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @property
    def frame_count(self) -> int:
        """Total frames executed since the last create or reset."""
        return int(lib.melonds_get_frame_count(self._handle))

    @property
    def current_fps(self) -> int:
        """Frames completed in the most recent second."""
        return self._perf.current_fps

    # ------------------------------------------------------------------
    # Throttle and speed control
    # ------------------------------------------------------------------

    def set_throttle(self, throttle: bool) -> None:
        """
        Enable or disable real-time speed limiting.

        When switching from unthrottled to throttled, this opens the
        audio stream if audio is enabled. When switching the other way,
        the audio stream is closed.
        """
        was_throttled = self._throttle
        self._throttle = throttle

        if throttle and not was_throttled:
            if self._audio and self._audio_out is None:
                sample_rate  = int(lib.melonds_audio_sample_rate(self._handle))
                self._audio_out = _AudioOutput(sample_rate, self._speed)
        elif not throttle and was_throttled:
            if self._audio_out is not None:
                self._audio_out.close()
                self._audio_out = None

    def get_throttle(self) -> bool:
        """Return True if real-time throttling is currently active."""
        return self._throttle

    def set_speed_factor(self, factor: float) -> None:
        """
        Set the speed multiplier.

        1.0 is normal speed (the DS runs at ~59.83 fps). 2.0 runs twice
        as fast. 0.5 runs at half speed. Only has an effect when
        throttle is True.
        """
        self._speed = max(0.1, float(factor))
        if self._audio_out is not None:
            self._audio_out.set_speed_factor(self._speed)

    def get_speed_factor(self) -> float:
        """Return the current speed multiplier."""
        return self._speed

    # ------------------------------------------------------------------
    # Hard reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """
        Hard-reset the emulated DS. Equivalent to cycling the power.
        The loaded ROM stays loaded and the frame counter resets to zero.
        """
        lib.melonds_reset(self._handle)

    # ------------------------------------------------------------------
    # Button input
    # ------------------------------------------------------------------

    def press_button(self, button: str | int) -> None:
        """
        Queue a button press for the next frame only.
        The button is automatically released after one frame.
        Pass a Button constant or a name string such as "A".
        """
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._pressed |= mask

    def hold_button(self, button: str | int) -> None:
        """
        Hold a button down across all future frames until you call
        release_button() or release_all_buttons().
        """
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._held |= mask

    def release_button(self, button: str | int) -> None:
        """Release a previously held button."""
        mask = button if isinstance(button, int) else Button.from_name(button)
        self._held    &= ~mask
        self._pressed &= ~mask

    def release_all_buttons(self) -> None:
        """Release all held and pending button presses."""
        self._held    = 0
        self._pressed = 0

    def reset_held_buttons(self) -> int:
        """
        Release all held buttons and return the previous bitmask.
        Useful for saving and restoring input state around a temporary
        action.
        """
        prev = self._held
        self._held = 0
        return prev

    def restore_held_buttons(self, mask: int) -> None:
        """Restore a bitmask returned by reset_held_buttons()."""
        self._held = mask

    def set_inputs(self, inputs: int) -> None:
        """
        Directly set the complete held-button bitmask for the next frame.
        This replaces any previously held buttons.
        """
        self._held = inputs

    def is_button_held(self, button: str | int) -> bool:
        """Return True if the button is currently in the held state."""
        mask = button if isinstance(button, int) else Button.from_name(button)
        return bool(self._held & mask)

    # ------------------------------------------------------------------
    # Touch screen
    # ------------------------------------------------------------------

    def touch_screen(self, x: int, y: int) -> None:
        """
        Simulate a stylus press at pixel (x, y) on the bottom screen.
        x: 0-255, y: 0-191.
        The touch stays active until release_touch() is called.
        """
        lib.melonds_set_touch(self._handle, x, y)

    def release_touch(self) -> None:
        """Lift the stylus off the touch screen."""
        lib.melonds_release_touch(self._handle)

    # ------------------------------------------------------------------
    # Memory access
    # ------------------------------------------------------------------

    def read_u8(self, address: int) -> int:
        """Read a single unsigned byte from the ARM9 address space."""
        return int(lib.melonds_mem_read_8(self._handle, address))

    def read_u16(self, address: int) -> int:
        """Read a 16-bit little-endian value from the ARM9 address space."""
        return int(lib.melonds_mem_read_16(self._handle, address))

    def read_u32(self, address: int) -> int:
        """Read a 32-bit little-endian value from the ARM9 address space."""
        return int(lib.melonds_mem_read_32(self._handle, address))

    def write_u8(self, address: int, value: int) -> None:
        """Write a single byte to the ARM9 address space."""
        lib.melonds_mem_write_8(self._handle, address, value & 0xFF)

    def write_u16(self, address: int, value: int) -> None:
        """Write a 16-bit little-endian value to the ARM9 address space."""
        lib.melonds_mem_write_16(self._handle, address, value & 0xFFFF)

    def write_u32(self, address: int, value: int) -> None:
        """Write a 32-bit little-endian value to the ARM9 address space."""
        lib.melonds_mem_write_32(self._handle, address, value & 0xFFFFFFFF)

    def read_bytes(self, address: int, length: int) -> bytes:
        """
        Read length bytes from address and return them as a bytes object.

        Uses a fast memcpy path for addresses in Main RAM
        (0x02000000-0x023FFFFF). Falls back to byte-by-byte reads for
        other regions.
        """
        buf = ffi.new(f"uint8_t[{length}]")
        n   = lib.melonds_mem_read_bulk(self._handle, address, buf, length)
        return bytes(ffi.buffer(buf, n))

    def write_bytes(self, address: int, data: bytes) -> int:
        """
        Write data to memory starting at address.

        Uses a fast memcpy path for Main RAM. Returns the number of
        bytes actually written.
        """
        if not data:
            return 0
        buf = ffi.from_buffer(data)
        return int(lib.melonds_mem_write_bulk(self._handle, address, buf, len(data)))

    # ------------------------------------------------------------------
    # SRAM (in-game save data)
    # ------------------------------------------------------------------

    @property
    def sram_size(self) -> int:
        """Size of the cartridge save memory in bytes. 0 if no cart is loaded."""
        return int(lib.melonds_sram_size(self._handle))

    def read_save_data(self) -> bytes:
        """
        Read and return the cartridge SRAM as a bytes object.

        This is the in-game save data, not an emulator save state.
        Returns an empty bytes object if no cart is loaded or the cart
        has no save memory.
        """
        sz = self.sram_size
        if sz == 0:
            return b""
        buf = ffi.new(f"uint8_t[{sz}]")
        n   = lib.melonds_sram_read(self._handle, buf, sz)
        return bytes(ffi.buffer(buf, n))

    def write_save_data(self, data: bytes) -> None:
        """
        Replace the cartridge SRAM with the contents of data.

        The length of data must match sram_size exactly.
        Raises ValueError if the sizes do not match.
        """
        if len(data) != self.sram_size:
            raise ValueError(
                f"Save data length {len(data)} does not match "
                f"cart SRAM size {self.sram_size}"
            )
        buf = ffi.from_buffer(data)
        ok  = lib.melonds_sram_write(self._handle, buf, len(data))
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown error"
            raise RuntimeError(f"write_save_data() failed: {msg}")

    def load_save_file(self, path: str | Path) -> None:
        """Load in-game save data from a .dsv file on disk."""
        ok = lib.melonds_sram_load_file(self._handle, str(path).encode())
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown error"
            raise RuntimeError(f"load_save_file('{path}') failed: {msg}")

    def save_to_file(self, path: str | Path) -> None:
        """Write the current cartridge SRAM to a file on disk."""
        ok = lib.melonds_sram_save_file(self._handle, str(path).encode())
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown error"
            raise RuntimeError(f"save_to_file('{path}') failed: {msg}")

    # ------------------------------------------------------------------
    # Real-time clock
    # ------------------------------------------------------------------

    def set_rtc(self, dt: datetime) -> None:
        """Set the emulated DS clock to the given datetime."""
        lib.melonds_rtc_set_time(
            self._handle,
            dt.year, dt.month,  dt.day,
            dt.hour, dt.minute, dt.second,
        )

    def sync_rtc_to_host(self) -> None:
        """Set the emulated RTC to the current host system time."""
        lib.melonds_rtc_sync_to_host(self._handle)

    # ------------------------------------------------------------------
    # Save states
    # ------------------------------------------------------------------

    def save_state(self) -> bytes:
        """
        Capture a complete emulator snapshot and return it as bytes.

        This saves the entire machine state (CPU registers, RAM, GPU,
        etc.) and is separate from the in-game SRAM save. The snapshot
        is kept in memory and no disk I/O occurs.
        """
        buf_ptr  = ffi.new("uint8_t**")
        size_ptr = ffi.new("size_t*")
        ok = lib.melonds_savestate_mem(self._handle, buf_ptr, size_ptr)
        if not ok:
            raise RuntimeError("save_state() failed")
        size = int(size_ptr[0])
        data = bytes(ffi.buffer(buf_ptr[0], size))
        lib.melonds_free_buf(buf_ptr[0])
        return data

    def load_state(self, state: bytes) -> None:
        """Restore a snapshot previously captured with save_state()."""
        buf = ffi.from_buffer(state)
        ok  = lib.melonds_loadstate_mem(self._handle, buf, len(state))
        if not ok:
            raise RuntimeError("load_state() failed")

    def save_state_to_file(self, path: str | Path) -> None:
        """Write a save state to a file on disk."""
        ok = lib.melonds_savestate(self._handle, str(path).encode())
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown error"
            raise RuntimeError(f"save_state_to_file('{path}') failed: {msg}")

    def load_state_from_file(self, path: str | Path) -> None:
        """Load a save state from a file on disk."""
        ok = lib.melonds_loadstate(self._handle, str(path).encode())
        if not ok:
            err = lib.melonds_get_error(self._handle)
            msg = ffi.string(err).decode() if err != ffi.NULL else "unknown error"
            raise RuntimeError(f"load_state_from_file('{path}') failed: {msg}")

    @contextmanager
    def peek_frame(self, frames: int = 1) -> Generator[None, None, None]:
        """
        Context manager that runs the emulator forward by frames steps,
        yields, then restores the state to what it was before.

            with emu.peek_frame(30):
                # 30 frames have been executed here
                val = emu.read_u32(some_address)
            # state is restored here

        Audio is not output during peek_frame, regardless of throttle
        settings.
        """
        snapshot = self.save_state()
        saved_throttle = self._throttle
        self._throttle = False  # no throttle or audio during lookahead
        for _ in range(frames):
            lib.melonds_run_frame(self._handle)
        try:
            yield
        finally:
            self.load_state(snapshot)
            self._throttle = saved_throttle

    # ------------------------------------------------------------------
    # Video and screenshots
    # ------------------------------------------------------------------

    def set_video_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the renderer. Disabling it skips all 2D/3D
        GPU work and is the main way to run faster than real-time.
        Screenshots are not available while video is disabled.
        """
        self._video = enabled
        lib.melonds_set_video_enabled(self._handle, int(enabled))

    def set_audio_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the SPU audio mixer.

        When enabling audio while throttle is True, this also opens the
        audio output stream if sounddevice is available.
        """
        self._audio = enabled
        lib.melonds_set_audio_enabled(self._handle, int(enabled))

        if enabled and self._throttle and self._audio_out is None:
            sample_rate     = int(lib.melonds_audio_sample_rate(self._handle))
            self._audio_out = _AudioOutput(sample_rate, self._speed)
        elif not enabled and self._audio_out is not None:
            self._audio_out.close()
            self._audio_out = None

    @property
    def video_enabled(self) -> bool:
        return self._video

    @property
    def audio_enabled(self) -> bool:
        return self._audio

    def get_framebuffer(self) -> bytes:
        """
        Return the last rendered frame as raw BGRA bytes.

        256 pixels wide, 384 pixels tall (top screen rows 0-191, bottom
        screen rows 192-383). Each pixel is 4 bytes in BGRA order.
        Returns an empty bytes object if video is disabled.
        """
        ptr = lib.melonds_get_framebuffer(self._handle)
        if ptr == ffi.NULL:
            return b""
        return bytes(ffi.buffer(ptr, 256 * 384 * 4))

    def get_screenshot(self) -> "PIL.Image.Image":
        """
        Return the current screen as a PIL Image in RGB mode.

        If video is currently disabled, this method temporarily enables
        it, runs one extra frame to populate the framebuffer, captures
        the image, then restores the original state. The returned image
        will be one frame ahead of the current emulator state in that
        case. Audio throttling is suspended during this operation.

        Requires Pillow (pip install Pillow).
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImportError(
                "get_screenshot() requires Pillow. "
                "Install it with: pip install Pillow"
            )

        restore_state = None
        if not self._video:
            restore_state = self.save_state()
            lib.melonds_set_video_enabled(self._handle, 1)
            # Run without throttle so we do not output audio for this frame
            lib.melonds_run_frame(self._handle)

        buf = ffi.new("uint8_t[%d]" % (256 * 384 * 3))
        lib.melonds_get_framebuffer_rgb(self._handle, buf)
        img = Image.frombytes("RGB", (256, 384), bytes(ffi.buffer(buf, 256 * 384 * 3)))

        if restore_state is not None:
            self.load_state(restore_state)
            lib.melonds_set_video_enabled(self._handle, 0)

        return img
