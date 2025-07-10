import re
from ..powang_types import *
from ..error import *
from .cast import explicitCastString

def builtin_output(*args: PowangAny) -> PowangInteger:
    """
    Prints out in an standard way any element given.  
    returns the amount of arguments that were passed
    """
    
    for arg in args:
        casted_arg = explicitCastString(arg)
        if arg.type == PowangObjectType.type and casted_arg is None:
            casted_arg = PowangString(f"<type: {arg.type_name}>")
        assert casted_arg is not None, powang_error_invalid_cast(
            "function: output",
            PowangString.type,
            arg.type,
            True,
        )
        print(casted_arg.data, sep='', end='')
    return PowangInteger(len(args))

def builtin_format(
    format_string: PowangString | PowangAny,
    *args: PowangAny,
):
    assert format_string.type == PowangString.type, powang_error_type_match(
        'function: format',
        PowangString.type,
        format_string.type,
    )
    
    string_args: list[str] = []
    for arg in args:
        assert (casted := explicitCastString(arg)) is not None, powang_error_invalid_cast(
            'function: format', PowangString.type, arg.type, True
        )
        string_args.append(casted.data)

    def replace_handler_iterate(match: re.Match[str]):
        index = int(match.group(1))
        sep = match.group(2)
        
        assert (0 <= index < len(args)), powang_error_index_out_of_range(index, len(args))

        items: list[str] = []
        arg = args[index]
        for item in arg.iterate().data:
            assert (casted := explicitCastString(item)) is not None, powang_error_invalid_cast(
                'function: format', PowangString.type, item.type, True
            )
            items.append(casted.data)
        return sep.join(items)
    
    def replace_handler(match: re.Match[str]):
        index = int(match.group(1))
        
        assert (0 <= index < len(args)), powang_error_index_out_of_range(index, len(args))

        return string_args[index]

    result = PowangString()
    result.data = PowangString(re.sub(r"\{(\d+)\/([^}]*)\}", replace_handler_iterate, format_string.data)).data
    result.data = PowangString(re.sub(r"\{(\d+)\}", replace_handler, result.data)).data
    return result
    
def builtin_printf(
    format_string: PowangString | PowangAny,
    *args: PowangAny,
):  return builtin_output(builtin_format(format_string, *args))

def builtin_error(
    message: PowangString | PowangAny,
    *args: PowangString,
):  
    assert message.type == PowangString.type, powang_error_type_match('builtin: error, message', PowangString.type, message.type)
    for arg in args:
        assert arg.type == PowangString.type, powang_error_type_match('builtin: error, argument', PowangString.type, arg.type)
    raise powang_throw(powang_error_format("USER", 'builtin: error', message.data, [arg.data for arg in args]))