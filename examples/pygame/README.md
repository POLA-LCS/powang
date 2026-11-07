## Pygame binding template

This directory is a starter project for using pygame with powang. Powang owns the
game logic and draw commands. Python owns the pygame window, clock and event loop.

### Layout

```text
examples/pygame/
  project.po
  game.po
  main.py
  lib/
    pygame.po
  pygame_host.py
```

### Run

```text
python main.py
```

`powang run` is not used here because the Python host owns the frame loop.

### project.po

```po
module project;

export project: Project = Project.[
    modules >> ["pygame_host"],
    paths >> ["."],
    logLevel >> "info"
];
```

### lib/pygame.po

```po
module pygame;

export extern fun init(): int >> "pygame_host.init";
export extern fun quit(): int >> "pygame_host.quit";
export extern fun set_mode(width: int, height: int): handle >> "pygame_host.set_mode";
export extern fun fill(screen: handle, r: int, g: int, b: int): int >> "pygame_host.fill";
export extern fun draw_rect(screen: handle, x: int, y: int, w: int, h: int, r: int, g: int, b: int): int >> "pygame_host.draw_rect";
export extern fun flip(screen: handle): int >> "pygame_host.flip";
export extern fun tick(clock: handle, fps: int): num >> "pygame_host.tick";
export extern fun make_clock(): handle >> "pygame_host.make_clock";
export extern fun event_quit(): bool >> "pygame_host.event_quit";
```

### pygame_host.py

```python
from __future__ import annotations

import pygame

_screens = {}
_images = {}
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


def draw_rect(screen_handle, x, y, w, h, r, g, b) -> int:
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
```

### game.po

```po
module game;

use ".\\lib\\pygame" as pygame;

fun commands(width: int, height: int): arr {
    return [
        ["clear", 0, 0, 0],
        ["rect", 10, 20, 30, 40, 255, 0, 0]
    ];
}
```

### main.py

```python
import pygame

from src.parser import Parser
from src.runtime import fresh_state, set_state, evaluateAstExpression
from src.scopestack import ScopeStack
from host_bridge import call_powang


def call_powang(name, *args):
    functions = ScopeStack.get_functions(name)
    if functions is None:
        raise RuntimeError(f"powang function not found: {name}")
    candidate = functions[0]
    # Call through your runtime helper when available.
    return candidate


source = open("game.po", encoding="utf-8").read()
state = fresh_state()
set_state(state)
for statement in Parser(source).parse():
    evaluateAstExpression(statement)

commands = call_powang("commands", 640, 480)
for command in commands:
    print(command)

pygame.quit()
```

## Notes

- Pygame stays in Python. Powang only sees handles and simple values.
- The LSP sees the `pygame` extern signatures from `lib/pygame.po`.
- Add more pygame operations by extending `pygame_host.py` and `lib/pygame.po`.
- For a full game, keep the frame loop in Python and let powang return draw commands.

If you want, I can make `main.py` fully runnable with a real pygame loop next.