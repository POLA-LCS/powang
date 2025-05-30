from typing import Optional as opt

# ERRORS
def ERROR_FORMAT(name: opt[str] = None, scope: opt[str] = None, resume: opt[str] = None, message: opt[str] = None):
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
    
# ERROR FORMATS
def ERROR_FORMAT_ARGC(scope: opt[str], resume: str, expected: int | str, provided: int):
    return ERROR_FORMAT('ARG COUNT', scope, resume, f'expected {expected} but {provided} was provided.')

def ERROR_FORMAT_ARGV(scope: opt[str], inst_or_macro: str, expected: str, provided: str):
    return ERROR_FORMAT('ARG TYPE', scope, "Invalid arguments", f'{inst_or_macro} expected {expected.upper()} but {provided.upper()} was provided.')

def ERROR_FORMAT_TYPE(scope: opt[str], left: type, right: type):
    return ERROR_FORMAT('TYPE', scope, 'types doesn\'t match', f'{left} --> {right}')

def ERROR_FORMAT_NAME(scope: opt[str], var_name: str, ):
    return ERROR_FORMAT('NAME', scope, 'doesn\'t exists', f'var -> {var_name}')

def ERROR_FORMAT_INDEX(scope: opt[str], index: int, max_length: int):
    return ERROR_FORMAT('INDEX', scope, 'out of range', f'access {index} where range is 0 - {max_length - 1}')
    
def ERROR_FORMAT_LOGIC(scope: opt[str], resume: str, message: str):
    return ERROR_FORMAT('LOGIC', scope, resume, message)

def ERROR_FORMAT_SYNTAX(resume: str, message: str):
    return ERROR_FORMAT('SYNTAX', None, resume, message)

def INLINE(ln: int, error: str):
    return f'ln -> {ln + 1} {error}'