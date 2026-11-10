from ...powang_types import *
from ...error import *
from .common import *
NATIVE_TYPE = PowangString.type
METHOD_NAMES = frozenset([
    'add', 'char_at', 'chars', 'count', 'div', 'get', 'mul', 'reverse',
    'size', 'sub',
])
def _string_operand(where: str, method: str, value: PowangAny) -> str:
    if value.type == PowangString.type or value.type == PowangChar.type:
        return value.data
    raise powang_throw(powang_error_format(
        'TYPE',
        f'native method: {method}',
        'expected a str or a char',
        [f'but {value.type} was encountered'],
    ))


def _dispatch_string(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangString.type, 'native method', method)
    if method == 'add':
        other = _string_operand(where, method, _target(arguments[1]))
        return _finish(original, PowangString(source.data + other))
    if method == 'sub':
        other = _string_operand(where, method, _target(arguments[1]))
        return _finish(original, PowangString(source.data.replace(other, '', 1)))
    if method == 'mul':
        count = _int_argument(arguments, 1, 0)
        return _finish(original, PowangString(source.data * count))
    if method == 'div':
        separator = _string_operand(where, method, _target(arguments[1]))
        return PowangArray([PowangString(part) for part in source.data.split(separator)])
    if method == 'count':
        other = _string_operand(where, method, _target(arguments[1]))
        return PowangInteger(source.data.count(other))
    if method == 'reverse':
        return _finish(original, PowangString(source.data[::-1]))
    if method == 'get':
        index = _normalize_index(len(source.data), _int_argument(arguments, 1, -1), method)
        return PowangString(source.data[index])
    if method == 'char_at':
        index = _normalize_index(len(source.data), _int_argument(arguments, 1, -1), method)
        return PowangChar(source.data[index])
    if method == 'chars':
        return PowangArray([PowangChar(character) for character in source.data])
    if method == 'size':
        return PowangInteger(len(source.data))
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'str.{method}',
    ))
