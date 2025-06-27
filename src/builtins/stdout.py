from ..powang_types import *
from ..error import *

def builtin_stdout(*args: PowangAny) -> PowangInteger:
    """
    Prints out in an standard way any element given.  
    returns the amount of arguments that were passed
    """
    for arg in args:
        if not arg.defined:
            builtin_stdout(PowangString('undefined'))
        elif arg.nova:
            builtin_stdout(PowangString('nova'))
        elif arg.type == PowangContainer.type:
            builtin_stdout(PowangString('['))
            for i, element in enumerate(arg.data):
                if i < len(arg.data) - 1:
                    builtin_stdout(element, PowangString(' '))
                else:
                    builtin_stdout(element)
            builtin_stdout(PowangString(']'))
        else:
            print(arg.data, sep='', end='')
    return PowangInteger(len(args))

def builtin_print(
    list: PowangAny = PowangContainer(),
    sep: PowangAny  = PowangString(' '),
    end: PowangAny  = PowangString('\n')
):
    """
    1:1 python print representation.  
    returns the length of the list
    """
    if list.type != PowangContainer.type:
        list = PowangContainer([list])
    
    assert sep.type == PowangString.type, powang_error_type_match(
        "function print",
        PowangString.type,
        sep.type
    )
    
    assert end.type == PowangString.type, powang_error_type_match(
        "function print",
        PowangString.type,
        end.type
    )
    
    if (length := len(list.data)):
        with_sep = []
        for i in range(length - 1):
            with_sep.append(list.data[i])
            with_sep.append(sep)
        builtin_stdout(*with_sep, list.data[-1], end)
        return PowangInteger(length)
    return builtin_stdout(end)