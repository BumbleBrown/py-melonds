# py-melonds

Python bindings for melonDS - Nintendo DS emulation from Python.

Built for automation, tooling, and bot development. Runs headless for maximum speed or with a display using pygame.

## What this is

py-melonds lets you drive a Nintendo DS emulator entirely from Python. You control the frame loop, read memory directly, and set inputs programmatically - no GUI required unless you want one.

```python
from melonds import MelonDSEmulator

emu = MelonDSEmulator(
    rom_path="game.nds",
    bios7_path="bios7.bin",
    bios9_path="bios9.bin",
    firmware_path="firmware.bin",
    video_enabled=False,
    audio_enabled=False,
)

while True:
    emu.press_button("A")
    emu.run_single_frame()
    val = emu.read_u32(0x02000000)
```

## Requirements

- Python 3.11+
- cffi (`pip install cffi`)
- pygame (`pip install pygame`) - only needed for display

## Windows Quick Start

1. Download the latest release zip from the [Releases](https://github.com/BumbleBrown/py-melonds/releases) page
2. Extract all 4 DLLs into `python/melonds/`
3. `pip install cffi pygame`
4. Copy `config.example.py` to `config.py` and fill in your paths
5. `python display.py`

You will need BIOS and firmware files dumped from a real DS:
- `bios7.bin` - 16KB ARM7 BIOS
- `bios9.bin` - 4KB ARM9 BIOS
- `firmware.bin` - 256KB firmware

## Building from Source

Requirements: Git, CMake 3.15+, GCC/MSVC, Python 3.11+

```bash
git clone https://github.com/BumbleBrown/py-melonds.git
cd py-melonds
git submodule update --init --recursive
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
pip install cffi pygame
python display.py
```

Windows users should use MSYS2 MinGW64 for building.

## Project Structure

```
py-melonds/
├── melonDS/                   - melonDS submodule (unmodified)
├── src/
│   ├── melonds_interface.h    - C ABI header
│   ├── melonds_interface.cpp  - C++ wrapper around NDS class
│   └── platform_headless.cpp - Headless platform stubs
├── python/melonds/
│   ├── __init__.py
│   ├── core.py                - CFFI bindings
│   └── emulator.py            - MelonDSEmulator class
├── tests/
│   ├── test_c.cpp             - C smoke test
│   └── test_python.py         - Python smoke test
├── display.py                 - Example pygame display
└── config.example.py          - Config template
```

## API

```python
from melonds import MelonDSEmulator

emu = MelonDSEmulator(rom_path, bios7_path, bios9_path, firmware_path)

# Frame control
emu.run_single_frame()

# Input
emu.press_button("A")        # Single frame press
emu.hold_button("Down")      # Hold until released
emu.release_button("Down")
emu.touch_screen(x, y)       # Touch screen (0-255, 0-191)
emu.release_touch()

# Memory
emu.read_u8(address)
emu.read_u16(address)
emu.read_u32(address)
emu.read_bytes(address, length)
emu.write_u32(address, value)

# Save states
state = emu.save_state()     # Returns bytes
emu.load_state(state)

# Speed control
emu.set_video_enabled(False)  # Disable renderer for speed
emu.set_audio_enabled(False)

# Peek ahead without keeping changes
with emu.peek_frame(30):
    val = emu.read_u32(addr)
# state restored here
```

## License

melonDS is GPL v3. This wrapper is also GPL v3.

## Credits

- [melonDS](https://github.com/melonDS-emu/melonDS) by Arisotura and contributors
- Inspired by [libmgba-py](https://github.com/hanzi/libmgba-py) and [pokebot-gen3](https://github.com/40Cakes/pokebot-gen3)
