from typing import Optional as opt
from .memory import MEMORY

# ====== PRIMIGENOUS ERROR FORMAT =========
def error_format(
        name   : opt[str]  = None,
        resume : opt[str]  = None,
        message: opt[list] = None
    ):

    output_message = (
        f'[{name} ERROR]' if name is not None else '[ERROR]'
    ) + f' (in {MEMORY.peek_scope().name})'

    if resume is not None:
        output_message += ' ' + resume
        
    if message is not None:
        output_message += ':\n'
        for line in message:
            output_message += f'|    {line}\n'
    return output_message

def raise_error(error: str):
    """`assert False, error`"""
    assert False, error

def error_with_line(ln: int, error: str):
    return f'ln {ln + 1} -> {error}'

# FORMATS

def error_argc( # expected X arguments but Y was provided.
    expected: int,
    provided: int
): return error_format('ARGUMENT', (
    "Too many arguments"
    if expected < provided else
    "Not enought arguments"
), [
    f'expected {expected} but arguments {provided} was provided.'
])

def error_type( # types doesn't match: X != Y
    left: str,
    right: str
): return error_format('TYPE', "types doesn't match", [
    f'expected {left} but {right} was provided.'
])

def error_identifier_not_found(
    var_name: str,
    is_inst: bool,
): return error_format('NAME', ("instruction " if is_inst else '') + "doesn't exists", [
    f'{var_name}'
])

def error_out_of_range(
    type: str,
    index: int,
    size: int
): return error_format('INDEX', f'{type} index out of range', [
    f'in length {size - 1} reached index {index}'
])

def error_logic(
    resume: str,
    message: opt[list]
): return error_format('LOGIC', resume,
    message
)

def error_syntax(
    resume: str,
    message: list[str],
): return error_format('SYNTAX', resume, 
    message
)

def error_bad_token(
    token: str,
    expected: str,
    message: list = []
): return error_syntax("bad token", [
    f'expected {expected} but {token} was provided.'
] + message)

def error_operand(
    lhs_type: str,
    operation: str,
    rhs_type: str
): return error_format('OPERATION', "Invalid operation", [
    f"{lhs_type} doesn't support {operation} with {rhs_type}",
])

def error_usage(
    resume: str,
    message: opt[list] = None
): return error_format('USAGE', resume,
    message
)

def error_constant_assign(
    message: opt[list] = None
): return error_format('ASSIGN', "Trying to change a constant value",
    message
)

def error_spread_expression(
    index: int,
    result: str
): return error_format('SPREAD', "Invalid spread expression", [
    f"expected name at {index + 1} to be an identifier",
    f"but {result} was provided.",
])

def error_spread_value(
    result: str
): return error_format('SPREAD', "Invalid spread value", [
    f"expected value to be a list",
    f"but {result} was provided.",
])