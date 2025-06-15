from .types import *
from .lexing.token import *
from .error import *
from .memory import *
from .circular import *
from .runtime import *
from .runtime.external_condition import EXTERNAL_CONDITION, ACTUAL_LINE

FLAG_WARNING : bool = False
FLAG_FLEX    : bool = False
FLAG_DISCREET: bool = False

def set_flag_flex_true():
    global FLAG_FLEX
    FLAG_FLEX = True

ERRORS_LIST: list[str] = []

EXIT_CODE  : int       = 0

def list_expression(tokens: list[Token]):
    return tokens

def process_values(indent: int, rest: list[Token]) -> list[PowangAny]:
    """### RECURSIVE"""
    value_list: list[PowangAny] = []
    for tk in rest:
        if \
            tk.type == TokenType.NUMBER_LIT or \
            tk.type == TokenType.STRING_LIT or \
            tk.type == TokenType.BOOL_LIT:
            value_list.append(tk.value)
        elif tk.type == TokenType.LIST_LIT:
            #print('[DEBUG]', tk.value)
            value_list.append(
                PowangList(process_values(indent, tk.value))
            )
        elif tk.type == TokenType.IDENTIFIER:
            assert (value := SCOPE.get_memory(tk.value)) is not None, error_identifier_not_found(
                tk.value, False
            )
            _, powang_value = value
            value_list.append(powang_value)
        elif tk.type == TokenType.EXPRESSION:
            value_list.append(interpret_line(indent, tk.value))

    return value_list

def interpret_line(indent: int, sentence: list[Token]) -> PowangAny:
    """### RECURSIVE"""

    domain, rest = sentence[0], sentence[1:]

    #print('[DEBUG]', indent, SCOPE.peek_name())

    if EXTERNAL_CONDITION:
        condition = EXTERNAL_CONDITION[-1](indent, domain)
        if condition:
            return PowangNov()
        else:
            EXTERNAL_CONDITION.pop()

    assert \
        domain.type == TokenType.KEYWORD     or \
        domain.type == TokenType.BUILTIN or \
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

    min_argc, max_argc, is_flex, function = powang_callable

    if domain.type == TokenType.BUILTIN or domain.type == TokenType.IDENTIFIER:
        rest = process_values(indent, rest)
        assert len(rest) >= min_argc, \
            error_argc(
                min_argc,
                len(rest
        ))
            
        assert len(rest) <= max_argc or max_argc == -1, \
            error_argc(
                max_argc,
                len(rest)
            )
    
    try:
        result = function(*rest)
        assert result.type != 'error', error_format(*result.data)
    except AssertionError as ass: # reached by FLEX instructions
        assert is_flex and FLAG_FLEX, ass
        ERRORS_LIST.append(*ass.args)
        return PowangNov()
    return result

def interpret_program(token_program: list[tuple[int, list[Token]]]):
    global EXIT_CODE
    global ACTUAL_LINE
    while ACTUAL_LINE[0] < len(token_program):
        sentence = token_program[ACTUAL_LINE[0]]
        
        if SCOPE.depth < 0:
            return

        indent, token_list = sentence

        ACTUAL_LINE[0] += 1
        
        if len(token_list) == 0: # IGNORE EMPTY LINES
            continue

        try:
            return_value = interpret_line(indent, token_list)
            if return_value.type == 'number':
                EXIT_CODE = int(return_value.data)
        except AssertionError as ass:
            raise_error(error_with_line(ACTUAL_LINE[0] - 1, *ass.args))
