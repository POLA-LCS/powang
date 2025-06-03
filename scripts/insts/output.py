from ..runtime.types import *
from ..errors import error_arguments
from ..runtime.memory import STACK

def inst_stdout(*args: PolangAny) -> PolangNumber:
    """### RECURSIVE"""
    for arg in args:
        if arg.type == PolangNumber.type and int(arg.data) == arg.data:
            print(int(arg.data), end='')
        elif arg.type == 'list':
            print('[', end='')
            if len(arg.data) != 0:
                i = 0
                for i in range(len(arg.data) - 1):
                    inst_stdout(arg.data[i], PolangString(' '))
                inst_stdout(arg.data[i + 1])
            print(']', end='')          
        else:
            print(arg.data, end='')
    return PolangNumber(float(len(args)), const=False)

def inst_print(
        args: PolangAny,
        sep = PolangString(' '),
        end = PolangString('\n')
    ):
    """### PARENT"""

    if args.type == 'list':
        length = len(args.data)
        i = 1
        while i < length + length - 1:
            args.data.insert(i, sep)
            i += 2
        return inst_stdout(*args.data, end) - PolangNumber(float(length))
    return inst_stdout(args, end)

def inst_exit(arg: PolangAny):
    assert arg.type == PolangNumber.type, error_arguments(
        STACK[-1], 'exit', PolangNumber.type, arg.type
    )
    
    STACK.clear()
    
    return arg