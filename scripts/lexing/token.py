from typing import Literal, Self
from enum import Enum, auto
from ..types import PowangAny

class TokenType(Enum):
    KEYWORD     = auto()
    BUILTIN = auto()
    IDENTIFIER  = auto()
    # ====== LITERALS =========
    NUMBER_LIT  = auto()
    STRING_LIT  = auto()
    LIST_LIT    = auto()
    BOOL_LIT    = auto()
    
    EXPRESSION  = auto()

    @staticmethod
    def to_str(type: 'TokenType'):
        return {
            TokenType.KEYWORD     : 'KEYWORD',
            TokenType.BUILTIN : 'BUILTIN',
            TokenType.IDENTIFIER  : 'IDENTIFIER',
            
            TokenType.NUMBER_LIT  : 'NUMBER LITERAL',
            TokenType.STRING_LIT  : 'STRING LITERAL',
            TokenType.LIST_LIT    : 'LIST LITERAL',
            TokenType.BOOL_LIT    : 'BOOL LITERAL',
            
            TokenType.EXPRESSION  : 'EXPRESSION',
        }.get(type, 'UNKNOWN TOKEN TYPE ???')
        
    @staticmethod
    def is_literal(type: 'TokenType') -> bool:
        return type in {
            TokenType.NUMBER_LIT,
            TokenType.STRING_LIT,
            TokenType.BOOL_LIT,
        }
        

# ====== THE NEXT TOKEN STRUCTURE IS TO MATCH THE TYPE CONSCISTENCY ========= #
class TokenBase:
    def __init__(self, type, value):
        self.type = type
        self.value = value
        
    def __repr__(self):
        return f'({TokenType.to_str(self.type)}: {self.value})'
        
class TokenNameValue(TokenBase):
    Types = Literal [
        TokenType.KEYWORD,
        TokenType.BUILTIN,
        TokenType.IDENTIFIER,
    ]
    type: Types
    value: str

    def __init__(self, type: Types, value: str):
        super().__init__(type, value)

# Tokens with list content
class TokenListValue(TokenBase):
    Types = Literal [
        TokenType.LIST_LIT,
        TokenType.EXPRESSION
    ]

    type: Types
    value: list['Token']

    def __init__(self, type: Types, value: list['Token']):
        super().__init__(type, value)

class TokenLiteralValue(TokenBase):
    Types = Literal [
        TokenType.NUMBER_LIT,
        TokenType.STRING_LIT,
        TokenType.BOOL_LIT,
    ]
    
    type: Types
    value: PowangAny
    
    def __init__(self, type: Types, value: PowangAny):
        super().__init__(type, value)

# Union Token type
Token = TokenLiteralValue | TokenNameValue | TokenListValue