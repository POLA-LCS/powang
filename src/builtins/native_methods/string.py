from ...powang_types import *
from ...error import *
from .common import *
NATIVE_TYPE = PowangString.type
METHOD_NAMES = frozenset(['add', 'count', 'div', 'get', 'mul', 'reverse', 'size', 'sub'])
def _dispatch_string(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangString.type, 'native method', method)
    if method == 'add':
        other = _target(arguments[1])
        _require(other, PowangString.type, 'native method', method)
        return _finish(original, PowangString(source.data + other.data))
    if method == 'sub':
        other = _target(arguments[1])
        _require(other, PowangString.type, 'native method', method)
        return _finish(original, PowangString(source.data.replace(other.data, '', 1)))
    if method == 'mul':
        count = _int_argument(arguments, 1, 0)
        return _finish(original, PowangString(source.data * count))
    if method == 'div':
        separator = _target(arguments[1])
        _require(separator, PowangString.type, 'native method', method)
        return PowangArray([PowangString(part) for part in source.data.split(separator.data)])
    if method == 'count':
        other = _target(arguments[1])
        _require(other, PowangString.type, 'native method', method)
        return PowangInteger(source.data.count(other.data))
    if method == 'reverse':
        return _finish(original, PowangString(source.data[::-1]))
    if method == 'get':
        index = _normalize_index(len(source.data), _int_argument(arguments, 1, -1), method)
        return PowangString(source.data[index])
    if method == 'size':
        return PowangInteger(len(source.data))
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'str.{method}',
    ))
