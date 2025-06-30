from ..powang_types import *
from ..parser import *

def builtin_stdin(receptor: PowangAny = PowangString()):
    assert not receptor.const or receptor.const.can_change, powang_error_constant_assign(
        "function: stdin",
        receptor.type,
        bool(receptor.weak),
    )
    
    python_input = input()
    try:
        if receptor.type == PowangBoolean.type:
            receptor.data = bool(python_input)
        elif receptor.type == PowangInteger.type:
            receptor.data = int(python_input)
        elif receptor.type == PowangNumber.type:
            receptor.data = float(python_input)
        elif receptor.type == PowangString.type:
            receptor.data = python_input
        elif receptor.type == PowangSome.type:
            try:
                receptor.data = float(python_input)
            except ValueError:
                try:
                    receptor.data = int(python_input)
                except ValueError:
                    if (boolean := {'true': True, 'false': False}.get(python_input)) is not None:
                        receptor.data = boolean        
                    else:
                        receptor.data = python_input
        else:
            raise powang_throw(powang_error_type_match('function: stdin', 'primitive type', receptor.type))
    except ValueError:
        raise powang_throw(powang_error_invalid_input(None, python_input, receptor.type))
        
    receptor.defined = True
    receptor.weak.has_value = True
    if receptor.const:
        receptor.const.can_change = False
    return receptor