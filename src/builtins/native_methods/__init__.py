from ...powang_types import *
from ...error import *
from .common import *
from .array import NATIVE_TYPE as ARRAY_NATIVE_TYPE, METHOD_NAMES as ARRAY_METHOD_NAMES, _dispatch_array
from .map import NATIVE_TYPE as MAP_NATIVE_TYPE, METHOD_NAMES as MAP_METHOD_NAMES, _dispatch_map
from .string import NATIVE_TYPE as STRING_NATIVE_TYPE, METHOD_NAMES as STRING_METHOD_NAMES, _dispatch_string
from .tuple import NATIVE_TYPE as TUPLE_NATIVE_TYPE, METHOD_NAMES as TUPLE_METHOD_NAMES, _dispatch_tuple
from .set import NATIVE_TYPE as SET_NATIVE_TYPE, METHOD_NAMES as SET_METHOD_NAMES, _dispatch_set
from .file import NATIVE_TYPE as FILE_NATIVE_TYPE, METHOD_NAMES as FILE_METHOD_NAMES, _dispatch_file
from .task import NATIVE_TYPE as TASK_NATIVE_TYPE, METHOD_NAMES as TASK_METHOD_NAMES, _dispatch_task
NATIVE_METHOD_TYPES = frozenset({
    ARRAY_NATIVE_TYPE,
    MAP_NATIVE_TYPE,
    STRING_NATIVE_TYPE,
    TUPLE_NATIVE_TYPE,
    SET_NATIVE_TYPE,
    FILE_NATIVE_TYPE,
    TASK_NATIVE_TYPE,
})

NATIVE_METHOD_NAMES: dict[str, frozenset[str]] = {
    ARRAY_NATIVE_TYPE: ARRAY_METHOD_NAMES,
    MAP_NATIVE_TYPE: MAP_METHOD_NAMES,
    STRING_NATIVE_TYPE: STRING_METHOD_NAMES,
    TUPLE_NATIVE_TYPE: TUPLE_METHOD_NAMES,
    SET_NATIVE_TYPE: SET_METHOD_NAMES,
    FILE_NATIVE_TYPE: FILE_METHOD_NAMES,
    TASK_NATIVE_TYPE: TASK_METHOD_NAMES,
}

def call_native_method(
    where: str,
    receiver_type: str,
    method_name: str,
    arguments: list[PowangAny],
) -> PowangAny:
    if not arguments:
        raise powang_throw(powang_error_format(
            'ARGUMENT', f'native method: {receiver_type}.{method_name}',
            'missing receiver argument',
        ))
    dispatch = {
        PowangArray.type: _dispatch_array,
        PowangMap.type: _dispatch_map,
        PowangString.type: _dispatch_string,
        PowangTuple.type: _dispatch_tuple,
        PowangSet.type: _dispatch_set,
        PowangFileStream.type: _dispatch_file,
        PowangTask.type: _dispatch_task,
    }.get(receiver_type)
    if dispatch is None:
        raise powang_throw(powang_error_identifier_not_found(
            'native method', f'{receiver_type}.{method_name}',
        ))
    try:
        return dispatch(where, method_name, arguments)
    except IndexError:
        raise powang_throw(powang_error_format(
            'ARGUMENT', f'native method: {receiver_type}.{method_name}',
            'not enought arguments',
        )) from None
    except TypeError as error:
        raise powang_throw(powang_error_format(
            'ARGUMENT', f'native method: {receiver_type}.{method_name}',
            f'invalid argument: {error}',
        )) from None


__all__ = [
    "NATIVE_METHOD_TYPES",
    "NATIVE_METHOD_NAMES",
    "call_native_method",
]
