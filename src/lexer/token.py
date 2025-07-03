from typing import Optional, Any
from enum import Enum, auto

class TokenTypeBase(Enum):
    @staticmethod
    def toStr(token_type: 'TokenTypeBase'):
        if token_type.value not in token_type._value2member_map_:
            raise ValueError(f"Unknown token type: {token_type}")
        return ' '.join(word.lower() for word in token_type.name.split('_'))

class LexerTokenType(TokenTypeBase):
    # Literals
    NOVA_LITERAL     = auto() # nova
    BOOLEAN_LITERAL  = auto() # true or false
    INTEGER_LITERAL  = auto() # 69
    FLOATING_LITERAL = auto() # 3.141592
    STRING_LITERAL   = auto() # "hello"

    # Identifiers
    IDENTIFIER = auto()
    KEYWORD    = auto() # if, else, etc.

    # Operators
    OPERATOR_PLUS       = auto() # +
    OPERATOR_SUMATORY   = auto() # [+]
    OPERATOR_MINUS      = auto() # -
    OPERATOR_INVERSE    = auto() # [-]
    OPERATOR_CAST_AS    = auto() # as
    OPERATOR_ASSIGNMENT = auto() # =

    # Group punctuation
    LEFT_PARENTHESIS  = auto() # (
    RIGHT_PARENTHESIS = auto() # )
    LEFT_BRACKET      = auto() # [
    RIGHT_BRACKET     = auto() # ]
    LEFT_BRACE        = auto() # {
    RIGHT_BRACE       = auto() # }

    # Symbols
    ARROW       = auto() # =>
    EXCLAMATION = auto() # !
    ARROBA      = auto() # @
    STAR        = auto() # *
    SLASH       = auto() # /
    SEMI_COLON  = auto() # ;
    COLON       = auto() # :
    COMMA       = auto() # ,
    DOT         = auto() # .

    # Compare
    COMPARE_TYPED_EQ  = auto() # ==:
    COMPARE_TYPED_NEQ = auto() # !=:
    COMPARE_TYPED_LEQ = auto() # <=:
    COMPARE_TYPED_GEQ = auto() # >=:
    COMPARE_TYPED_LSS = auto() # <:
    COMPARE_TYPED_GTR = auto() # >:
    COMPARE_EQ        = auto() # ==
    COMPARE_NEQ       = auto() # !=
    COMPARE_GEQ       = auto() # <=
    COMPARE_LEQ       = auto() # >=
    COMPARE_LSS       = auto() # <
    COMPARE_GTR       = auto() # >
    COMPARE_EQ_TYPE   = auto() # ::
    COMPARE_NEQ_TYPE  = auto() # !:

    AND  = auto() # &&
    OR = auto() # ||

    # Extra
    END_OF_FILE = auto()

class ParserTokenType(TokenTypeBase):
    PROGRAM               = auto()
    UNARY_EXPRESSION      = auto()
    BINARY_EXPRESSION     = auto()
    ARRAY_EXPRESSION      = auto()
    INDEX_EXPRESSION      = auto()
    CALL_EXPRESSION       = auto()
    BLOCK_STATEMENT       = auto()
    TYPE                  = auto()
    WEAK_TYPE             = auto()
    PAIR_TYPE_IDENTIFIER  = auto()
    DECLARATION_TYPED_VAR = auto()
    DECLARATION_INTERPRET = auto()
    DECLARATION_UNDEFINED = auto()
    DECLARATION_FUN       = auto()
    ASSIGNMENT            = auto()
    ACCESS_EXPRESSION     = auto()
    KEY_VALUE_PAIR        = auto()
    IF_STATEMENT          = auto()
    FOR_STATEMENT         = auto()
    FOR_EACH_STATEMENT    = auto()

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