from typing import Self

class TokenType:
    KEYWORD    = 'keyword'
    NAME       = 'name'
    NUMBER_LIT = 'number'
    STRING_LIT = 'string'
    LIST_LIT   = 'list'
    EXPRESSION = 'expression'

class Token:
    def __init__(self, type: str, value: str | list[Self]):
        self.type = type
        self.value = value

    def __repr__(self) -> str:
        return f'({self.type}: {self.value})'