from ..powang_types import *
from ..error import *

def builtin_size(*args: PowangAny):
    """Returns the sumatory of the sizes"""
    size_result = PowangInteger(0)
    for i, arg in enumerate(args):
        assert arg.defined, powang_error_undefined_argument(
            'function: size',
            i + 1,
            arg.type,
        )
        
        if arg.type == PowangSome.type:
            arg = PowangTypeMap(arg.some)(arg.data)
        
        assert (size := arg.size()) is not None, powang_error_not_iterable('function: size', arg.type, [
            f"in argument {i + 1}"
        ])
        size_result.data += size.data
    return size_result

def builtin_typeof(arg: PowangAny):
    return PowangString(arg.type)