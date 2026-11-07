import re
from ..powang_types import *
from ..error import *
from .cast import explicitCastString

def builtin_print(*args: PowangAny) -> PowangInteger:
    """
    Prints each argument without adding a newline.
    Returns the number of arguments.
    """
    
    for arg in args:
        casted_arg = explicitCastString(arg)
        if arg.type == PowangObjectType.type and casted_arg is None:
            casted_arg = PowangString(f"<type: {arg.type_name}>")
        if casted_arg is None:
            raise powang_throw(powang_error_invalid_cast(
                "function: print",
                PowangString.type,
                arg.type,
                True,
            ))
        print(casted_arg.data, sep='', end='')
    return PowangInteger(len(args))

def builtin_println(*args: PowangAny) -> PowangInteger:
    """Prints each argument and then a newline."""
    builtin_print(*args)
    print()
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
        casted = explicitCastString(arg)
        if casted is None:
            raise powang_throw(powang_error_invalid_cast(
                'function: format', PowangString.type, arg.type, True
            ))
        string_args.append(casted.data)

    ITERABLE_TYPES = {PowangArray.type, PowangString.type, PowangMap.type}

    def replace_handler_iterate(match: re.Match[str]):
        index = int(match.group(1))
        sep = match.group(2)
        
        if not (0 <= index < len(args)):
            raise powang_throw(powang_error_index_out_of_range(index, len(args)))

        arg = args[index]
        if arg.type not in ITERABLE_TYPES:
            ## Scalars have nothing to iterate, substitute their string form directly
            return string_args[index]

        items: list[str] = []
        for item in arg.iterate().data:
            casted = explicitCastString(item)
            if casted is None:
                raise powang_throw(powang_error_invalid_cast(
                    'function: format', PowangString.type, item.type, True
                ))
            items.append(casted.data)
        return sep.join(items)
    
    def replace_handler(match: re.Match[str]):
        index = int(match.group(1))
        
        if not (0 <= index < len(args)):
            raise powang_throw(powang_error_index_out_of_range(index, len(args)))

        return string_args[index]

    result = PowangString()
    result.data = PowangString(re.sub(r"\{(\d+)\/([^}]*)\}", replace_handler_iterate, format_string.data)).data
    result.data = PowangString(re.sub(r"\{(\d+)\}", replace_handler, result.data)).data
    return result
    
def builtin_printf(
    format_string: PowangString | PowangAny,
    *args: PowangAny,
):  return builtin_print(builtin_format(format_string, *args))

def builtin_fail(
    kind: PowangString | PowangAny,
    message: PowangString | PowangAny,
    *args: PowangString,
) -> PowangErrorValue:
    ## Value constructor counterpart to `error(...)`: returns an error value
    ## instead of raising, so `?` can propagate it from `T?` functions.
    assert kind.type == PowangString.type, powang_error_type_match('builtin: fail, kind', PowangString.type, kind.type)
    assert message.type == PowangString.type, powang_error_type_match('builtin: fail, message', PowangString.type, message.type)
    for arg in args:
        assert arg.type == PowangString.type, powang_error_type_match('builtin: fail, argument', PowangString.type, arg.type)
    created_error = powang_error_format(kind.data, 'builtin: fail', message.data, [arg.data for arg in args])
    return PowangErrorValue.from_error(created_error)

def builtin_error(
    message: PowangString | PowangAny,
    *args: PowangString,
):  
    assert message.type == PowangString.type, powang_error_type_match('builtin: error, message', PowangString.type, message.type)
    for arg in args:
        assert arg.type == PowangString.type, powang_error_type_match('builtin: error, argument', PowangString.type, arg.type)
    raise powang_throw(powang_error_format("USER", 'builtin: error', message.data, [arg.data for arg in args]))