from ..error import *
from ..powang_types import *

def builtin_size(*args: PowangAny):
    """Returns the sumatory of the sizes"""
    size_result = PowangInteger(0)
    for i, arg in enumerate(args):
        assert arg.defined, powang_error_undefined_argument(
            'function: size',
            i + 1,
            arg.type,
        )
        
        if arg.type == PowangAnyType.type:
            arg = PowangUnwrapAny(arg)
        
        size = arg.size()
        if size is None:
            raise powang_throw(powang_error_not_iterable('function: size', arg.type, [
                f"in argument {i + 1}"
            ]))
        size_result.data += size.data
    return size_result