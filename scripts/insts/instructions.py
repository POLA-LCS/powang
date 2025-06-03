from typing import Callable
from ..runtime.types import PolangAny, PolangError
#                       argc, flex, function
InstructionType = tuple[int,  bool, Callable[(...), PolangAny | PolangError]]

from .output import *
from .input import *

from icecream import ic

INSTRUCTIONS: dict[str, InstructionType] = {
    'stdout': (-1, True, inst_stdout),
    'print': (3, True, inst_print),
    # 'stdin': (2, False, inst_stdin),
}