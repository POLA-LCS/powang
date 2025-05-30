from .value import Types
from .errors import INLINE, ERROR_FORMAT_SYNTAX
from typing import Self

INSTRUCTIONS_SET: list[str] = [
    'stdout', 'print'
]

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

def get_number_from_word(number_str: str) -> (Types.Number | None):
    try:
        return float(number_str)
    except ValueError:
        return None

def lex_open_close(record: str, part_in_words: list[str], open: str, close: str) -> (tuple[int, str] | None):
    if record.endswith(close) and len(record) > 1:
        return (0, record)
    record += ' '
    stack = 0
    for eaten_words, word in enumerate(part_in_words):
        if open in word and word is not close:
            stack += 1
        if word.endswith(close):
            if stack > 0:
                stack -= 1
            else:
                return (eaten_words + 1, (record + word))
        record += word + ' '
    return None # SYNTAX ERROR

def tokenize_line(ln: int, line_in_words: list[str]) -> list[Token]:
    sentence: list[Token] = []

    eaten_words = 0
    for word_index, word in enumerate(line_in_words):
        if word == '##':
            return sentence
        if len(word) == 0:
            continue
        if eaten_words > 0:
            eaten_words -= 1
            continue

        # KEYWORDS
        if word in INSTRUCTIONS_SET:
            sentence.append(Token(TokenType.KEYWORD, word))
        # LITERAL NUMBER
        elif (number := get_number_from_word(word)) is not None:
            sentence.append(Token(TokenType.NUMBER_LIT, word))
        # LITERAL STRING
        elif word.startswith("\'"):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], "\'", "\'")) is not None, \
                    INLINE(ln, ERROR_FORMAT_SYNTAX("invalid literal string: reached end of line", ' '.join(line_in_words[word_index:])))
            eaten_words, record = result
            record = record[1:-1]
            record = record.replace("\\n", '\n')
            record = record.replace("\\t", '\t')
            assert "\'" not in record, \
                    INLINE(ln, ERROR_FORMAT_SYNTAX("string didin't finished properly", ' '.join(line_in_words[word_index:])))

            sentence.append(Token(TokenType.STRING_LIT, record))
        # LITERAL LIST
        elif word.startswith('['):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], '[', ']')) is not None, \
                    INLINE(ln, ERROR_FORMAT_SYNTAX('invalid list expression: perhaps you miss a space?', ' '.join(line_in_words[word_index:])))
            eaten_words, record = result

            # RE LEXING
            sentence.append(Token(TokenType.LIST_LIT, tokenize_line(ln, record[1:-1].split(' '))))
        # EXPRESSION
        elif word.startswith('('):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], '(', ')')) is not None, \
                    INLINE(ln, ERROR_FORMAT_SYNTAX('invalid expression: perhaps you miss a space?', ' '.join(line_in_words[word_index:])))
            eaten_words, record = result

            # RE LEXING
            sentence.append(Token(TokenType.EXPRESSION, tokenize_line(ln, record[1:-1].split(' '))))

        else:
            sentence.append(Token(TokenType.NAME, word))

    return sentence