from ...types import *
from ...error import error_type
from ...memory import SCOPE_STACK

def inst_stdout(*args: PowangAny) -> PowangNumber:
    """### RECURSIVE"""
    for arg in args:
        if arg.type == PowangNumber.type and int(arg.data) == arg.data:
            print(int(arg.data), end='')
        elif arg.type == 'list':
            print('[', end='')
            if len(arg.data) != 0:
                i = 0
                for i in range(len(arg.data) - 1):
                    inst_stdout(arg.data[i], PowangString(' '))
                inst_stdout(arg.data[(i + 1) if i else i])
            print(']', end='')          
        elif arg.type == 'nov':
            print('nov', end='')
        else:
            print(arg.data, end='')
    return PowangNumber(float(len(args)), const=False)

def inst_print(
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
        return inst_stdout(*args.data, end).substraction_number(PowangNumber(float(length)))
    return inst_stdout(args, end)

def inst_exit(arg: PowangAny):
    SCOPE_STACK.append('exit')
    assert arg.type == PowangNumber.type, error_type(
        PowangNumber.type, arg.type
    )
    
    SCOPE_STACK.clear()
    
    return arg