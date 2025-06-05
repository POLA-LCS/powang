from .token import Token, TokenLiteralValue, TokenNameValue, TokenListValue, TokenType
from ..types import PolangNumber, PolangString, PolangStruct # TODO: PolangStruct
from ..error import error_syntax, error_with_line
from ..instructions.instructions import INSTRUCTIONS, KEYWORDS

def get_number_from_word(number_str: str) -> (float | None):
    try:               return float(number_str)
    except ValueError: return None

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

def tokenize_line(ln: int, line_in_words: list[str]):
    """### RECURSIVE"""
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

        # ====== INSTRUCTIONS
        if word in INSTRUCTIONS:
            sentence.append(TokenNameValue(TokenType.INSTRUCTION, word))
            
        elif word in KEYWORDS:
            sentence.append(TokenNameValue(TokenType.KEYWORD, word))
            
        # ====== LITERAL NUMBER
        elif (number := get_number_from_word(word)) is not None:
            sentence.append(TokenLiteralValue(TokenType.NUMBER_LIT, PolangNumber(number)))

        # ====== LITERAL STRING
        elif word.startswith("\'"):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], "\'", "\'")) is not None, \
                error_with_line(ln, error_syntax(
                    "invalid literal string", [
                    "reached end of line",
                    ' '.join(line_in_words[word_index:]) # line
                ]))
            eaten_words, record = result
            record = record[1:-1]
            
            # scape chars
            record = record.replace("\\n", '\n')
            record = record.replace("\\t", '\t')
            
            # ascii scape
            if "\\a" in record:
                record = record.replace("\\a32", ' ')
                record = record.replace("\\a13", '\n')
                record = record.replace("\\a9", '\t')
            
            assert "\'" not in record, \
                    error_with_line(ln, error_syntax("string didin't finished properly", [' '.join(line_in_words[word_index:])]))

            sentence.append(TokenLiteralValue(TokenType.STRING_LIT, PolangString(record)))

        # ====== LITERAL LIST
        elif word.startswith('['):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], "[", "]")) is not None, \
                error_with_line(ln, error_syntax(
                    "invalid list literael", [
                    "perhaps you miss a space at the end",
                    ' '.join(line_in_words[word_index:]) # line
                ]))
            eaten_words, record = result
            sentence.append(TokenListValue(
                TokenType.LIST_LIT,
                tokenize_line(ln, record[1:-1].split(' ')), # relexing for inner tokens
            ))

        # ====== EXPRESSION
        elif word.startswith('('):
            assert (result := lex_open_close(word, line_in_words[word_index + 1:], "(", ")")) is not None, \
                error_with_line(ln, error_syntax(
                    "invalid expression literael", [
                    "perhaps you miss a space at the end",
                    ' '.join(line_in_words[word_index:]) # line
                ]))
            eaten_words, record = result
            sentence.append(TokenListValue(
                TokenType.EXPRESSION,
                tokenize_line(ln, record[1:-1].split(' ')) # relexing for inner tokens
            ))
            
        else:
            sentence.append(TokenNameValue(TokenType.IDENTIFIER, word))

    return sentence