from ..lexing.token import Token
from typing import Callable

SKIP_CONDITION: list[Callable[[Token, list[Token]], bool]] = []
def get_skip_condition(x: Token, y: list[Token]):
    if SKIP_CONDITION:
        return SKIP_CONDITION[-1](x, y)
    else:
        return False

def pop_skip_condition():
    if SKIP_CONDITION:
        return SKIP_CONDITION.pop()