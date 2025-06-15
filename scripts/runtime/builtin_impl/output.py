from ...types import *
from ...error import error_type
from ...memory import SCOPE

def builtin_stdout(*args: PowangAny) -> PowangNumber:
    """### RECURSIVE"""
    for arg in args:
        if arg.type == PowangNumber.type:
            print(arg.get_number(), end='')
        elif arg.type == 'list':
            print('[', end='')
            if (length := len(arg.data)) == 1:
                builtin_stdout(arg.data[0])
            elif length != 0:
                i = 0
                for i in range(length - 1):
                    builtin_stdout(arg.data[i], PowangString(' '))
                builtin_stdout(arg.data[i + 1])
            print(']', end='')          
        elif arg.type == 'nov':
            print('nov', end='')
        elif arg.type == 'bool':
            print({True: 'true', False: 'false'}[arg.data], end='')
        else:
            print(arg.data, end='')
    return PowangNumber(float(len(args)), const=False)

def builtin_print(
        args: PowangAny,
        sep = PowangString(' '),
        end = PowangString('\n')
    ):
    """### PARENT"""
    
    if args.type == 'list':
        length = len(args.data)
        i = 1
        while i < length + length - 1:
            args.data.insert(i, sep)
            i += 2
        return builtin_stdout(*args.data, end).substraction(PowangNumber(float(length)))
    return builtin_stdout(args, end)

def builtin_exit(arg: PowangAny):
    SCOPE.push('exit', False)
    assert arg.type == PowangNumber.type, error_type(
        PowangNumber.type, arg.type
    )
    
    while SCOPE.depth > 0:
        SCOPE.pop()
    
    return arg