from re import match, Pattern
from ..powang_types import *
from ..error import *
from .cast import explicit_cast_string

def builtin_stdout(*args: PowangAny) -> PowangInteger:
    """
    Prints out in an standard way any element given.  
    returns the amount of arguments that were passed
    """
    
    for arg in args:
        assert (casted_arg := explicit_cast_string(arg)) is not None, powang_error_format_invalid_cast(
            "function: stdout",
            PowangString.type,
            arg.type,
            True,
        )
        print(casted_arg.data, sep='', end='')
    return PowangInteger(len(args))

def builtin_print(
    array: PowangAny = PowangArray(),
    sep: PowangAny  = PowangString(' '),
    end: PowangAny  = PowangString('\n')
):
    """
    1:1 python print representation.  
    returns the length of the array
    """
    if not array.defined:
        array = PowangArray([array])  
    elif not array.weak.has_value:
        array = PowangArray([PowangString('nova')])
    elif array.type != PowangArray.type:
        array = PowangArray([array])

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
    
    if (length := len(array.data)):
        with_sep = []
        if length:
            for i in range(length - 1):
                with_sep.append(explicit_cast_string(array.data[i]))
                with_sep.append(sep)
            builtin_stdout(*with_sep, array.data[-1], end)
        return PowangInteger(length)
    return builtin_stdout(end)

def builtin_stdfmt(
    format_string: PowangString | PowangAny,
    *args: PowangAny,
):
    assert format_string.type == PowangString.type, powang_error_type_match(
        'function: format',
        PowangString.type,
        format_string.type,
    )
    
    argc = len(args)
    pattern = r'\{\d+\}'
    result: str = ''
    i: int = 0
    # while i < len(format_string.data):
    group = match(pattern, format_string.data)
    if group is not None:
        print(group)
        format_string.data = format_string.data[i + group.span()[1]:]
        print(format_string.data)
    group = match(pattern, format_string.data)
    if group is not None:
        print(group)
        format_string.data = format_string.data[i + len(group.string):]
            # string = group.string

            # result += format_string.data[i:i + len(string)]
    return PowangString(result)