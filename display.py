import sys
import datetime
import pygame
sys.path.insert(0, 'python')
from melonds import MelonDSEmulator
from melonds.core import lib, ffi
from config import ROM_PATH, BIOS7_PATH, BIOS9_PATH, FIRMWARE_PATH
from memory_gen4 import Gen4Memory, GAME_PEARL
from pathlib import Path

SAVE_PATH = str(Path(ROM_PATH).with_suffix('.sav'))

SCREEN_W = 256
SCREEN_H = 192
SCALE    = 2

pygame.init()
window = pygame.display.set_mode((SCREEN_W * SCALE, SCREEN_H * 2 * SCALE))
pygame.display.set_caption("py-melonds")
clock = pygame.time.Clock()

emu = MelonDSEmulator(
    rom_path=ROM_PATH,
    bios7_path=BIOS7_PATH,
    bios9_path=BIOS9_PATH,
    firmware_path=FIRMWARE_PATH,
    save_path=SAVE_PATH,
    video_enabled=True,
    audio_enabled=False,
)

# Sync DS RTC to PC system time
emu.sync_rtc_to_now()
print(f"RTC set to {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

mem = Gen4Memory(emu, game=GAME_PEARL, language="EN")
pointers_loaded     = False
in_battle_last      = False
party               = []
save_indicator_last = 0

print("Running — close window or press Escape to quit")
print("Controls: Arrow keys | X=A  Z=B  Enter=Start  Backspace=Select  A=L  S=R  D=X  C=Y")
print("Touch: left-click bottom screen")

running = True
while running:
    # ------------------------------------------------------------------ events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mx, my = event.pos
                if my >= SCREEN_H * SCALE:
                    ds_x = max(0, min(255, mx // SCALE))
                    ds_y = max(0, min(191, (my - SCREEN_H * SCALE) // SCALE))
                    lib.melonds_set_touch(emu._handle, ds_x, ds_y)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                lib.melonds_release_touch(emu._handle)

    # ------------------------------------------------------------------ input
    keys = pygame.key.get_pressed()
    ds_keys = 0
    if keys[pygame.K_x]:         ds_keys |= 1      # A
    if keys[pygame.K_z]:         ds_keys |= 2      # B
    if keys[pygame.K_RETURN]:    ds_keys |= 8      # Start
    if keys[pygame.K_BACKSPACE]: ds_keys |= 4      # Select
    if keys[pygame.K_RIGHT]:     ds_keys |= 16     # Right
    if keys[pygame.K_LEFT]:      ds_keys |= 32     # Left
    if keys[pygame.K_UP]:        ds_keys |= 64     # Up
    if keys[pygame.K_DOWN]:      ds_keys |= 128    # Down
    if keys[pygame.K_s]:         ds_keys |= 256    # R
    if keys[pygame.K_a]:         ds_keys |= 512    # L
    if keys[pygame.K_d]:         ds_keys |= 1024   # X
    if keys[pygame.K_c]:         ds_keys |= 2048   # Y

    emu.set_inputs(ds_keys)
    emu.run_single_frame()

    # ------------------------------------------------------------------ pointer init
    if not pointers_loaded:
        anchor = emu.read_u32(0x021C489C)
        if anchor != 0:
            mem.update_pointers()
            pointers_loaded = True
            tid = mem.read_trainer_id()
            sid = mem.read_trainer_sid()
            print(f"\nIn-game! anchor=0x{anchor:08X}")
            print(f"  TID={tid}  SID={sid}")

    # ------------------------------------------------------------------ memory reads
    if pointers_loaded:
        try:
            in_battle = mem.is_in_battle()

            # ---- Save detection — runs every frame ----
            save_ind = emu.read_u8(mem._ptrs["save_indicator"])
            if save_indicator_last == 1 and save_ind == 0:
                print(f"\n  [SAVE] Save complete — flushing SRAM to disk...")
                try:
                    emu.save_sram(SAVE_PATH)
                    size = Path(SAVE_PATH).stat().st_size
                    print(f"  [SAVE] Done — {size} bytes written to {SAVE_PATH}")
                except Exception as e:
                    print(f"  [SAVE] Failed: {e}")
            save_indicator_last = save_ind

            # ---- Print state every 600 frames (~10 seconds at 60fps) ----
            if emu.frame_count % 600 == 0:
                state = mem.read_game_state()
                party = mem.read_party()
                print(f"\n--- frame {emu.frame_count} ---")
                print(f"  map={state['map_header']} | "
                      f"in_battle={in_battle} | "
                      f"pos=({state['trainer_x']},{state['trainer_z']}) | "
                      f"save_indicator=0x{save_ind:02X}")
                print(f"  TID={state['trainer_id']}  SID={mem.read_trainer_sid()}")
                print(f"  party ({len(party)}):")
                for mon in party:
                    shiny_mark = " *** SHINY ***" if mon['is_shiny'] else ""
                    print(f"    [{mon['slot']}] species={mon['species']:>3}  "
                          f"lv={mon['level']:>3}  "
                          f"nature={mon['nature']:<10}  "
                          f"pid=0x{mon['pid']:08X}  "
                          f"chk=0x{mon['checksum']:04X}"
                          f"{shiny_mark}")

            # ---- Battle start ----
            if in_battle and not in_battle_last:
                foe = mem.read_current_foe()
                tid = mem.read_trainer_id()
                sid = mem.read_trainer_sid()
                print(f"\n=== ENCOUNTER ===")
                if foe:
                    pid      = foe['pid']
                    sv       = tid ^ sid ^ (pid >> 16) ^ (pid & 0xFFFF)
                    is_shiny = sv < 8
                    shiny_mark = "  *** SHINY ***" if is_shiny else ""
                    print(f"  species={foe['species']:>3}  "
                          f"lv={foe['level']:>3}  "
                          f"nature={foe['nature']}")
                    print(f"  pid=0x{pid:08X}  "
                          f"TID={tid}  SID={sid}")
                    print(f"  shiny_value={sv}  "
                          f"shiny={is_shiny}"
                          f"{shiny_mark}")
                    print(f"  ivs={foe['ivs']}")
                else:
                    print("  (foe not yet loaded)")

            # ---- Battle end ----
            if not in_battle and in_battle_last:
                print("=== BATTLE ENDED ===\n")

            in_battle_last = in_battle

        except Exception as e:
            import traceback
            print(f"  memory read error: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------ render
    fb = lib.melonds_get_framebuffer(emu._handle)
    if fb != ffi.NULL:
        raw    = bytes(ffi.buffer(fb, SCREEN_W * SCREEN_H * 2 * 4))
        surf   = pygame.image.frombuffer(raw, (SCREEN_W, SCREEN_H * 2), 'BGRA')
        scaled = pygame.transform.scale(surf, (SCREEN_W * SCALE, SCREEN_H * 2 * SCALE))
        window.blit(scaled, (0, 0))
        pygame.display.flip()

    clock.tick(240)
    pygame.display.set_caption(f"py-melonds | {clock.get_fps():.0f} fps")

pygame.quit()
print("Done")
