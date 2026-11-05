from ..powang_types import *
from ..parser import *
from .output import builtin_print

def builtin_inputf(receptor: PowangAny, prompt: PowangString | PowangAny):
    assert prompt.type == PowangString.type, powang_error_type_match(
        'builtin: inputf, prompt',
        PowangString.type,
        prompt.type,
    )
    builtin_print(prompt)
    return builtin_input(receptor)

def builtin_input(receptor: Optional[PowangAny] = None):
    if receptor is None:
        receptor = PowangString()
    assert not receptor.const or receptor.const.can_change, powang_error_constant_assign(
        "builtin: input",
        receptor.type,
        bool(receptor.weak),
    )
    
    try:
        python_input = input()
    except EOFError:
        # stdin closed mid-read: report a clean Powang error, not a traceback.
        raise powang_throw(powang_error_format("INPUT", "builtin: input", "Input stream ended unexpectedly"))
    try:
        if receptor.type == PowangBoolean.type:
            ## Follows PowangBoolean.cast string semantics: a non empty string is true
            receptor.data = len(python_input) > 0
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