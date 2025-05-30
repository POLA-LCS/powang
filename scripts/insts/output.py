from ..lexing.token import Token, TokenType
from ..errors import error_format_ARGV, error_format_name
from ..runtime.memory import get_memory, STACK

def inst_stdout(*tokens: Token) -> int:
    """### RECURSIVE """
    # TYPE CHECK ASSERT
    if len(tokens) == 0:
        return 0

    for tk in tokens:
        # NAME
        if tk.type == TokenType.NAME:
            assert (value := get_memory(tk.value)) is not None, error_format_name(STACK[-1], tk.value) # type: ignore
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
    assert values.type == TokenType.LIST_LIT and isinstance(values.value, list), error_format_ARGV(
        STACK[-1], 'print', TokenType.LIST_LIT, str(values)
    )

    length = len(values.value)
    i = 1
    while i < length + length - 1:
        values.value.insert(i, sep)
        i += 2

    return inst_stdout(*values.value, end)