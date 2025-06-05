from ...types import *
from ...error import error_operand
from ...memory import MEMORY

def calculate_operation_single(operation_string: str, arg: PowangAny):
    if arg.type == PowangList.type:
        return calculate_operation(operation_string, *arg.data)
    if arg.type == PowangNumber.type and operation_string == 'substraction':
        return -arg.data
    return arg

def calculate_operation(operation_string: str, *args: PowangAny):
    if len(args) == 1:
        return calculate_operation_single(operation_string, *args)
    operation_string += '_'
    if len(args) == 0:
        return PowangNov()
    result_sum = args[0]
    for arg in args[1:]:
        complete_operation = operation_string + arg.type
        assert result_sum.has(complete_operation), error_operand(
            result_sum.type,
            complete_operation.split('_')[0],
            arg.type
        )
        result_sum = result_sum.__getattribute__(complete_operation)(arg)
    return result_sum

def inst_operator_plus(*args: PowangAny):
    return calculate_operation('addition', *args)

def inst_operator_mult(*args: PowangAny):
    return calculate_operation('multiplication', *args)

def inst_operator_div(*args: PowangAny):
    return calculate_operation('division', *args)

def inst_operator_sub(*args: PowangAny):
    return calculate_operation('substraction', *args)

def inst_operator_equ(*args: PowangAny):
    return calculate_operation('equal', *args)