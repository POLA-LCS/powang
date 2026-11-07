__all__ = [
    "_is_reference",
    "_target",
    "_deep_copy",
    "_finish",
    "_argument",
    "_require",
    "_require_unlocked",
    "_require_elements_unlocked",
    "_normalize_index",
    "_int_argument",
    "_MISSING",
]

from typing import Any, Optional

from ...powang_types import *
from ...error import *



def _is_reference(value: PowangAny) -> bool:
    return value.type == PowangReference.type


def _target(value: PowangAny) -> PowangAny:
    return value.get() if _is_reference(value) else value


def _deep_copy(value: PowangAny) -> PowangAny:
    if value.type == PowangReference.type:
        return value
    copied = PowangCopyConstruct(value)
    if value.type == PowangArray.type:
        copied.data = [_deep_copy(item) for item in value.data]
    elif value.type == PowangMap.type:
        copied.data = {
            _deep_copy(key): _deep_copy(item) for key, item in value.data.items()
        }
    elif value.type == PowangSet.type:
        copied.data = {_deep_copy(key): None for key in value.data.keys()}
    elif value.type == PowangTuple.type:
        copied.data = [_deep_copy(item) for item in value.data]
    elif value.type == PowangObjectType.type:
        copied.data = {key: _deep_copy(item) for key, item in value.data.items()}
        copied.private_props = {
            key: _deep_copy(item) for key, item in value.private_props.items()
        }
    return copied


def _finish(original: PowangAny, value: PowangAny) -> PowangAny:
    if _is_reference(original):
        original.set(value)
        return original
    return value


def _argument(arguments: list[PowangAny], index: int, default: Any = None) -> PowangAny:
    if index < len(arguments):
        return arguments[index]
    if default is _MISSING:
        raise powang_throw(powang_error_format(
            'ARGUMENT', 'native method', 'not enought arguments',
        ))
    return default


_MISSING = object()


def _require(value: PowangAny, expected: str, where: str, method: str) -> PowangAny:
    if value.type != expected:
        raise powang_throw(powang_error_type_match(
            f'native method: {method}', expected, value.type,
        ))
    return value


def _require_unlocked(value: PowangAny, method: str) -> None:
    if getattr(value, 'structure_locked', False):
        raise powang_throw(powang_error_format(
            'CONST', f'native method: {method}', "container structure is locked",
            ["the type annotation ends with '!'"],
        ))


def _require_elements_unlocked(value: PowangAny, method: str) -> None:
    if getattr(value, 'elements_locked', False):
        raise powang_throw(powang_error_format(
            'CONST', f'native method: {method}', "container elements are locked",
            ["the element type ends with '!'"],
        ))


def _normalize_index(length: int, index: int, method: str) -> int:
    if index < 0:
        index += length
    if index < 0 or index >= length:
        raise powang_throw(powang_error_index_out_of_range(index, length))
    return index


def _int_argument(arguments: list[PowangAny], index: int, default: int) -> int:
    value = _argument(arguments, index, PowangInteger(default))
    concrete = PowangUnwrapAny(value)
    _require(concrete, PowangInteger.type, 'native method', 'index')
    return concrete.data


