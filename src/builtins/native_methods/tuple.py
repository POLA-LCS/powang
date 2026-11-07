from ...powang_types import *
from ...error import *
from .common import *
NATIVE_TYPE = PowangTuple.type
METHOD_NAMES = frozenset(['add', 'get', 'reverse', 'size', 'to_arr'])
def _dispatch_tuple(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    source = _target(arguments[0])
    _require(source, PowangTuple.type, 'native method', method)
    if method == 'get':
        index = _normalize_index(len(source.data), _int_argument(arguments, 1, -1), method)
        return _deep_copy(source.data[index])
    if method == 'size':
        return PowangInteger(len(source.data))
    if method == 'to_arr':
        return PowangArray([_deep_copy(item) for item in source.data])
    if method == 'reverse':
        return PowangTuple([_deep_copy(item) for item in reversed(source.data)])
    if method == 'add':
        other = _target(arguments[1])
        _require(other, PowangTuple.type, 'native method', method)
        return PowangTuple(
            [_deep_copy(item) for item in source.data]
            + [_deep_copy(item) for item in other.data]
        )
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'tup.{method}',
    ))
