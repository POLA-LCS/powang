from ...powang_types import *
from ...error import *
from .common import *
NATIVE_TYPE = PowangArray.type
METHOD_NAMES = frozenset(['add', 'clear', 'get', 'pop', 'popget', 'popval', 'push', 'put', 'reverse', 'set', 'size'])
def _array_add(arguments: list[PowangAny], method: str, flatten: bool) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangArray.type, 'native method', method)
    _require_unlocked(source, method)
    items = [_deep_copy(item) for item in source.data]
    addition = _target(arguments[1])
    if flatten:
        if addition.type not in (PowangArray.type, PowangTuple.type, PowangSet.type):
            raise powang_throw(powang_error_type_match(
                f'native method: {method}', 'arr, tup or set', addition.type,
            ))
        additions = list(addition.data.keys()) if addition.type == PowangSet.type else addition.data
        items.extend(_deep_copy(item) for item in additions)
    else:
        items.append(_deep_copy(addition))
    return _finish(original, PowangArray(items))


def _array_popget(arguments: list[PowangAny], method: str, remove: bool) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangArray.type, 'native method', method)
    index = _normalize_index(len(source.data), _int_argument(arguments, 1, -1), method)
    result = _deep_copy(source.data[index])
    if remove:
        _require_unlocked(source, method)
        items = list(source.data)
        items.pop(index)
        _finish(original, PowangArray(items))
    return result


def _array_popval(arguments: list[PowangAny], method: str) -> PowangAny:
    original = arguments[0]
    source = _target(original)
    _require(source, PowangArray.type, 'native method', method)
    _require_unlocked(source, method)
    needle = _target(arguments[1])
    maximum = _int_argument(arguments, 2, -1)
    removed = 0
    items: list[PowangAny] = []
    for item in source.data:
        if removed != maximum and item == needle:
            removed += 1
            continue
        items.append(item)
    return _finish(original, PowangArray(items))


def _dispatch_array(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    if method == 'push':
        return _array_add(arguments, method, False)
    if method == 'add':
        return _array_add(arguments, method, True)
    if method == 'pop':
        return _array_popget(arguments, method, True)
    if method == 'popget':
        return _array_popget(arguments, method, True)
    if method == 'put':
        original = arguments[0]
        source = _target(original)
        _require(source, PowangArray.type, 'native method', method)
        _require_unlocked(source, method)
        index = _int_argument(arguments, 1, 0)
        items = list(source.data)
        if index < 0:
            index = max(0, len(items) + index)
        if index > len(items):
            index = len(items)
        items.insert(index, _deep_copy(arguments[2]))
        return _finish(original, PowangArray(items))
    if method == 'popval':
        return _array_popval(arguments, method)
    if method == 'get':
        source = _target(arguments[0])
        _require(source, PowangArray.type, 'native method', method)
        index = _normalize_index(len(source.data), _int_argument(arguments, 1, -1), method)
        return _deep_copy(source.data[index])
    if method == 'set':
        original = arguments[0]
        source = _target(original)
        _require(source, PowangArray.type, 'native method', method)
        _require_elements_unlocked(source, method)
        index = _normalize_index(len(source.data), _int_argument(arguments, 1, 0), method)
        items = list(source.data)
        items[index] = _deep_copy(arguments[2])
        return _finish(original, PowangArray(items))
    if method == 'reverse':
        original = arguments[0]
        source = _target(original)
        _require(source, PowangArray.type, 'native method', method)
        _require_unlocked(source, method)
        return _finish(original, PowangArray(list(reversed(source.data))))
    if method == 'clear':
        original = arguments[0]
        source = _target(original)
        _require(source, PowangArray.type, 'native method', method)
        _require_unlocked(source, method)
        return _finish(original, PowangArray())
    if method == 'size':
        source = _target(arguments[0])
        _require(source, PowangArray.type, 'native method', method)
        return PowangInteger(len(source.data))
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'arr.{method}',
    ))
