from .value import *
from types import FunctionType
from .lexer import INSTRUCTIONS_SET, Token, TokenType
from .errors import *

# Flags
WARNING_ENABLE: bool = False
ERRORS_AT_EXIT: bool = False
STRICT_ASSERTS: bool = False

ERRORS_LIST: list[str] = []

# Exit
EXIT_CODE  : int       = 0
RUNNING    : bool      = True

STACK = ['global'] # TODO

MEMORY: dict[str, Value] = {
    'nice': Value(69, True)
}

# ====== INSTRUCTIONS =========
InstType = tuple[int, FunctionType]

def inst_out(*args: Token):
    for tk in args:
        if tk.type == TokenType.KEYWORD:
            if tk.value == 'out':
                print()
        elif tk.type == TokenType.NAME:
            assert (value := MEMORY.get(tk.value)) is not None, ERROR_FORMAT_NAME(STACK[-1] + ' out', tk.value) # type: ignore
            print(value.value, end='')
        elif tk.type == TokenType.LIST_LIT:
            print('[', end='')
            for i, item in enumerate(tk.value):
                inst_out(item) # type: ignore
                if i + 1 < len(tk.value):
                    print(' ', end='')
            print(']', end='')
        else:
            print(tk.value, end='')

INSTRUCTIONS: dict[str, InstType] = {
    'stdout': (-1, inst_out) # type: ignore
}

# DEVELOP ASSERT
if any([inst not in INSTRUCTIONS for inst in INSTRUCTIONS_SET]):
    print(
        ERROR_FORMAT_LOGIC(
            'development',
            "forgotten inst implementation",
            f"inst -> {sorted(INSTRUCTIONS_SET)}\n    impl -> {[key for key in sorted(INSTRUCTIONS.keys())]}"
        )
    )
    exit(69)