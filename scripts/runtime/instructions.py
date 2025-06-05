from ..types import PowangCallable
from .instruction_impl import *
from .keywords_impl.boolean import inst_keyword_not

INSTRUCTIONS: dict[str, PowangCallable] = {
    'stdout': PowangCallable(1, -1, True,  inst_stdout       ),
    'print':  PowangCallable(1, 3,  True,  inst_print        ),
    'exit':   PowangCallable(1, 1,  False, inst_exit         ),
    '+':      PowangCallable(1, -1, False, inst_operator_plus),
    '-':      PowangCallable(1, -1, False, inst_operator_sub ),
    '*':      PowangCallable(1, -1, False, inst_operator_mult),
    '/':      PowangCallable(1, -1, False, inst_operator_div ),
    'not': PowangCallable(1, 1, False, inst_keyword_not),
    # 'stdin': (2, False, inst_stdin),
}