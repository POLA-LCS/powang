from typing import Optional

def powang_throw(format: str):
    """`assert 0, format`"""
    assert 0, format
    return Exception() # for type checking problemso

def powang_error_format(
    name: Optional[str] = None,
    where: Optional[str] = None,
    resume: Optional[str] = None,
    messages: list    [str] = []
):
    error_message: str = '[ERROR]' if not name else f'[{name} ERROR]'
    if where:
        error_message += f' (in {where})'
    if resume:
        error_message += f' ' + resume
    if messages:
        error_message += ':'
        for msg in messages:
            error_message += '\n      | ' + msg
    return error_message
        
def powang_error_syntax(
    where: Optional[str],
    resume: Optional[str],
    messages: list[str] = []
):  return powang_error_format('SYNTAX', where, resume, messages)

def powang_error_syntax_unexpected_end(
    where: Optional[str],
    tokenizer: object
):  return powang_error_syntax(where, "Unexpected end of input", [
    tokenizer.data[tokenizer.row] # type: ignore
])

def powang_error_syntax_unexpected_token(
    where: Optional[str],
    encountered: str,
    expected: str,
):  return powang_error_syntax(where, f"Unexpected token", [
    f"expected {expected}",
    f"but {encountered} was encountered"
])

def powang_error_identifier_not_found(
    where     : Optional[str],
    identifier: str,
    messages  : list[str] = []
):  return powang_error_format('IDENTIFIER', where, "doens't exists", [
    identifier,
] + messages)
    
def powang_error_identifier_type(
    where     : Optional[str],
    type_id   : str,
    messages  : list[str] = []
):  return powang_error_format('TYPE', where, "Identifier does not name a valid type", [
    type_id
] + messages)

def powang_error_type_match(
    where     : Optional[str],
    expected  : str,
    encounter : str,
):  return powang_error_format('TYPE', where, "Types doesn't match", [
    f"expected {expected}",
    f"but {encounter} was encounter"
])

def powang_error_strong_nova_assign(
    where : Optional[str],
    type : str,
):  return powang_error_format('ASSIGN', where, "Weak assign to strong value", [
    f"trying to assign nova to a strong {type}"
])

def powang_error_undefined_reference(
    where      : Optional[str],
    undefined  : str,
):  return powang_error_format('REFERENCE', where, f"Undefined reference: {undefined}\n",)

def powang_error_undefined_argument(
    where     : Optional[str],
    parameter : int,
    type  : str,
):  return powang_error_format('CALL', f'function call: {where}',
    'undefined parameter', [
    f"parameter number {parameter}",
    f"is an undefined value of type {type}"
])

def powang_error_invalid_input(
    where     : Optional[str],
    value     : str,
    type      : str,
):  return powang_error_format('INPUT', where, 'Invalid input for specified type', [
    f"cannot convert {value}",
    f"into type {type}",
])

def powang_error_prefix_operator(
    where     : Optional[str],
    operator  : str,
):  return powang_error_format('PREFIX', where, 'Invalid prefix', [
    f'"{operator}" is not a valid prefix'
])

def powang_error_invalid_type_for_prefix_operator(
    where    : Optional[str],
    operator : str,
    type     : str,
):  return powang_error_format('PREFIX', where, 'Unsupported prefix', [
    f'for prefix "{operator}"',
    f'and type "{type}"',
])

def powang_error_index_out_of_range(
    index : int,
    size  : int,
):  return powang_error_format('INDEX', None, 'Out of range', [
    f"index {index} out of range [0; {size})"
])

def powang_error_format_strings_multiple_expressions(
    string: str,
):  return powang_error_format(
    'FORMAT',
    'string format',
    'invalid format string due to multiple expressions', [
        string,
        ' ' * string.index(';') + '^'
])

def powang_error_format_invalid_cast(
    where    : Optional[str],
    cast_to  : str,
    to_cast  : str,
    explicit : bool,
): return powang_error_format(
    'TYPE',
    where,
    f'Invalid {"explicit" if explicit else ''} cast types', [
        f"unable to cast {to_cast} to {cast_to}"
])

def powang_error_constant_assign(
    where : Optional[str],
    type  : str,
    weak  : bool,
):  return powang_error_format('ASSIGN', where, "constant assign", [
    f"trying to assign into a {f"not changeable weak" if weak else ''} const {type}"
])

def powang_error_unsupported_operation(
    where    : Optional[str],
    left     : str,
    operator : str,
    right    : str
):  return powang_error_format('OPERATION', where, "Invalid operation", [
    f"Unsupported \"{operator}\" operation between {left} and {right}",
])