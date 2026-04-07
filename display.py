import sys
import pygame

sys.path.insert(0, 'python')
from melonds import MelonDSEmulator
from melonds.core import lib, ffi
from config import ROM_PATH, BIOS7_PATH, BIOS9_PATH, FIRMWARE_PATH

SCREEN_W = 256
SCREEN_H = 192
SCALE = 2

pygame.init()
window = pygame.display.set_mode((SCREEN_W * SCALE, SCREEN_H * 2 * SCALE))
pygame.display.set_caption("py-melonds")
clock = pygame.time.Clock()

emu = MelonDSEmulator(
    rom_path=ROM_PATH,
    bios7_path=BIOS7_PATH,
    bios9_path=BIOS9_PATH,
    firmware_path=FIRMWARE_PATH,
    video_enabled=True,
    audio_enabled=False,
)

print("Running — close the window or press Escape to quit")
print("Controls: Arrow keys, X=A, Z=B, Enter=Start, Backspace=Select, A=L, S=R")
print("Touch screen: left click on bottom screen")

running = True
while running:
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

    keys = pygame.key.get_pressed()
    ds_keys = 0
    if keys[pygame.K_x]:         ds_keys |= 1
    if keys[pygame.K_z]:         ds_keys |= 2
    if keys[pygame.K_RETURN]:    ds_keys |= 8
    if keys[pygame.K_BACKSPACE]: ds_keys |= 4
    if keys[pygame.K_RIGHT]:     ds_keys |= 16
    if keys[pygame.K_LEFT]:      ds_keys |= 32
    if keys[pygame.K_UP]:        ds_keys |= 64
    if keys[pygame.K_DOWN]:      ds_keys |= 128
    if keys[pygame.K_s]:         ds_keys |= 256
    if keys[pygame.K_a]:         ds_keys |= 512

    emu.set_inputs(ds_keys)
    emu.run_single_frame()

    fb = lib.melonds_get_framebuffer(emu._handle)
    if fb != ffi.NULL:
        raw = bytes(ffi.buffer(fb, SCREEN_W * SCREEN_H * 2 * 4))
        surf = pygame.image.frombuffer(raw, (SCREEN_W, SCREEN_H * 2), 'BGRA')
        scaled = pygame.transform.scale(surf, (SCREEN_W * SCALE, SCREEN_H * 2 * SCALE))
        window.blit(scaled, (0, 0))
        pygame.display.flip()

    clock.tick(60)

pygame.quit()
print("Done")