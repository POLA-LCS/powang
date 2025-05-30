from .value import *
from typing import Callable
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
    'nice': Value(69.0, True),
    'newl': Value('\n', False)
}

# ====== INSTRUCTIONS =========
InstType = tuple[int, Callable]

def inst_stdout(*tokens: Token) -> int:
    """### RECURSIVE """
    # TYPE CHECK ASSERT
    if len(tokens) == 0:
        return 0

    for tk in tokens:
        # NAME
        if tk.type == TokenType.NAME:
            assert (value := MEMORY.get(tk.value)) is not None, ERROR_FORMAT_NAME(STACK[-1], tk.value) # type: ignore
            print(value.value, end='')
        # LIST LITERAL
        elif tk.type == TokenType.LIST_LIT:
            print('[', end='')
            i = 0
            while i < len(tk.value) - 1:
                inst_stdout(tk.value[i], Token(TokenType.STRING_LIT, ' ')) # type: ignore
                i += 1
            inst_stdout(tk.value[i]) # type: ignore
            print(']', end='')
        # LIST_LIT LITERAL
        elif tk.type == TokenType.EXPRESSION:
            print('(...)', end='')
        else:
            print(tk.value, end='')
    return len(tokens)

def inst_print(
        values: Token,
        sep = Token(TokenType.STRING_LIT, ' '),
        end = Token(TokenType.NAME, 'newl')
    ):

    #                     TYPE CHECK RELAX | vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
    assert values.type == TokenType.LIST_LIT and isinstance(values.value, list), ERROR_FORMAT_ARGV(
        STACK[-1], 'print', TokenType.LIST_LIT, str(values)
    )

    length = len(values.value)
    i = 1
    while i < length + length - 1:
        values.value.insert(i, sep)
        i += 2

    return inst_stdout(*values.value, end)

INSTRUCTIONS: dict[str, InstType] = {
    'stdout': (-1, inst_stdout),
    'print': (3, inst_print)
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