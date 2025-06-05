from ...types import *
from ...lexing.token import *
from ...error import *
from ...circular import circular_interpret_line, circular_process_value
from ...memory import *

def keyword_var(name: Token, value: Token):
    assert name.type == TokenType.IDENTIFIER, error_syntax(
        "bad token", [
            "expecting an identifier",
            f"but {name.type} was provided"
    ])

    if value.type == TokenType.EXPRESSION:
        result_value = circular_interpret_line(value.value)
    else:
        result_value = circular_process_value([value])[0]

    if (variable := get_memory(name.value)) is None:
        set_memory(name.value, result_value)
    else:
        assert variable.type == result_value.type, error_type(
            variable.type, result_value.type
        )
        
        set_memory(name.value, result_value)
    return result_value

def keyword_del(name: Token):
    assert name.type == TokenType.IDENTIFIER, error_syntax(
        "bad token", [
            "expecting an identifier",
            f"but {name.type} was provided."
    ])

    assert get_memory(name.value), error_identifier_not_found(
        name.value, False
    )
    
    return MEMORY[get_scope_name()].pop(name.value)