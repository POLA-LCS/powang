from typing import Optional as opt

# ERRORS
def error_format(name: opt[str] = None, scope: opt[str] = None, resume: opt[str] = None, message: opt[str] = None):
    output_error_string = f'[{name} ERROR]' if name is not None else '[ERROR]'
    if scope is not None:
        output_error_string += f' (in {scope})'
    if resume is not None:
        output_error_string += ' ' + resume
    if message is not None:
        output_error_string += f':\n    {message}'
    return output_error_string + '\n'
    
def RAISE(error: str):
    """`assert 0, error`"""
    assert 0, error
    
# ERROR formatS
def error_format_ARGC(scope: opt[str], resume: str, expected: int | str, provided: int):
    return error_format('ARG COUNT', scope, resume, f'expected {expected} but {provided} was provided.')

def error_format_ARGV(scope: opt[str], inst_or_macro: str, expected: str, provided: str):
    return error_format('ARG TYPE', scope, "Invalid arguments", f'{inst_or_macro} expected {expected.upper()} but {provided.upper()} was provided.')

def error_format_TYPE(scope: opt[str], left: type, right: type):
    return error_format('TYPE', scope, 'types doesn\'t match', f'{left} --> {right}')

def error_format_name(scope: opt[str], var_name: str, ):
    return error_format('NAME', scope, 'doesn\'t exists', f'var -> {var_name}')

def error_format_INDEX(scope: opt[str], index: int, max_length: int):
    return error_format('INDEX', scope, 'out of range', f'access {index} where range is 0 - {max_length - 1}')
    
def error_format_LOGIC(scope: opt[str], resume: str, message: str):
    return error_format('LOGIC', scope, resume, message)

def error_format_syntax(resume: str, message: str):
    return error_format('SYNTAX', None, resume, message)

def INLINE_ERROR(ln: int, error: str):
    return f'ln -> {ln + 1} {error}'