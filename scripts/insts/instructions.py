from typing import Callable

#                       argc, flex, function
InstructionType = tuple[int , bool, Callable]

from .output import *

INSTRUCTIONS: dict[str, InstructionType] = {
    'stdout': (-1, True, inst_stdout),
    'print': (3, True, inst_print)
}