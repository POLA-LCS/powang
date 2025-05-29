from .value import Types, get_number_from_word
from .errors import INLINE, ERROR_FORMAT_SYNTAX, RAISE
from .runtime import instructions

class TokenType:
    KEYWORD    = 'keyword'
    NAME       = 'name'
    NUMBER_LIT = 'number_lit'
    STRING_LIT = 'string_lit'
    LIST_LIT   = 'list_lit'
    EXPRESSION = 'expression'

class Token:
    def __init__(self, type: str, value: str | None):
        self.type = type
        self.value = value

    def __repr__(self) -> str:
        if self.value is not None:
            return f'({self.type}: {self.value})'
        return f'({self.type})'

Expression = tuple[Token, ...]
List = list[Token]
Sentence = list[Token | Expression | List]

# from icecream import ic as PRINT

def lex_open_close(record: str, part_in_words: list[str], open: str, close: str) -> tuple[int, str] | None:
    if record.endswith(close) and len(record) > 1:
        return (0, record)
    record += ' '
    stack = 0
    for eaten, word in enumerate(part_in_words):
        if open in word and not word.endswith(close):
            stack += 1
        if word.endswith(close):
            if stack > 0:
                stack -= 1
            else:
                return (eaten + 1, (record + word))
        record += word + ' '
    return None # SYNTAX ERROR

def lex_line(ln: int, line_in_words: list[str]) -> Sentence:
    sentence: Sentence = []
    
    eaten = 0
    for word_i, word in enumerate(line_in_words):
        if eaten > 0:
            eaten -= 1
            continue
        if word in instructions:
            sentence.append(Token(TokenType.KEYWORD, word))
        elif (number := get_number_from_word(word)) is not None:
            sentence.append(Token(TokenType.NUMBER_LIT, word))
        elif word.startswith("\'"):
            assert (result := lex_open_close(word, line_in_words[word_i + 1:], "\'", "\'")) is not None, \
                    INLINE(ln, ERROR_FORMAT_SYNTAX('invalid literal string: perhaps you miss a space?', ' '.join(line_in_words[word_i:])))
            eaten, record = result
            sentence.append(Token(TokenType.STRING_LIT, record))
        elif word.startswith('['):
            assert (result := lex_open_close(word, line_in_words[word_i + 1:], '[', ']')) is not None, \
                    INLINE(ln, ERROR_FORMAT_SYNTAX('invalid list expression: perhaps you miss a space?', ' '.join(line_in_words[word_i:])))
            eaten, record = result
            sentence.append(Token(TokenType.LIST_LIT, record))
        elif word.startswith('('):
            assert (result := lex_open_close(word, line_in_words[word_i + 1:], '(', ')')) is not None, \
                    INLINE(ln, ERROR_FORMAT_SYNTAX('invalid expression: perhaps you miss a space?', ' '.join(line_in_words[word_i:])))
            eaten, record = result
            sentence.append(Token(TokenType.EXPRESSION, record))

    return sentence