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
    INTERPOLATED_STRING_LITERAL = auto() # $"hello {name}"

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

    OPERATOR_ASSIGNMENT_PLUS  = auto() # +=
    OPERATOR_ASSIGNMENT_MINUS = auto() # -=
    OPERATOR_ASSIGNMENT_STAR  = auto() # *=
    OPERATOR_ASSIGNMENT_SLASH = auto() # /=

    # Group punctuation
    LEFT_PARENTHESIS  = auto() # (
    RIGHT_PARENTHESIS = auto() # )
    LEFT_BRACKET      = auto() # [
    RIGHT_BRACKET     = auto() # ]
    LEFT_BRACE        = auto() # {
    RIGHT_BRACE       = auto() # }

    # Symbols
    RIGHT_ARROW       = auto() # >>
    EXCLAMATION = auto() # !
    ARROBA      = auto() # @
    STAR        = auto() # *
    SLASH       = auto() # /
    PERCENT     = auto() # %
    SEMI_COLON  = auto() # ;
    COLON       = auto() # :
    COMMA       = auto() # ,
    DOT         = auto() # .
    ELLIPSIS    = auto() # ...
    QUESTION_MARK = auto() # ?
    SAFE_ACCESS = auto() # ?.
    COALESCE    = auto() # ??

    # Compare
    COMPARE_EQ        = auto() # ==
    COMPARE_NEQ       = auto() # !=
    COMPARE_LEQ       = auto() # <=
    COMPARE_GEQ       = auto() # >=
    COMPARE_LSS       = auto() # <
    COMPARE_GTR       = auto() # >
    COMPARE_EQ_TYPE   = auto() # ::
    COMPARE_NEQ_TYPE  = auto() # !:

    AND  = auto() # &&
    AMPERSAND = auto() # &
    OR = auto() # ||
    PIPE = auto() # |
    REFERENCE_PIPELINE = auto() # &>
    PIPELINE = auto() # :>

    # Extra
    END_OF_FILE = auto()

class ParserTokenType(TokenTypeBase):
    PROGRAM                 = auto()
    UNARY_EXPRESSION        = auto()
    BINARY_EXPRESSION       = auto()
    ARRAY_EXPRESSION        = auto()
    INDEX_EXPRESSION        = auto()
    CALL_EXPRESSION         = auto()
    BLOCK_STATEMENT         = auto()
    TYPE                    = auto()
    TYPE_REFERENCE          = auto()
    WEAK_TYPE               = auto()
    PAIR_TYPE_IDENTIFIER    = auto()
    DECLARATION_TYPED_VAR   = auto()
    DECLARATION_INTERPRET   = auto()
    DECLARATION_UNDEFINED   = auto()
    DECLARATION_FUN         = auto()
    ASSIGNMENT              = auto()
    ACCESS_EXPRESSION       = auto()
    METHOD_CALL             = auto()
    FAKE_METHOD_CALL        = auto()
    KEY_VALUE_PAIR          = auto()
    IF_STATEMENT            = auto()
    TRY_STATEMENT           = auto()
    FOR_STATEMENT           = auto()
    FOR_EACH_STATEMENT      = auto()
    RETURN_EXPRESSION       = auto()
    POSTFIX_UNWRAP          = auto()
    TYPE_ALIAS              = auto()
    TYPE_DECLARATION        = auto()
    USE_EXPRESSION          = auto()
    EXTERN_REFERENCE         = auto()
    SPAWN_EXPRESSION         = auto()
    TUPLE_EXPRESSION          = auto()
    REFERENCE_EXPRESSION     = auto()
    INTERPOLATED_STRING      = auto()
    MATCH_STATEMENT          = auto()
    MATCH_EXPRESSION         = auto()
    DESTRUCTURE_DECLARATION  = auto()
    DESTRUCTURE_PATTERN      = auto()
    RANGE_STATEMENT          = auto()
    SAFE_ACCESS_EXPRESSION   = auto()
    COALESCE_EXPRESSION      = auto()
    NAMED_ARGUMENT           = auto()
    PIPELINE_EXPRESSION      = auto()
    CONST_DECLARATION        = auto()
    MODULE_DECLARATION       = auto()
    INSTANTIATION            = auto()

def TokenToString(token: TokenTypeBase):
    if isinstance(token, LexerTokenType):
        return LexerTokenType.toStr(token)
    return ParserTokenType.toStr(token)

TokenType = LexerTokenType | ParserTokenType
DictRepr = dict[str | TokenType, Any]

class TokenBase:
    def __init__(self, type: TokenTypeBase, value, line: Optional[int] = None,
                 column: Optional[int] = None):
        self.type = type
        self.value = value
        self.line = line
        self.column = column
        
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

    def __init__(self, type: LexerTokenType, value: Optional[str],
                 line: Optional[int] = None, column: Optional[int] = None):
        super().__init__(type, value, line, column)
        
class ParserToken(TokenBase):
    type: ParserTokenType
    value: DictRepr

    def __init__(self, type: ParserTokenType, value: DictRepr):
        super().__init__(type, value)

def doToken(token_type: LexerTokenType | ParserTokenType, value: Any,
            line: Optional[int] = None, column: Optional[int] = None):
    if isinstance(token_type, LexerTokenType):
        return LexerToken(LexerTokenType(token_type), value, line, column) # type: ignore
    elif isinstance(token_type, ParserTokenType):
        return ParserToken(ParserTokenType(token_type), value) # type: ignore