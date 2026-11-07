from ..tasks import builtin_wait, builtin_cancel, builtin_task_status
from ...powang_types import *
from .common import (
    _target,
    _require,
    _finish,
    _int_argument,
    _deep_copy,
)
NATIVE_TYPE = PowangTask.type
METHOD_NAMES = frozenset(['cancel', 'status', 'wait'])
from ...powang_types import *
from ...error import *
def _dispatch_task(where: str, method: str, arguments: list[PowangAny]) -> PowangAny:
    source = _target(arguments[0])
    _require(source, PowangTask.type, 'native method', method)
    if method == 'wait':
        if len(arguments) > 1:
            return builtin_wait(source, _target(arguments[1]))
        return builtin_wait(source)
    if method == 'cancel':
        return builtin_cancel(source)
    if method == 'status':
        return builtin_task_status(source)
    raise powang_throw(powang_error_identifier_not_found(
        'native method', f'task.{method}',
    ))
