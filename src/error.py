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
            error_message += '\n\t' + msg
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
    encountered: str,
    expected: str,
    where: Optional[str]
):  return powang_error_syntax(None, f"Unexpected token", [
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
    where      : Optional[str],
    var_name   : str,
):  return powang_error_format('ASSIGN', where, "Weak assign to strong value", [
    f"trying to assign nova to the strong variable '{var_name}'"
])

def powang_error_undefined_value(
    where      : Optional[str],
    left_side  : str,
    right_side : str,
):  return powang_error_format('ASSIGN', where, "Undefined reference", [
    f"trying to assign the undefined variable '{right_side}' to '{left_side}'",
])

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