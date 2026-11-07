import os
import sys

REPO = os.environ.get("POWANG_REPO", r"C:\Users\zarap\Dev\Python\powang")
sys.path.insert(0, REPO)

import pygame

from src.parser import Parser
from src.runtime import fresh_state, set_state, evaluateAstExpression, callFunction
from src.scopestack import ScopeStack

source = open("game.po", encoding="utf-8").read()
state = fresh_state()
set_state(state)
for statement in Parser(source).parse():
    evaluateAstExpression(statement)


def call_powang(name, *args):
    functions = ScopeStack.get_functions(name)
    if functions is None:
        raise RuntimeError(f"powang function not found: {name}")
    candidate = functions[0]
    return callFunction("host", name, candidate, list(args))


pygame.init()
screen = pygame.display.set_mode((640, 480))
clock = pygame.time.Clock()
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    dt = clock.tick(60) / 1000.0
    _ = dt

    commands = call_powang("commands", screen.get_width(), screen.get_height())
    screen.fill((0, 0, 0))
    for command in commands:
        if command[0] == "rect":
            pygame.draw.rect(screen, (command[5], command[6], command[7]), (command[1], command[2], command[3], command[4]))

    pygame.display.flip()

pygame.quit()
