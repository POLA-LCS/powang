from .builtin_impl import *
from ..types import InstructionFormat
from ..error import error_out_of_range

def builtin_index(index: PowangAny, list: PowangAny):
    assert list.type == PowangList.type, error_type(
        PowangNumber.type,
        list.type,
    )
    
    assert index.type == PowangNumber.type, error_type(
        PowangNumber.type,
        index.type,
    )
    
    int_index = int(index.data)
    
    assert int_index == index.data, error_type(
        'INTEGER NUMBER',
        index.type,
    )
    
    assert int_index < (length := len(list.data)), error_out_of_range(
        PowangList.type, int_index, length
    )
    
    # assert int_index >= 0, error_out_of_range(
    #     PowangList.type, int_index, length,
    # )

    return list.data[int_index]

BUILTINS: dict[str, InstructionFormat] = {
    'stdout': (1, -1, True , builtin_stdout        ),
    'print':  (1,  3, True , builtin_print         ),
    'exit':   (1,  1, False, builtin_exit          ),

    # Arithmetics
    '+':      (1, -1, False, builtin_operator_plus ),
    '-':      (1, -1, False, builtin_operator_sub  ),
    '*':      (1, -1, False, builtin_operator_mult ),
    '/':      (1, -1, False, builtin_operator_div  ),
    
    'idx': (2, 2, False, builtin_index)
}