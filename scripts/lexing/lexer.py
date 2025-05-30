from ..types import NUMBER
from .token import Token, TokenType
from ..errors import error_format, error_format_syntax, INLINE_ERROR
from ..insts.instructions import INSTRUCTIONS

def get_number_from_word(number_str: str) -> (NUMBER | None):
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
        if word in INSTRUCTIONS:
            sentence.append(Token(TokenType.KEYWORD, word))
        # LITERAL NUMBER
        elif (number := get_number_from_word(word)) is not None:
            sentence.append(Token(TokenType.NUMBER_LIT, word))
        # LITERAL STRING
        elif word.startswith("\'"):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], "\'", "\'")) is not None, \
                    INLINE_ERROR(ln, error_format_syntax("invalid literal string: reached end of line", ' '.join(line_in_words[word_index:])))
            eaten_words, record = result
            record = record[1:-1]
            record = record.replace("\\n", '\n')
            record = record.replace("\\t", '\t')
            assert "\'" not in record, \
                    INLINE_ERROR(ln, error_format_syntax("string didin't finished properly", ' '.join(line_in_words[word_index:])))

            sentence.append(Token(TokenType.STRING_LIT, record))
        # LITERAL LIST
        elif word.startswith('['):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], '[', ']')) is not None, \
                    INLINE_ERROR(ln, error_format_syntax('invalid list expression: perhaps you miss a space?', ' '.join(line_in_words[word_index:])))
            eaten_words, record = result

            # RE LEXING
            sentence.append(Token(TokenType.LIST_LIT, tokenize_line(ln, record[1:-1].split(' '))))
        # EXPRESSION
        elif word.startswith('('):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], '(', ')')) is not None, \
                    INLINE_ERROR(ln, error_format_syntax('invalid expression: perhaps you miss a space?', ' '.join(line_in_words[word_index:])))
            eaten_words, record = result

            # RE LEXING
            sentence.append(Token(TokenType.EXPRESSION, tokenize_line(ln, record[1:-1].split(' '))))

        else:
            sentence.append(Token(TokenType.NAME, word))

    return sentence