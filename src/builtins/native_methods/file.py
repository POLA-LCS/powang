from ..file import builtin_open, builtin_read, builtin_write, builtin_close
from ...powang_types import *
from .common import (
    _target,
    _require,
    _finish,
    _int_argument,
    _deep_copy,
)
NATIVE_TYPE = PowangFileStream.type
METHOD_NAMES = frozenset(['close', 'open', 'read', 'write'])
from ...powang_types import *
from ...error import *
def _file_source(arguments: list[PowangAny]) -> PowangString:
    source = _target(arguments[0])
    if source.type == PowangFileStream.type:
        return source.data
    if source.type == PowangString.type:
        return source
    raise powang_throw(powang_error_type_match(
        'native method: file', 'file or str', source.type,
    ))


def _dispatch_file(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    if method == 'open':
        path = _target(arguments[0])
        mode = _target(arguments[1]) if len(arguments) > 1 else PowangString("read")
        _require(path, PowangString.type, 'native method', method)
        _require(mode, PowangString.type, 'native method', method)
        opened = builtin_open(path, mode)
        if not opened.data:
            return PowangBoolean(False)
        return PowangFileStream(path, mode)
    source_name = _file_source(arguments)
    if method == 'read':
        return builtin_read(source_name)
    if method == 'close':
        return builtin_close(source_name)
    if method == 'write':
        return builtin_write(source_name, _target(arguments[1]))
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'file.{method}',
    ))
