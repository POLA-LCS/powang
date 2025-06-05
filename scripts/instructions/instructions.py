from typing import Callable
from ..types import PolangAny, PolangError

class Instruction:
    def __init__(self, min_argc: int, max_argc: int, is_flex: bool, function: Callable[(...), PolangAny | PolangError]):
        self.min_argc = min_argc
        self.max_argc = max_argc
        self.is_flex = is_flex
        self.function = function

from .output import *
from .input import *

INSTRUCTIONS: dict[str, Instruction] = {
    'stdout': Instruction(1, -1, True, inst_stdout),
    'print':  Instruction(1, 3, True, inst_print),
    'exit':   Instruction(1, 1, False, inst_exit),
    # 'stdin': (2, False, inst_stdin),
}

def keyword_if(*args):
    return PolangError(('IMPLEMENTATION', 'if keyword not implemented yet', []))

KEYWORDS: dict[str, Instruction] = {
    'if': Instruction(2, 2, True, keyword_if)
}