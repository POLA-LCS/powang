from ...powang_types import *
from ...error import *
from .common import *

NATIVE_TYPE = PowangChar.type
METHOD_NAMES = frozenset([
    'code', 'to_str', 'is_digit', 'is_alpha', 'is_alnum', 'is_space',
    'is_upper', 'is_lower', 'is_ascii',
])

_DECIMAL_DIGITS = frozenset('0123456789')
_ASCII_LETTERS = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
)
_ASCII_WHITESPACE = frozenset(' \t\n\r\v\f')


def _dispatch_char(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangChar.type, 'native method', method)
    require(source.defined, lambda: powang_error_undefined_reference(
        'native method',
        f'char.{method}',
    ))
    character = source.data
    if method == 'code':
        return PowangInteger(ord(character))
    if method == 'to_str':
        return PowangString(character)
    if method == 'is_digit':
        return PowangBoolean(character in _DECIMAL_DIGITS)
    if method == 'is_alpha':
        return PowangBoolean(character in _ASCII_LETTERS)
    if method == 'is_alnum':
        return PowangBoolean(
            character in _DECIMAL_DIGITS or character in _ASCII_LETTERS
        )
    if method == 'is_space':
        return PowangBoolean(character in _ASCII_WHITESPACE)
    if method == 'is_upper':
        return PowangBoolean(
            character in _ASCII_LETTERS and character.isupper()
        )
    if method == 'is_lower':
        return PowangBoolean(
            character in _ASCII_LETTERS and character.islower()
        )
    if method == 'is_ascii':
        return PowangBoolean(character.isascii())
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'char.{method}',
    ))
