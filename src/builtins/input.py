from ..powang_types import *
from ..parser import *

def builtin_input(receptor: PowangAny = PowangString()):
    assert not receptor.const or receptor.const.can_change, powang_error_constant_assign(
        "builtin: input",
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
                receptor.data = int(python_input)
                receptor.some = PowangInteger.type
            except ValueError:
                try:
                    receptor.data = float(python_input)
                    receptor.some = PowangNumber.type
                except ValueError:
                    if (boolean := {'true': True, 'false': False}.get(python_input)) is not None:
                        receptor.data = boolean        
                        receptor.some = PowangBoolean.type
                    else:
                        receptor.data = python_input
                        receptor.some = PowangString.type
        else:
            raise powang_throw(powang_error_type_match('builtin: input', 'primitive type', receptor.type))
    except ValueError:
        raise powang_throw(powang_error_invalid_input(None, python_input, receptor.type))
        
    receptor.defined = True
    receptor.weak.has_value = True
    if receptor.const:
        receptor.const.can_change = False
    return receptor

def builtin_system(prompt: PowangAny):
    assert prompt.type == PowangString.type, powang_error_type_match("builtin: system", PowangString.type, prompt.type)
    
    from subprocess import run
    return PowangInteger(run(prompt.data, shell=True).returncode)