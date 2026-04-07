# py-melonds

Python bindings for [melonDS](https://github.com/melonDS-emu/melonDS) — a headless Nintendo DS emulator library, mirroring the architecture of [libmgba-py](https://github.com/hanzi/libmgba-py) for Gen 3.

## What this is

This provides a Python API to drive melonDS programmatically — no GUI, no window, just a tight Python loop calling `run_single_frame()` and reading DS memory directly. The goal is the same unthrottled 1000+ FPS that the Gen 3 pokebot achieves with libmgba.

```python
from melonds import MelonDSEmulator

emu = MelonDSEmulator(
    rom_path="platinum.nds",
    bios7_path="bios7.bin",   # optional — FreeBIOS used if omitted
    bios9_path="bios9.bin",   # optional
    video_enabled=False,      # disable renderer for max speed
    audio_enabled=False,
)

# Python owns the frame loop — no emulator speed limiter
while True:
    emu.press_button("A")
    emu.run_single_frame()
    val = emu.read_u32(0x021C489C)   # any DS memory address
```

## Architecture

```
py-melonds/
├── melonDS/              ← git submodule (melonDS-emu/melonDS, unmodified)
├── src/
│   ├── melonds_interface.h    ← C ABI header (all Python sees)
│   ├── melonds_interface.cpp  ← C++ wrapper around melonDS::NDS
│   └── platform_headless.cpp  ← Platform:: stubs (no Qt/SDL/OpenGL)
├── python/melonds/
│   ├── __init__.py
│   ├── core.py           ← CFFI bindings (loads the .dll/.so)
│   └── emulator.py       ← MelonDSEmulator class
├── tests/
│   ├── test_c.cpp         ← C smoke test (no Python needed)
│   └── test_python.py     ← Python smoke test
└── CMakeLists.txt
```

## Prerequisites

- Git
- CMake 3.15+
- C++17 compiler (MSVC 2022, GCC 11+, or Clang 13+)
- Python 3.11+
- `pip install cffi`

## Build

### Windows (MSYS2 or Visual Studio)
```bat
scripts\build_win64.bat
```

### Linux
```bash
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
```

### Manual
```bash
git submodule update --init --recursive
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --parallel
```

The compiled library (`melonds.dll` / `melonds.so`) is automatically
copied to `python/melonds/` after a successful build.

## Test

```bash
# C smoke test (no Python)
./build/melonds_test platinum.nds bios7.bin bios9.bin

# Python smoke test
pip install cffi
python tests/test_python.py platinum.nds bios7.bin bios9.bin
```

## Speed vs current Lua bot

| Mode | Lua bot (BizHawk/DeSmuME) | py-melonds |
|---|---|---|
| Normal | ~1,200 enc/hr | — |
| Focus mode | ~2,000–3,000 enc/hr | — |
| Unthrottled (video off) | **Not possible** | ~5,000–6,000+ enc/hr |

The speed difference is architectural: the Lua bot is a callback inside
BizHawk's frame loop. py-melonds owns the loop, just like libmgba-py.

## License

melonDS is GPL v3. This wrapper is also GPL v3.
