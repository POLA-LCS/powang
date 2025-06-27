from re import match, Match
from typing import Callable, Optional
from ..error import *
from .token import LexerTokenType, LexerToken

class Tokenizer:
    Keywords: set[str] = {
        'if', 'else', 'for', 'func', 'ret', 'use', 'type'
    }
    
    RegexPatterns: dict[
        str,                               # Regex pattern
        tuple[
            Optional[LexerTokenType],      # Optional LexerTokenType assosiated
            Optional[Callable[[str], str]] # Optional Modifier function to process the matched string
        ]] = {
        
        r'##.*': (None, None),                      # Comments
        r';'   : (LexerTokenType.SEMI_COLON, None), # Line termination
        
        r'-?\d+\.\d+': (LexerTokenType.FLOATING_LITERAL, None),
        r'-?\d+'     : (LexerTokenType.INTEGER_LITERAL, None),
        
        r'\'([^\']*)\'': ( # eg. 'Hello, world!'
            LexerTokenType.STRING_LITERAL,
            lambda x: x[1:-1]  # Remove the quotes
        ),
        
        r'\"([^\"]*)\"': ( # eg. "Hello, @[name]!"
            LexerTokenType.FMT_STRING_LITERAL,
            lambda x: x[1:-1]  # Remove the quotes
        ),
        
        r'[+-]': (LexerTokenType.OPERATOR_ADDITION, None),
        r'[*/]': (LexerTokenType.OPERATOR_MULTIPLICATION, None),
        r':'   : (LexerTokenType.COLON, None),
        r'@'   : (LexerTokenType.WEAK_PREFIX, None),
        r'!'   : (LexerTokenType.EXCLAMATION, None),
        r'='   : (LexerTokenType.OPERATOR_ASSIGNMENT, None),
        r'\.'  : (LexerTokenType.DOT,   None),
        r','   : (LexerTokenType.COMMA, None),
            
        r'\(': (LexerTokenType.LEFT_PARENTHESIS, None),
        r'\)': (LexerTokenType.RIGHT_PARENTHESIS, None),
        
        r'\[': (LexerTokenType.LEFT_BRACKET, None),
        r'\]': (LexerTokenType.RIGHT_BRACKET, None),
        
        r'\{': (LexerTokenType.LEFT_BRACE, None),
        r'\}': (LexerTokenType.RIGHT_BRACE, None),
        

        r'\s+': (None, None),                          # Whitespace

        r'\b(?:' + '|'.join(Keywords) + r')\b': (LexerTokenType.KEYWORD, None), # Keywords
        r'true' : (LexerTokenType.BOOLEAN_LITERAL, None),
        r'false': (LexerTokenType.BOOLEAN_LITERAL, None),
        r'nova' : (LexerTokenType.NOVA_LITERAL,    None),
        r'[a-zA-Z_][a-zA-Z0-9_]*': (LexerTokenType.IDENTIFIER, None),           # Identifiers
    }
    
    
    def __init__(self, data: str):
        self.data = data
        self.position: int = 0
        self.row: int = 0
        
    def isNumber(self, string: str) -> bool:
        try:
            float(string)
            return True
        except ValueError:
            return False
        
    def hasMoreTokens(self) -> bool:
        return self.position < len(self.data)
        
    def actualChar(self) -> str: # char
        return self.data[self.position]
        
    def getNextToken(self) -> LexerToken:
        if not self.hasMoreTokens():
            return LexerToken(LexerTokenType.END_OF_FILE, None)
               
        if self.actualChar() == '\n':
            self.row += 1
               
        # Pattern recognition
        for pattern, (token_type, modifier) in self.RegexPatterns.items():
            match_result: Match[str] | None = match(pattern, self.data[self.position:])
            
            if match_result is not None:
                matched_string: str = match_result.group(0)
                self.position += len(matched_string)
                
                if token_type is None: # whitespace
                    return self.getNextToken()
                
                if modifier is None:
                    return LexerToken(token_type, matched_string)
                
                return LexerToken(token_type, modifier(matched_string))
        lines = self.data.split('\n')
        for i in range(self.row):
            self.position -= len(lines[i])
        raise powang_throw(powang_error_syntax(None, "unexpected character", [
            lines[self.row],
            ' ' * (self.position) + '^'
        ]))