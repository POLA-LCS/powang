from .value import *
from types import FunctionType

# Flags
WARNING_ENABLE: bool = False
ERRORS_AT_EXIT: bool = False
STRICT_ASSERTS: bool = False

ERRORS_LIST: list[str] = []

# Exit
EXIT_CODE  : int       = 0
RUNNING    : bool      = True

STACK = [] # TODO

MEMORY: dict[str, Value] = {
    'nice': Value(69, True)
}

# ====== INSTRUCTIONS =========
InstType = tuple[int, FunctionType]

instructions: dict[str, InstType] = {}