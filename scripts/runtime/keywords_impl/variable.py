from ...lexing.token import Token, TokenType
from ...interpret import process_values, interpret_expression
from ...types.native import PowangList, PowangAny
from .control import keyword_end
from ...error import *
from ...types import PowangCopyConstruct

VARIABLE_EXPRESSION = 'variable expression'

def get_spread_names_value(names: Token, values: Token) -> tuple[list[str], list[PowangAny]]:
    if values.type == TokenType.EXPRESSION:
        result: PowangAny = interpret_expression(MEMORY.indent_depth, values.value)
    else:
        result: PowangAny = process_values(MEMORY.indent_depth, [values])[0]
    
    spread_names : list[str]       = []
    spread_values: list[PowangAny] = []
    
    # Common variable definition
    if names.type == TokenType.IDENTIFIER:
        return ([names.value], [result])
    
    # Spread variable definition
    if names.type == TokenType.EXPRESSION:
        assert result.type == PowangList.type, error_spread_value(result.type)
        spread_values = result.data
        
        for i, spread_name in enumerate(names.value):
            assert spread_name.type == TokenType.IDENTIFIER, error_spread_expression(i, result.type)
            spread_names.append(spread_name.value)
    return (spread_names, spread_values)
    
def keyword_var(
        var_name : Token,
        var_value: Token,
        var_const: bool = False,
    ):

    spread_names, spread_values = get_spread_names_value(var_name, var_value)
    assert len(spread_names) == len(spread_values), error_syntax(
        "invalid spread expression", [
            "spread variable names and values must have a 1:1 matching",
            f"but {len(spread_names)} names and {len(spread_values)} values were provided."
        ]
    )

    for name, value in zip(spread_names, spread_values):
        powang_result = PowangCopyConstruct(value)
        powang_result.const = var_const
        MEMORY.set_memory(name, powang_result, MEMORY.peek_scope().name)

    return PowangList(spread_values) if len(spread_values) > 1 else spread_values[0]

def keyword_def(var_name: Token, value: Token):
    return keyword_var(var_name, value, True)

def keyword_set(var_name: Token, var_value: Token):
    assert var_name.type == TokenType.IDENTIFIER, error_syntax(
        "bad token", [
            f"expected {TokenType.to_str(TokenType.IDENTIFIER)}",
            f"but {var_name.type} was provided"
        ]
    )

    spread_names, spread_values = get_spread_names_value(var_name, var_value)
    assert len(spread_names) == len(spread_values), error_syntax(
        "invalid spread expression", [
            "spread variable names and values must have a 1:1 matching",
            f"but {len(spread_names)} names and {len(spread_values)} values were provided."
        ]
    )

    for name, value in zip(spread_names, spread_values):
        assert (powang_variable := MEMORY.get_memory(name)) is not None, error_identifier_not_found(
            var_name.value, False
        )

        scope, value = powang_variable

        assert value.type == value.type, error_type(
            value.type, value.type
        )
        
        assert not value.const, error_constant_assign([
            f"const -> {var_name.value}"
        ])

        MEMORY.set_memory(var_name.value, value, scope.name)
    return PowangList(spread_values) if len(spread_values) > 1 else spread_values[0]