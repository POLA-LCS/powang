from .types import *
from .lexing.token import *
from .error import *
from .memory import *
from .circular import *
from .runtime import *

FLAG_WARNING : bool = False
FLAG_FLEX    : bool = False
FLAG_DISCREET: bool = False

ERRORS_LIST: list[str] = []

EXIT_CODE  : int       = 0

def process_values(rest: list[Token]) -> list[PowangAny]:
    """### RECURSIVE CHILD"""
    value_list: list[PowangAny] = []
    for tk in rest:
        if tk.type == TokenType.NUMBER_LIT or tk.type == TokenType.STRING_LIT:
            value_list.append(tk.value)
        elif tk.type == TokenType.LIST_LIT:
            value_list.append(
                PowangList(process_values(tk.value), const=False)
            )
        elif tk.type == TokenType.IDENTIFIER:
            assert (value := get_memory(tk.value)) is not None, error_identifier_not_found(
                tk.value, False
            )
            value_list.append(value)
        elif tk.type == TokenType.EXPRESSION:
            value_list.append(interpret_line(tk.value))
        elif tk.type == TokenType.INSTRUCTION:
            value_list.append(PowangString(f'<powang {tk.value}>'))

    return value_list

def interpret_line(sentence: list[Token]) -> PowangAny:
    """### RECURSIVE"""
    #print(sentence, '\n')

    domain, rest = sentence[0], sentence[1:]

    if get_skip_condition(domain, rest):
        return PowangNov()
    else:
        pop_skip_condition()

    assert \
        domain.type == TokenType.KEYWORD     or \
        domain.type == TokenType.INSTRUCTION or \
        domain.type == TokenType.IDENTIFIER,    \
        error_syntax(
        "bad token", [
            f"expecting keyword, instruction or macro",
            f"{domain.type} was recieved"
    ])

    powang_callable = get_powang_callable(domain.value)
    assert powang_callable is not None, error_identifier_not_found(
        domain.value, True
    )

    if domain.type == TokenType.INSTRUCTION or domain.type == TokenType.IDENTIFIER:
        arguments = process_values(rest)
        assert len(arguments) >= powang_callable.min_argc, \
            error_argc(
                powang_callable.min_argc,
                len(arguments
        ))
            
        assert len(arguments) <= powang_callable.max_argc or powang_callable.max_argc == -1, \
            error_argc(
                powang_callable.max_argc,
                len(arguments
        ))
        result = powang_callable.function(*arguments)
    else: # HERE powang_callable is a KEYWORD
        result = powang_callable.function(*rest)

    if result.type == 'error':
        assert powang_callable.is_flex and FLAG_FLEX, result.data
        ERRORS_LIST.append(error_format(*result.data))
        return PowangNov()
    else:
        return result

def interpret_program(token_program: list[list[Token]]):
    global EXIT_CODE
    for ln, sentence in enumerate(token_program):
        if len(SCOPE_STACK) == 0:
            return
        if len(sentence) == 0: # IGNORE EMPTY LINES
            continue

        try:
            return_value = interpret_line(sentence)
            if return_value.type == 'number':
                EXIT_CODE = int(return_value.data)
        except AssertionError as ass:
            raise_error(error_with_line(ln, *ass.args))