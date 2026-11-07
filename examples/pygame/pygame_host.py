from __future__ import annotations

import pygame

_screens = {}
_clocks = {}


def init() -> int:
    pygame.init()
    return 1


def quit() -> int:
    pygame.quit()
    return 1


def set_mode(width: int, height: int) -> int:
    screen = pygame.display.set_mode((width, height))
    handle = len(_screens)
    _screens[handle] = screen
    return handle


def fill(screen_handle: int, r: int, g: int, b: int) -> int:
    screen = _screens[screen_handle]
    screen.fill((r, g, b))
    return 1


def draw_rect(screen_handle: int, x: int, y: int, w: int, h: int, r: int, g: int, b: int) -> int:
    screen = _screens[screen_handle]
    pygame.draw.rect(screen, (r, g, b), (x, y, w, h))
    return 1


def flip(screen_handle: int) -> int:
    pygame.display.flip()
    return 1


def make_clock() -> int:
    clock = pygame.time.Clock()
    handle = len(_clocks)
    _clocks[handle] = clock
    return handle


def tick(clock_handle: int, fps: int) -> float:
    clock = _clocks[clock_handle]
    return clock.tick(fps) / 1000.0


def event_quit() -> bool:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return True
    return False
