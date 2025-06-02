from ..lexing.token import Token, TokenType, TokenStrValue
from ..errors import error_arguments, error_name
from ..runtime.memory import get_memory, STACK
from ..circular.instructions import circular_get_inst

def inst_stdout(*tokens: Token) -> int:
    """### RECURSIVE """
    if len(tokens) == 0:
        print()
        return 0

    for tk in tokens:
        # ====== NAME
        if tk.type == TokenType.NAME:
            assert (value := get_memory(tk.value)) is not None, error_name(STACK[-1], tk.value)
            print(value.value, end='')
        # ====== LIST LITERAL
        elif tk.type == TokenType.LIST_LIT:
            print('[', end='')
            if len(tk.value) != 0:
                i = 0
                for i in range(len(tk.value) - 1):
                    inst_stdout(tk.value[i], TokenStrValue(TokenType.STRING_LIT, ' '))
                inst_stdout(tk.value[i])
            print(']', end='')
        # ====== LIST_LIT LITERAL
        elif tk.type == TokenType.EXPRESSION:
            print(f'({tk.value})', end='')
        elif tk.type == TokenType.KEYWORD:
            argc, flex, func = circular_get_inst(tk.value)
            print(f'<inst {tk.value}({argc if argc > -1 else '...'}){f' FLEX' if flex else ''}>', end='')
        else:
            print(tk.value, end='')
    return len(tokens)

def inst_print(
    
        values: Token,
        sep = TokenStrValue(TokenType.STRING_LIT, ' '),
        end = TokenStrValue(TokenType.NAME, 'newl')
    ):
    """### PARENT"""

    assert values.type == TokenType.LIST_LIT, error_arguments(
        STACK[-1], 'print', str(TokenType.LIST_LIT), str(values)
    )

    length = len(values.value)
    i = 1
    while i < length + length - 1:
        values.value.insert(i, sep)
        i += 2

    return inst_stdout(*values.value, end)