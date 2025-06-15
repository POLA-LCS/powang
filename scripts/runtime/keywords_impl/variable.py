from ...lexing.token import Token, TokenType
from ...interpret import process_values, interpret_line
from ...types.native import PowangList, PowangAny
from ...error import *
from ...types import PowangCopyConstruct

def keyword_var(
        name: Token,
        value: Token,
        const: bool = False,
    ):
    
    spread_values: PowangList = PowangList([])
    spread_names: list[str] = []
    
    if name.type != TokenType.EXPRESSION:
        assert name.type == TokenType.IDENTIFIER, error_syntax(
            "bad token", [
                f"expected {TokenType.to_str(TokenType.IDENTIFIER)} or {TokenType.to_str(TokenType.EXPRESSION)}",
                f"but {name.type} was provided"
            ]
        )
        
        spread_names = [name.value]
        
        if value.type == TokenType.EXPRESSION:
            result = interpret_line(SCOPE.depth, value.value)
        else:
            result = process_values(SCOPE.depth, [value])[0]
            
        spread_values.data = [result]
        
    else:
        for i, token in enumerate(name.value):
            assert token.type == TokenType.IDENTIFIER, error_syntax(
                "bad token", [
                    f"expected token {i} to be a {TokenType.to_str(TokenType.IDENTIFIER)}",
                    f"but {name.type} was provided"
                ]
            )
            spread_names.append(token.value)
        
        if value.type == TokenType.EXPRESSION:
            spread_values.data = [interpret_line(SCOPE.depth, value.value)]
        elif value.type == TokenType.IDENTIFIER:
            assert (result := SCOPE.get_memory(value.value)) is not None, error_identifier_not_found(
                value.value, False
            )
            
            scope, list_value = result
            
            assert list_value.type == PowangList.type, error_syntax(
                "invalid spread type", [
                    f"spreading expression expected type {PowangList.type}",
                    f"but {list_value.type} was provided",
                ]
            )
            
            spread_values.data = list_value.data
        else:
            assert value.type == TokenType.LIST_LIT, error_syntax(
                "bad token", [
                    f"spreading expression expected {TokenType.to_str(TokenType.LIST_LIT)}",
                    f"but {TokenType.to_str(value.type)} was provided",
                ]
            )
            
            spread_values.data = process_values(SCOPE.depth, value.value)   
        assert (name_len := len(spread_names)) == (value_len := len(spread_values.data)), error_syntax(
            "not enough values to spread", [
                f"expected {name_len} values",
                f"but {value_len} was provided.",
            ]
        )

    for sp_name, sp_value in zip(spread_names, spread_values.data):
        if (existing := SCOPE.get_memory(sp_name)) is not None:
            _, existing_value = existing
            assert existing_value.type == sp_value.type, error_type(
                existing_value.type, sp_value.type
            )

        powang_result = PowangCopyConstruct(sp_value)
        powang_result.const = const

        SCOPE.set_memory(sp_name, powang_result, SCOPE.peek_name()[0])

    return spread_values if len(spread_values.data) > 1 else spread_values.data[0]

def keyword_def(name: Token, value: Token):
    return keyword_var(name, value, True)

def keyword_set(name: Token, value: Token):
    assert name.type == TokenType.IDENTIFIER, error_syntax(
        "bad token", [
            f"expected {TokenType.to_str(TokenType.IDENTIFIER)}",
            f"but {name.type} was provided"
        ]
    )

    if value.type == TokenType.EXPRESSION:
        result = interpret_line(SCOPE.depth, value.value)
    else:
        result = process_values(SCOPE.depth, [value])[0]

    assert (existing := SCOPE.get_memory(name.value)) is not None, error_identifier_not_found(
        name.value, False
    )

    existing_scope, existing_value = existing

    assert existing_value.type == result.type, error_type(
        existing_value.type, result.type
    )
    
    assert not existing_value.const, error_constant_assign([
        f"const -> {name.value}"
    ])

    SCOPE.set_memory(name.value, result, existing_scope[0])
    return result