import sys, time
sys.path.insert(0, 'python')
from melonds import MelonDSEmulator
from memory_gen4 import Gen4Memory, GAME_PEARL

from config import ROM_PATH, BIOS7_PATH, BIOS9_PATH, FIRMWARE_PATH
from pathlib import Path

SAVE_PATH = str(Path(ROM_PATH).with_suffix('.sav'))
print(f"Using save: {SAVE_PATH}")

emu = MelonDSEmulator(
    rom_path=ROM_PATH,
    bios7_path=BIOS7_PATH,
    bios9_path=BIOS9_PATH,
    firmware_path=FIRMWARE_PATH,
    save_path=SAVE_PATH,
    video_enabled=False,
    audio_enabled=False,
)

mem = Gen4Memory(emu, game=GAME_PEARL, language="EN")

print("Booting — pressing A/Start every 60 frames to advance menus...")
total = 0
while True:
    for i in range(500):
        # Press A every 60 frames to advance past title, press start, continue screen
        if i % 60 == 0:
            emu.press_button("A")
        emu.run_single_frame()
    total += 500

    anchor = emu.read_u32(0x021C489C)

    if anchor == 0:
        print(f"  {total:,} frames | still booting...")
        if total >= 200_000:
            print("Gave up.")
            break
        continue

    mem.update_pointers()
    loaded = mem.is_save_loaded()
    print(f"  {total:,} frames | anchor=0x{anchor:08X} | save_loaded={loaded} | map={mem.read_map_header()}")

    if loaded:
        print("\nSave loaded! Reading state...")
        state = mem.read_game_state()
        print(f"  map={state['map_header']} pos=({state['trainer_x']},{state['trainer_z']})")
        print(f"  trainer={state['trainer_name']} TID={state['trainer_id']}")
        party = mem.read_party()
        print(f"  party ({len(party)} pokemon):")
        for mon in party:
            print(f"    [{mon['slot']}] species={mon['species']} lv={mon['level']} shiny={mon['is_shiny']} nature={mon['nature']} nick={mon['nickname']!r}")
        break

    if total >= 200_000:
        print("Stopped at 200k frames — save never loaded.")
        break