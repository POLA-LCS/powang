from ..powang_types import *
from ..error import powang_error_format
from ..lexer.tokenizer import *
from ..parser import *

def builtin_stdin(value: PowangAny):
    python_input = input()
    try:
        if value.type == PowangBoolean.type:
            value.data = bool(python_input)
        elif value.type == PowangInteger.type:
            value.data = int(python_input)
        elif value.type == PowangNumber.type:
            value.data = float(python_input)
        elif value.type == PowangString.type:
            value.data = python_input
        elif value.type == PowangSome.type:
            try:
                value.data = float(python_input)
            except ValueError:
                try:
                    value.data = int(python_input)
                except ValueError:
                    if (boolean := {'true': True, 'false': False}.get(python_input)) is not None:
                        value.data = boolean        
                    else:
                        value.data = python_input
        else:
            raise powang_throw(powang_error_type_match('funcion: stdin', 'primitive type', value.type))
    except ValueError:
        raise powang_throw(powang_error_invalid_input(None, python_input, value.type))
    value.defined = True
    value.nova = False
    return value