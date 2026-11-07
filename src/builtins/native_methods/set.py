from ...powang_types import *
from ...error import *
from .common import *
NATIVE_TYPE = PowangSet.type
METHOD_NAMES = frozenset(['add', 'clear', 'difference', 'has', 'intersection', 'pop', 'popget', 'size', 'to_arr', 'union'])
def _dispatch_set(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangSet.type, 'native method', method)
    if method == 'add':
        _require_unlocked(source, method)
        value = _target(arguments[1])
        result = dict(source.data)
        result[value] = None
        return _finish(original, PowangSet(list(result.keys())))
    if method == 'has':
        return PowangBoolean(_target(arguments[1]) in source.data)
    if method in ('pop', 'popget'):
        _require_unlocked(source, method)
        value = _target(arguments[1])
        existed = value in source.data
        if existed:
            result = dict(source.data)
            del result[value]
            _finish(original, PowangSet(list(result.keys())))
        if method == 'popget':
            return PowangBoolean(existed)
        return _finish(original, PowangSet(list(source.data.keys())))
    if method in ('union', 'intersection', 'difference'):
        other = _target(arguments[1])
        _require(other, PowangSet.type, 'native method', method)
        if method == 'union':
            _require_unlocked(source, method)
            result = dict(source.data)
            result.update(other.data)
        elif method == 'intersection':
            _require_unlocked(source, method)
            result = {key: None for key in source.data.keys() if key in other.data}
        else:
            _require_unlocked(source, method)
            result = {key: None for key in source.data.keys() if key not in other.data}
        return _finish(original, PowangSet(list(result.keys())))
    if method == 'size':
        return PowangInteger(len(source.data))
    if method == 'to_arr':
        return PowangArray([_deep_copy(key) for key in source.data.keys()])
    if method == 'clear':
        _require_unlocked(source, method)
        return _finish(original, PowangSet())
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'set.{method}',
    ))
