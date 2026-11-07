from ...powang_types import *
from ...error import *
from .common import *
NATIVE_TYPE = PowangMap.type
METHOD_NAMES = frozenset(['clear', 'get', 'has', 'keys', 'merge', 'pop', 'popget', 'size', 'values'])
def _dispatch_map(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangMap.type, 'native method', method)
    if method == 'has':
        return PowangBoolean(_target(arguments[1]) in source.data)
    if method == 'get':
        key = _target(arguments[1])
        if key in source.data:
            return _deep_copy(source.data[key])
        if len(arguments) > 2:
            return _deep_copy(arguments[2])
        raise powang_throw(powang_error_key(str(key)))
    if method in ('pop', 'popget'):
        key = _target(arguments[1])
        if key not in source.data:
            raise powang_throw(powang_error_key(str(key)))
        value = _deep_copy(source.data[key])
        result_data = dict(source.data)
        del result_data[key]
        result_map = PowangMap(result_data)
        if method == 'popget':
            if _is_reference(original):
                _require_unlocked(source, method)
                original.set(result_map)
            return value
        _require_unlocked(source, method)
        return _finish(original, result_map)
    if method == 'merge':
        _require_unlocked(source, method)
        other = _target(arguments[1])
        _require(other, PowangMap.type, 'native method', method)
        result = dict(source.data)
        result.update(other.data)
        return _finish(original, PowangMap(result))
    if method == 'keys':
        return PowangArray([_deep_copy(key) for key in source.data.keys()])
    if method == 'values':
        return PowangArray([_deep_copy(value) for value in source.data.values()])
    if method == 'size':
        return PowangInteger(len(source.data))
    if method == 'clear':
        _require_unlocked(source, method)
        return _finish(original, PowangMap())
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'map.{method}',
    ))
