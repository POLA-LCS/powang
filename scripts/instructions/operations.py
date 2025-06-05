from ..types import *
from ..error import error_operand
from ..memory import MEMORY


def calculate_operation_single(operation_string: str, arg: PolangAny):
    if arg.type == 'list':
        return calculate_operation(operation_string, *arg.data)
    return arg

def calculate_operation(operation_string: str, *args: PolangAny):
    if len(args) == 1:
        calculate_operation_single(operation_string, *args)
    operation_string += '_'
    if len(args) == 0:
        return PolangNov()
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

def inst_operator_plus(*args: PolangAny):
    return calculate_operation('addition', *args)

def inst_operator_mult(*args: PolangAny):
    return calculate_operation('multiplication', *args)

def inst_operator_div(*args: PolangAny):
    return calculate_operation('division', *args)

def inst_operator_sub(*args: PolangAny):
    return calculate_operation('substraction', *args)