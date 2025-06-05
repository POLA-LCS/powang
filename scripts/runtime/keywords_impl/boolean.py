from ...lexing.token import *
from ...error import *
from ...circular import circular_interpret_line, circular_process_value
from ...types import *

def evaluate_boolean_expression(value: PowangAny | PowangError) -> bool:
    if value.type == PowangNov.type or value.type == PowangError.type:
        return False
    if value.type == PowangNumber.type:
        return (value.data != 0)
    if value.type == PowangString.type or value.type == PowangList.type:
        return len(value.data) != 0
    if value.type == PowangStruct.type:
        return evaluate_boolean_expression(value.methods['bool'].function())
    return False

from ..skip_condition import *
def keyword_if(expression: Token):
    if expression.type == TokenType.EXPRESSION:
        result = circular_interpret_line(expression.value)
    else:
        result = circular_process_value([expression])[0]

    if not evaluate_boolean_expression(result): # jump to the next END
        SKIP_CONDITION.append(lambda domain, _: not (domain.type == TokenType.KEYWORD and domain.value == 'end'))
    
    return PowangNov()

def inst_keyword_not(value: PowangAny):
    return PowangNumber(0.0 if evaluate_boolean_expression(value) else 1.0)