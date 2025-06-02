from typing import Callable
#                       argc, flex, function
InstructionType = tuple[int , bool, Callable]

from .output import *
from .input import *
from .variable import *

from ..runtime import Value, MEMORY

INSTRUCTIONS: dict[str, InstructionType] = {
    'stdout': (-1, True, inst_stdout),
    'print': (3, True, inst_print),
    #'stdin': (2, False, inst_stdin),
    
    'var': (2, False, inst_var),
    'scope': (1, False, inst_scope),
    
    'print_memory': (0, False, lambda: print(MEMORY)),
    'new'
    'number': (1, False, float),
    'string': (1, False, str),
    'list': (1, False, list)
}