from ..lexing.token import Token
from typing import Callable

EXTERNAL_CONDITION: list[Callable[[int, Token], bool]] = []
ACTUAL_LINE: list[int] = [0]