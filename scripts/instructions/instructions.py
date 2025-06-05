from typing import Callable
from ..types import PolangAny, PolangError
from ..circular import circular_interpret_line
from ..lexing.token import *
from ..error import *

class Instruction:
    def __init__(self, min_argc: int, max_argc: int, is_flex: bool, function: Callable[(...), PolangAny | PolangError]):
        self.min_argc = min_argc
        self.max_argc = max_argc
        self.is_flex = is_flex
        self.function = function

from .output import *
from .input import *
from .operations import *

INSTRUCTIONS: dict[str, Instruction] = {
    'stdout': Instruction(1, -1, True, inst_stdout),
    'print':  Instruction(1, 3, True, inst_print),
    'exit':   Instruction(1, 1, False, inst_exit),
    '+': Instruction(1, -1, False, inst_operator_plus),
    '-': Instruction(1, -1, False, inst_operator_sub),
    '*': Instruction(1, -1, False, inst_operator_mult),
    '/': Instruction(1, -1, False, inst_operator_div),
    'false': Instruction(0, 0, False, lambda: PolangNumber(0.0)),
    'true': Instruction(0, 0, False, lambda: PolangNumber(1.0))
    # 'stdin': (2, False, inst_stdin),
}

def keyword_if(expression: Token, code: Token):
    assert expression.type == TokenType.EXPRESSION, error_syntax(
        "Expected valid convert to boolean expression", [
            f"recieved {expression.type}",
            f"{expression.value} was provided."
        ]
    )
    
    assert code.type == TokenType.EXPRESSION, error_syntax(
        "Expected valid code expression", [
            f"recieved {code.type}",
            f"{code.value}"
        ]
    )

    result = circular_interpret_line(expression.value)
    
    execute = False
    if result.type == PolangNumber.type:
        execute = result.data != 0 
    elif result.type == PolangNov.type:
        execute = False
    elif result.type == PolangList.type or result.type == PolangString.type:
        execute = len(result.data) != 0
    else:
        raise_error(error_syntax(
            "Cannot evaluate to boolean expression", [
                f"recieved {expression.type}",
                f"{expression.value} was provided."
        ]))
        
    if execute:
        return circular_interpret_line(code.value)
    return PolangNov()

KEYWORDS: dict[str, Instruction] = {
    'if': Instruction(2, 2, True, keyword_if)
}