"""Character predicates and code point helpers.

Every predicate accepts either a ``char`` or a one-character ``str``. The
latter keeps older code that indexes a string working while new code can use
``str.char_at`` or ``str.chars`` and stay in ``char``.
"""

from ..powang_types import *
from ..error import *

_DECIMAL_DIGITS = frozenset('0123456789')
_ASCII_LETTERS = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
)
_ASCII_WHITESPACE = frozenset(' \t\n\r\v\f')


def _character_text(where: str, value: PowangAny) -> str:
    if value.type == PowangAnyType.type:
        value = PowangUnwrapAny(value)
    require(value.defined, lambda: powang_error_undefined_argument(
        where,
        1,
        value.type,
    ))
    if value.type == PowangChar.type:
        return value.data
    if value.type == PowangString.type and len(value.data) == 1:
        return value.data
    raise powang_throw(powang_error_format(
        'TYPE',
        where,
        'expected a char or a one-character str',
        [f'but {value.type} was encountered'],
    ))


def builtin_is_digit(value: PowangAny) -> PowangBoolean:
    return PowangBoolean(_character_text('function: is_digit', value) in _DECIMAL_DIGITS)


def builtin_is_alpha(value: PowangAny) -> PowangBoolean:
    return PowangBoolean(_character_text('function: is_alpha', value) in _ASCII_LETTERS)


def builtin_is_alnum(value: PowangAny) -> PowangBoolean:
    character = _character_text('function: is_alnum', value)
    return PowangBoolean(character in _DECIMAL_DIGITS or character in _ASCII_LETTERS)


def builtin_is_space(value: PowangAny) -> PowangBoolean:
    return PowangBoolean(_character_text('function: is_space', value) in _ASCII_WHITESPACE)


def builtin_is_upper(value: PowangAny) -> PowangBoolean:
    character = _character_text('function: is_upper', value)
    return PowangBoolean(character in _ASCII_LETTERS and character.isupper())


def builtin_is_lower(value: PowangAny) -> PowangBoolean:
    character = _character_text('function: is_lower', value)
    return PowangBoolean(character in _ASCII_LETTERS and character.islower())


def builtin_is_ascii(value: PowangAny) -> PowangBoolean:
    return PowangBoolean(_character_text('function: is_ascii', value).isascii())


def builtin_ord(value: PowangAny) -> PowangInteger:
    return PowangInteger(ord(_character_text('function: ord', value)))


def builtin_chr(value: PowangAny) -> PowangChar:
    if value.type == PowangAnyType.type:
        value = PowangUnwrapAny(value)
    require(value.defined, lambda: powang_error_undefined_argument(
        'function: chr',
        1,
        value.type,
    ))
    require(value.type == PowangInteger.type, lambda: powang_error_type_match(
        'function: chr',
        PowangInteger.type,
        value.type,
    ))
    code_point = value.data
    if code_point < 0 or code_point > 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
        label = f'U+{code_point:X}' if code_point >= 0 else str(code_point)
        raise powang_throw(powang_error_format(
            'VALUE',
            'function: chr',
            'invalid Unicode scalar value',
            [f'{label} is not a Unicode scalar value'],
        ))
    return PowangChar(chr(code_point))


def builtin_digit_value(value: PowangAny) -> PowangInteger:
    character = _character_text('function: digit_value', value)
    if character not in _DECIMAL_DIGITS:
        return PowangInteger(-1)
    return PowangInteger(ord(character) - ord('0'))
