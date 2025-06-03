from typing import Optional as opt

# ERRORS
def error_format(
        name   : opt[str]  = None,
        scope  : opt[str]  = None,
        resume : opt[str]  = None,
        message: opt[list] = None
    ):

    output_message = f'[{name} ERROR]' if name is not None else '[ERROR]'
    if scope is not None:
        output_message += f' (in {scope})'
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

# FORMATS

def error_argc(
        scope: opt[str],
        resume: str,
        expected: int,
        provided: int
    ): return error_format('ARGUMENT', scope,
        resume,
        [f'expected {expected} but {provided} was provided.'])

def error_arguments(
        scope: opt[str],
        inst: str,
        expected: str,
        provided: str
    ): return error_format('ARGUMENT', scope,
        "Invalid arguments",
        [f'{inst} expected {expected.upper()} but {provided.upper()} was provided.'])

def error_type(
        scope: opt[str],
        left: type,
        right: type
    ): return error_format('TYPE', scope,
        'types doesn\'t match',
        [f'{left} --> {right}'])

def error_identifier(
        scope: opt[str],
        var_name: str
    ): return error_format('NAME', scope,
        'doesn\'t exists',
        [f'name -> {var_name}'])

def error_index(scope: opt[str], index: int, max_length: int):
    return error_format('INDEX', scope, 'out of range', [f'access {index} where range is 0 - {max_length - 1}'])

def error_logic(scope: opt[str], resume: str, message: opt[list]):
    return error_format('LOGIC', scope, resume, message)

def error_syntax(resume: str, message: opt[list]):
    return error_format('SYNTAX', None, resume, message)

def error_usage(resume: str, message: opt[list] = None):
    return error_format('USAGE', None, resume, message)

def error_with_line(ln: int, error: str):
    return f'ln -> {ln + 1} {error}'