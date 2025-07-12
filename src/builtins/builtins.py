from .output import *
from .system import *
from .input import *
from .info import *
from .file import *
from .iterable import *

from .cast import * # HELPER

BUILTINS: dict[str, tuple[int, int, Callable[(...), PowangAny]]] = {
    # OUTPUT
    'output': (1, -1, builtin_output),
    'format': (1, -1, builtin_format),
    'printf': (1, -1, builtin_printf),
    'error' : (1, -1, builtin_error ),
    'system': (1, -1, builtin_system),

    # INPUT
    'input' : (0,  1, builtin_input),

    # INFO
    'typeof': (1,  1, builtin_typeof),

    # ITERABLE
    'size'  : (1, -1, builtin_size),

    # FILE IO
    'open' : (1, 2, builtin_open ),
    'close': (1, 1, builtin_close),
    'write': (1, 1, builtin_write),
    'read' : (1, 1, builtin_read ),
}