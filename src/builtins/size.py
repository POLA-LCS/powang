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
        
        if arg.type == PowangContainer.type or arg.type == PowangString.type:
            size_result.data += len(arg.data)
        else:
            assert arg.type == PowangUserType.type, powang_error_type_match(
                'function: size',
                'sizeable type',
                arg.type,
            )
            assert 'size' in arg.methods, powang_error_identifier_not_found(
                'User Type Method',
                'size', [
                    f'trying to get the size of a user type "{arg.name}"',
                    "but was not founded"
                ]
            )
            return PowangNova()
    return size_result