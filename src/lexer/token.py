from typing import Optional, Any
from enum import Enum, auto

class TokenTypeBase(Enum):
    @staticmethod
    def toStr(token_type: 'TokenTypeBase'):
        if token_type.value not in token_type._value2member_map_:
            raise ValueError(f"Unknown token type: {token_type}")
        return ' '.join(word.upper() for word in token_type.name.split('_'))

class LexerTokenType(TokenTypeBase):
    # Literals
    NOVA_LITERAL       = auto() # nova
    BOOLEAN_LITERAL    = auto() # true or false
    INTEGER_LITERAL    = auto() # 69
    FLOATING_LITERAL   = auto() # 3.141592
    STRING_LITERAL     = auto() # 'hello'
    FMT_STRING_LITERAL = auto() # "hello ${12 + 23 + 34}"

    # Identifiers
    IDENTIFIER         = auto()
    KEYWORD            = auto()  # var, if, else, etc.

    # Operators
    OPERATOR_ADDITION       = auto()  # + OR -
    OPERATOR_MULTIPLICATION = auto()  # * OR /
    OPERATOR_ASSIGNMENT     = auto()  # =

    # Group punctuation
    EXCLAMATION       = auto() # !
    WEAK_PREFIX       = auto() # @
    LEFT_PARENTHESIS  = auto() # (
    RIGHT_PARENTHESIS = auto() # )
    LEFT_BRACKET      = auto() # [
    RIGHT_BRACKET     = auto() # ]
    LEFT_BRACE        = auto() # {
    RIGHT_BRACE       = auto() # }

    # Separators
    SEMI_COLON = auto() # ;
    COLON      = auto() # :
    COMMA      = auto() # ,
    DOT        = auto() # .

    # Extra
    END_OF_FILE = auto()

class ParserTokenType(TokenTypeBase):
    PROGRAM               = auto()
    BINARY_EXPRESSION     = auto()
    LIST_EXPRESSION       = auto()
    CALL_EXPRESSION       = auto()
    BLOCK_STATEMENT       = auto()
    TYPE                  = auto()
    WEAK_TYPE             = auto()
    PAIR_TYPE_IDENTIFIER  = auto()
    DECLARATION_TYPED_VAR = auto()
    DECLARATION_INTERPRET = auto()
    DECLARATION_UNDEFINED = auto()
    ASSIGNMENT            = auto()

def TokenToString(token: TokenTypeBase):
    if isinstance(token, LexerTokenType):
        return LexerTokenType.toStr(token)
    return ParserTokenType.toStr(token)

TokenType = LexerTokenType | ParserTokenType
DictRepr = dict[str | TokenType, Any]

class TokenBase:
    def __init__(self, type: TokenTypeBase, value):
        self.type = type
        self.value = value
        
    def __repr__(self):
        return f'({self.type.toStr(self.type)}: {self.value})'
    
    def toDict(self, value: Optional[Any] = None) -> DictRepr:
        return {
            "type": self.type,
            "value": self.value if value is None else value
        }
    
class LexerToken(TokenBase):
    type: LexerTokenType
    value: str

    def __init__(self, type: LexerTokenType, value: Optional[str]):
        super().__init__(type, value)
        
class ParserToken(TokenBase):
    type: ParserTokenType
    value: DictRepr

    def __init__(self, type: ParserTokenType, value: DictRepr):
        super().__init__(type, value)

# Union Token type
TokenType = LexerTokenType | ParserTokenType

def doToken(token_type: LexerTokenType | ParserTokenType, value: Any):
    if isinstance(token_type, LexerTokenType):
        return LexerToken(LexerTokenType(token_type), value) # type: ignore
    elif isinstance(token_type, ParserTokenType):
        return ParserToken(ParserTokenType(token_type), value) # type: ignore