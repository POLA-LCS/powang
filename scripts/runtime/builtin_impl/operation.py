from ...types import *
from ...error import error_operand, error_logic

def calculate_operation_single(operation_string: OperationName, arg: PowangAny) -> PowangAny:
    if operation_string == 'addition':
        return arg
    if operation_string == 'substraction':
        if arg.type == PowangBool.type:
            return PowangBool(not arg.data)
        if arg.type == PowangNumber.type:
            return PowangNumber(-arg.data)
        if arg.type == PowangString.type:
            return PowangString(arg.data[::-1])
        if arg.type == PowangList.type:
            return PowangList(arg.data[::-1])
    return PowangNov()

def calculate_operation(operation_string: OperationName, *args: PowangAny):
    if len(args) == 1:
        result = calculate_operation_single(operation_string, *args)
        assert result.type != PowangNov.type, error_operand(
            args[0].type,
            operation_string,
            'prefix',
        )
        return result

    operation_result = args[0]
    
    for arg in args[1:]:
        operation: OperationFunc = {
            'addition': operation_result.addition,
            'substraction': operation_result.substraction,
            'multiplication': operation_result.multiplication,
            'division': operation_result.division,
        }[operation_string]
        result = operation(arg)

        assert operation_result.type != PowangNov.type, error_operand(
            operation_result.type,
            operation_string,
            arg.type
        )
        
        operation_result = result
    return operation_result

# ====== ARITHMETICS =========
def builtin_operator_plus(*args: PowangAny):
    return calculate_operation('addition', *args)

def builtin_operator_mult(*args: PowangAny):
    return calculate_operation('multiplication', *args)

def builtin_operator_div(*args: PowangAny):
    return calculate_operation('division', *args)

def builtin_operator_sub(*args: PowangAny):
    return calculate_operation('substraction', *args)