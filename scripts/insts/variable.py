from ..lexing.token import *
from ..runtime import Value, STACK, MEMORY, get_memory
from ..errors import error_arguments, error_name

def inst_var(var_name: Token, right_value: Token):
    assert var_name.type == TokenType.NAME, error_arguments(
        STACK[-1],
        'var',
        TokenType.str(TokenType.NAME),
        TokenType.str(var_name.type)
    )
    
    if right_value.type == TokenType.NAME:
        assert (value := get_memory(right_value.value)) is not None, error_name(
            STACK[-1],
            right_value.value
        )
    else:
        value = Value(right_value.value, False)
        MEMORY.setdefault(STACK[-1], {})[var_name.value] = value
        
def inst_scope(scope_name: Token):
    assert scope_name.type == TokenType.NAME, error_arguments(
        STACK[-1],
        'scope',
        TokenType.str(TokenType.NAME),
        TokenType.str(scope_name.type)
    )
    
    STACK.append(scope_name.value)