# py-melonds

Python bindings for [melonDS](https://github.com/melonDS-emu/melonDS), a Nintendo DS emulator.

The goal of this project is straightforward: expose melonDS to Python in the same way that [libmgba-py](https://github.com/hanzi/libmgba-py) exposes mGBA for Game Boy Advance, or [py-desmume](https://github.com/SkyTemple/py-desmume) exposes DeSmuME. No GUI, no window -- just a Python API you can call from a loop to run frames, read memory, and control input.

Pre-built binaries for Windows are available on the [releases](../../releases) page. Linux and macOS build scripts are included but those platforms have not been tested -- if you get it working, pull requests are welcome.

```python
from melonds import MelonDSEmulator

emu = MelonDSEmulator(
    rom_path="game.nds",
    bios7_path="bios7.bin",   # optional -- FreeBIOS used if omitted
    bios9_path="bios9.bin",   # optional
    video_enabled=False,      # disable for maximum speed
    audio_enabled=False,
)

while True:
    emu.press_button("A")
    emu.run_single_frame()
    val = emu.read_u32(0x02000000)
```

## Installation

### Pre-built (recommended)

Download the zip for your platform from the [releases](../../releases) page and extract it. The `melonds/` folder inside is the Python package. Place it somewhere Python can find it, then install the one required dependency:

```
pip install cffi
```

Optionally, for `get_screenshot()`:

```
pip install Pillow
```

For audio output at normal speed:

```
pip install sounddevice
```

### Automated install

Copy `install.py` from this repo into your project and call it at startup:

```python
from pathlib import Path
from install import install_melonds

install_melonds(target_dir=Path("melonds"), version="v0.1.0")

from melonds import MelonDSEmulator
```

### Build from source

Requires Git, CMake 3.15+, and a C++17 compiler (MSVC 2022, GCC 11+, or Clang 13+).

```
git clone --recurse-submodules https://github.com/bumblebrown/py-melonds.git
cd py-melonds
scripts\build_win64.bat
```

If you already cloned without `--recurse-submodules`:

```
git submodule update --init --recursive
```

The compiled library is copied to `python/melonds/` automatically after a successful build.

## What it can do

- Run frames at unthrottled speed with no internal limiter
- Read and write arbitrary DS memory addresses
- Fast bulk memory reads via direct memcpy for Main RAM
- Load and dump cartridge SRAM (in-game save data)
- Capture and restore in-memory save states (fast, no disk I/O)
- Control the DS real-time clock
- Capture screenshots as PIL images
- Simulate button presses, holds, and touch screen input
- Run frames ahead and roll back with `peek_frame`
- Audio output at native DS speed via sounddevice

## API reference

### MelonDSEmulator

```python
MelonDSEmulator(
    rom_path,
    bios7_path=None,
    bios9_path=None,
    firmware_path=None,
    video_enabled=True,
    audio_enabled=False,
    throttle=True,
    speed_factor=1.0,
    sync_rtc=True,
)
```

| Method / property | Description |
|---|---|
| `run_single_frame()` | Run one frame. Handles throttle and audio internally. |
| `reset()` | Hard-reset the emulated DS. |
| `frame_count` | Total frames run since last create/reset. |
| `current_fps` | Frames completed in the last second. |
| `set_throttle(bool)` | Enable or disable real-time speed limiting. |
| `get_throttle()` | Current throttle state. |
| `set_speed_factor(float)` | Speed multiplier (1.0 = normal, 2.0 = 2x). |
| `get_speed_factor()` | Current speed multiplier. |
| `press_button(button)` | Press for one frame only. |
| `hold_button(button)` | Hold until released. |
| `release_button(button)` | Release a held button. |
| `release_all_buttons()` | Release everything. |
| `reset_held_buttons()` | Release all held, return previous mask. |
| `restore_held_buttons(mask)` | Restore a saved mask. |
| `set_inputs(mask)` | Set held-button mask directly. |
| `is_button_held(button)` | Check held state. |
| `touch_screen(x, y)` | Press touch screen at (x, y). |
| `release_touch()` | Lift the stylus. |
| `read_u8/u16/u32(addr)` | Read from ARM9 address space. |
| `write_u8/u16/u32(addr, val)` | Write to ARM9 address space. |
| `read_bytes(addr, length)` | Read a block of bytes. |
| `write_bytes(addr, data)` | Write a block of bytes. |
| `sram_size` | Cartridge save size in bytes. |
| `read_save_data()` | Read SRAM as bytes. |
| `write_save_data(data)` | Replace SRAM. |
| `load_save_file(path)` | Load SRAM from a .dsv file. |
| `save_to_file(path)` | Write SRAM to a .dsv file. |
| `set_rtc(datetime)` | Set the emulated clock. |
| `sync_rtc_to_host()` | Sync clock to host system time. |
| `save_state()` | Capture machine state as bytes. |
| `load_state(data)` | Restore a captured state. |
| `save_state_to_file(path)` | Write save state to disk. |
| `load_state_from_file(path)` | Load save state from disk. |
| `peek_frame(n=1)` | Run n frames then roll back (context manager). |
| `set_video_enabled(bool)` | Toggle the renderer. |
| `set_audio_enabled(bool)` | Toggle SPU audio mixing. |
| `get_framebuffer()` | Raw BGRA framebuffer bytes (256x384). |
| `get_screenshot()` | PIL Image in RGB mode. Requires Pillow. |

### Button

```python
from melonds import Button

emu.set_inputs(Button.A | Button.START)
emu.press_button("A")
mask = Button.from_name("Up")
```

Available: `A`, `B`, `X`, `Y`, `L`, `R`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `START`, `SELECT`.

### Low-level access

The raw CFFI handles are exported for callers that need direct C access:

```python
from melonds import ffi, lib

fb = lib.melonds_get_framebuffer(emu._handle)
```

## Project layout

```
py-melonds/
  melonDS/                git submodule (melonDS-emu/melonDS, unmodified)
  src/
    melonds_interface.h   C API header (the only header CFFI sees)
    melonds_interface.cpp C++ implementation
    platform_headless.cpp Platform stubs (no Qt/SDL/OpenGL)
  python/melonds/
    __init__.py
    core.py               CFFI bindings
    emulator.py           MelonDSEmulator class
  scripts/
    build_win64.bat
  .github/workflows/
    build-release.yml     automated release builds
  install.py              download helper for end users
  CMakeLists.txt
  pyproject.toml
  README.md
```

## Platform support

| Platform | Status |
|---|---|
| Windows x64 | Tested and working |
| Linux x86_64 | Build scripts included, not tested |
| macOS Intel | Build scripts included, not tested |
| macOS Apple Silicon | Build scripts included, not tested |

If you get Linux or macOS working, please open a pull request.

## License

melonDS is licensed under the GNU General Public License v3. This binding library is also released under GPL v3.

---

*This project was developed with assistance from [Claude](https://claude.ai) by Anthropic. The goal was to do for melonDS what libmgba-py does for mGBA and py-desmume does for DeSmuME -- expose the emulator core to Python so it can be driven programmatically.*
