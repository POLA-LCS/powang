from ...types import *
from ...lexing.token import *
from ...interpret import interpret_line
from ...runtime import SCOPE
from ...lexing import tokenize_line

def evaluate_boolean_expression(value: PowangAny | PowangError) -> bool:
    if value.type == PowangBool.type:
        return value.data
    if value.type == PowangNov.type or value.type == PowangError.type:
        return False
    if value.type == PowangNumber.type:
        return (value.data != 0)
    if value.type == PowangString.type or value.type == PowangList.type:
        return len(value.data) != 0
    if value.type == PowangStruct.type:
        return evaluate_boolean_expression(interpret_line(SCOPE.depth, tokenize_line(0, value.methods['bool'].data)))
    return False

def builtin_keyword_not(value: PowangAny):
    return PowangNumber(0.0 if evaluate_boolean_expression(value) else 1.0)