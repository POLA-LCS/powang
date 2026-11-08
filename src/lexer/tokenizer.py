from re import match, Match
from typing import Callable, Optional
from ..error import *
from .token import LexerTokenType, LexerToken

def _invalid_exponent(matched: str) -> str:
    """Reject an exponent marker with no digits after it (e.g. `1e`, `1.5e+`)."""
    raise powang_throw(powang_error_syntax(None, "invalid floating literal", [
        f"incomplete exponent in: {matched}",
    ]))

class Tokenizer:
    Keywords: set[str] = {
        'if', 'else', 'for', 'fun', 'return', 'use', 'type', 'extern',
        'export', 'try', 'catch', 'finally', 'spawn', 'match', 'case', 'const',
        'enum', 'module', 'loop', 'break', 'continue',
    }
    
    RegexPatterns: dict[
        str,                               # Regex pattern
        tuple[
            Optional[LexerTokenType],      # Optional LexerTokenType assosiated
            Optional[Callable[[str], str]] # Optional Modifier function to process the matched string
        ]] = {
        
        r'##.*': (None, None),                      # Comments
        r';'   : (LexerTokenType.SEMI_COLON, None), # Line termination
        
        r'\d+(?:\.\d+)?[eE](?=[^\d+\-]|$|[+\-](?!\d))': (LexerTokenType.FLOATING_LITERAL, _invalid_exponent),
        r'\d+\.\d+(?:[eE][+-]?\d+)?': (LexerTokenType.FLOATING_LITERAL, None),
        r'\d+[eE][+-]?\d+'          : (LexerTokenType.FLOATING_LITERAL, None),
        r'\d+'                      : (LexerTokenType.INTEGER_LITERAL, None),
        
        r'\$"((?:\\.|[^"\\])*)"': (
            LexerTokenType.INTERPOLATED_STRING_LITERAL,
            lambda x: x[2:-1]  # Remove the $ and the quotes
        ),
        r'\"((?:\\.|[^\"\\])*)\"': (
            LexerTokenType.STRING_LITERAL,
            lambda x: x[1:-1]  # Remove the quotes
        ),
        
        
        r'\&\&' : (LexerTokenType.AND, None),
        r'\|\|' : (LexerTokenType.OR, None),
        r'&>'   : (LexerTokenType.REFERENCE_PIPELINE, None),
        r'\|'   : (LexerTokenType.PIPE, None),
        r'&'    : (LexerTokenType.AMPERSAND, None),
        r'::'   : (LexerTokenType.COMPARE_EQ_TYPE, None),
        r'!:'   : (LexerTokenType.COMPARE_NEQ_TYPE, None),
        r'=='   : (LexerTokenType.COMPARE_EQ, None),
        r'!='   : (LexerTokenType.COMPARE_NEQ, None),
        r'<='   : (LexerTokenType.COMPARE_LEQ, None),
        r'>='   : (LexerTokenType.COMPARE_GEQ, None),
        r'<'    : (LexerTokenType.COMPARE_LSS, None),

        r'>>'  : (LexerTokenType.RIGHT_ARROW, None),
        r':>'  : (LexerTokenType.PIPELINE, None),
        r'>'   : (LexerTokenType.COMPARE_GTR, None),
        
        r'\+='    : (LexerTokenType.OPERATOR_ASSIGNMENT_PLUS, None),
        r'\-='    : (LexerTokenType.OPERATOR_ASSIGNMENT_MINUS, None),
        r'\*='    : (LexerTokenType.OPERATOR_ASSIGNMENT_STAR, None),
        r'\/='    : (LexerTokenType.OPERATOR_ASSIGNMENT_SLASH, None),
        
        r':'   : (LexerTokenType.COLON, None),
        r'!'   : (LexerTokenType.EXCLAMATION, None),
        r'='   : (LexerTokenType.OPERATOR_ASSIGNMENT, None),

        r'\[\+\]' : (LexerTokenType.OPERATOR_SUMATORY, None),
        r'\[\-\]' : (LexerTokenType.OPERATOR_INVERSE, None),
        r'\+'     : (LexerTokenType.OPERATOR_PLUS , None),
        r'-'      : (LexerTokenType.OPERATOR_MINUS, None),
        r'\*'     : (LexerTokenType.STAR , None),
        r'/'      : (LexerTokenType.SLASH, None),
        r'%'      : (LexerTokenType.PERCENT, None),

        r'\.\.\.' : (LexerTokenType.ELLIPSIS, None),
        r'\.'  : (LexerTokenType.DOT,   None),
        r'\?\.' : (LexerTokenType.SAFE_ACCESS, None),
        r'\?\?' : (LexerTokenType.COALESCE, None),
        r'\?'  : (LexerTokenType.QUESTION_MARK, None),
        r','   : (LexerTokenType.COMMA, None),

        r'@'   : (LexerTokenType.ARROBA, None),
            
        r'\(': (LexerTokenType.LEFT_PARENTHESIS, None),
        r'\)': (LexerTokenType.RIGHT_PARENTHESIS, None),
        
        r'\[': (LexerTokenType.LEFT_BRACKET, None),
        r'\]': (LexerTokenType.RIGHT_BRACKET, None),
        
        r'\{': (LexerTokenType.LEFT_BRACE, None),
        r'\}': (LexerTokenType.RIGHT_BRACE, None),
        
        r'\s*as(?![a-zA-Z0-9_])': (LexerTokenType.OPERATOR_CAST_AS, lambda x: x.strip()),
        r'\s+': (None, None),                          # Whitespace

        r'\b(?:' + '|'.join(Keywords) + r')\b': (LexerTokenType.KEYWORD, None), # Keywords
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

    def _line_column(self) -> tuple[int, int]:
        """Return the zero-based line and column of ``self.position``."""
        last_newline = self.data.rfind('\n', 0, self.position)
        return self.row, self.position - last_newline - 1
        
    def getNextToken(self) -> LexerToken:
        while self.hasMoreTokens():
            while self.hasMoreTokens() and self.actualChar() == '\n':
                self.row += 1
                self.position += 1

            if not self.hasMoreTokens():
                return LexerToken(LexerTokenType.END_OF_FILE, None, self.row, 0)

            ## Block comments use `#! ... !#` and may span multiple lines.
            if self.data.startswith('#!', self.position):
                comment_end = self.data.find('!#', self.position + 2)
                if comment_end == -1:
                    lines = self.data.split('\n')
                    raise powang_throw(powang_error_with_position(
                        powang_error_syntax(None, "unterminated block comment", [
                            lines[self.row] if self.row < len(lines) else '',
                        ]),
                        self.row + 1,
                        self._line_column()[1],
                    ))
                skipped = self.data[self.position:comment_end + 2]
                self.row += skipped.count('\n')
                self.position = comment_end + 2
                continue

            # Pattern recognition
            for pattern, (token_type, modifier) in self.RegexPatterns.items():
                match_result: Match[str] | None = match(pattern, self.data[self.position:])

                if match_result is not None:
                    matched_string: str = match_result.group(0)
                    token_line, token_column = self._line_column()
                    self.position += len(matched_string)

                    if token_type is None: # whitespace / comments
                        ## Whitespace may contain newlines; the row counter must
                        ## follow them or later token positions drift.
                        self.row += matched_string.count('\n')
                        break # skip and keep scanning iteratively

                    if modifier is None:
                        self.row += matched_string.count('\n')
                        return LexerToken(token_type, matched_string, token_line, token_column)

                    self.row += matched_string.count('\n')
                    return LexerToken(token_type, modifier(matched_string), token_line, token_column)
            else:
                lines = self.data.split('\n')
                token_line, token_column = self._line_column()
                for i in range(self.row):
                    self.position -= len(lines[i]) + 1
                raise powang_throw(powang_error_with_position(
                    powang_error_syntax(None, "unexpected character", [
                        lines[self.row],
                        (' ' * (self.position)) + '^'
                    ]),
                    token_line + 1,
                    token_column,
                ))
        return LexerToken(LexerTokenType.END_OF_FILE, None, self.row, 0)