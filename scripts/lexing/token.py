from typing import Literal
from enum import Enum

class TokenType(Enum):
    KEYWORD    = 'keyword'
    NAME       = 'name'
    NUMBER_LIT = 'number'
    STRING_LIT = 'string'
    LIST_LIT   = 'list'
    EXPRESSION = 'expression'

    @staticmethod
    def str(type: 'TokenType'):
        return {
            TokenType.KEYWORD    : 'KEYWORD',
            TokenType.NAME       : 'NAME',
            TokenType.NUMBER_LIT : 'LIT NUMBER',
            TokenType.STRING_LIT : 'LIT STRING',
            TokenType.LIST_LIT   : 'LIT LIST',
            TokenType.EXPRESSION : 'EXPRESSION',
        }[type]

# ====== THE NEXT TOKEN STRUCTURE IS TO MATCH THE TYPE CONSCISTENCY ========= #
class TokenStrValue:
    Types = Literal [
        TokenType.KEYWORD,
        TokenType.NAME,
        TokenType.NUMBER_LIT,
        TokenType.STRING_LIT
    ]
    type: Types
    value: str

    def __init__(self, type: Types, value: str):
        self.type = type
        self.value = value

    def __repr__(self):
        return f'({TokenType.str(self.type)}: {self.value})'

# Tokens with list content
class TokenListValue:
    Types = Literal [
        TokenType.LIST_LIT,
        TokenType.EXPRESSION
    ]

    type: Types
    value: list['Token']

    def __init__(self, type: Types, value: list['Token']):
        self.type = type
        self.value = value

    def __repr__(self):
        return f'({TokenType.str(self.type)}: {self.value})'

# Union Token type
Token = TokenListValue | TokenStrValue