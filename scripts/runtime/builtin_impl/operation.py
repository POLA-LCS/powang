from ...types import *
from ...error import error_operand

def calculate_operation_single(operation_string: str, arg: PowangAny) -> PowangAny:
    if arg.type == PowangList.type:
        return calculate_operation(operation_string, *arg.data)
    if arg.type == PowangNumber.type and operation_string == 'substraction':
        return PowangNumber(-arg.data)
    return arg

def calculate_operation(operation_string: str, *args: PowangAny):
    if len(args) == 1:
        return calculate_operation_single(operation_string, *args)
    if len(args) == 0:
        return PowangNov()
    result_sum = args[0]
    for arg in args[1:]:
        complete_operation = operation_string + '_' + arg.type
        assert result_sum.has(complete_operation), error_operand(
            result_sum.type,
            complete_operation,
            arg.type
        )
        result_sum = result_sum.__getattribute__(complete_operation)(arg)
    return result_sum

# ====== ARITHMETICS =========
def builtin_operator_plus(*args: PowangAny):
    return calculate_operation('addition', *args)

def builtin_operator_mult(*args: PowangAny):
    return calculate_operation('multiplication', *args)

def builtin_operator_div(*args: PowangAny):
    return calculate_operation('division', *args)

def builtin_operator_sub(*args: PowangAny):
    return calculate_operation('substraction', *args)