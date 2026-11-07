from .output import *
from .system import *
from .input import *
from .info import *
from .file import *
from .iterable import *
from .tasks import builtin_wait, builtin_cancel, builtin_task_status

from .cast import * # HELPER

BUILTINS: dict[str, tuple[int, int, Callable[(...), PowangAny]]] = {
    # OUTPUT
    'print': (1, -1, builtin_print),
    'println': (0, -1, builtin_println),
    'format': (1, -1, builtin_format),
    'printf': (1, -1, builtin_printf),
    'error' : (1, -1, builtin_error ),
    'fail'  : (2, -1, builtin_fail  ),
    'system': (1, -1, builtin_system),

    # INPUT
    'input' : (0,  1, builtin_input),
    'inputf': (2,  2, builtin_inputf),

    # INFO
    'typeof': (1,  1, builtin_typeof),
    'typedeep': (1, 1, builtin_typedeep),

    # ITERABLE
    'size'  : (1, -1, builtin_size),

    # FILE IO
    'open' : (1, 2, builtin_open ),
    'close': (1, 1, builtin_close),
    'write': (1, 2, builtin_write),
    'read' : (1, 1, builtin_read ),

    # TASKS
    'wait'       : (1, 2, builtin_wait       ),
    'cancel'     : (1, 1, builtin_cancel     ),
    'task_status': (1, 1, builtin_task_status),
}