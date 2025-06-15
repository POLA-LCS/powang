from ...lexing.token import Token, TokenType, TokenNameValue
from ...interpret import process_values, interpret_line
from ...types import *
from ...memory import SCOPE, SCOPE_LABELS
from ...runtime.external_condition import *
from ...error import *

IF_EXPRESSION  = 'if expression'
IF_STATEMENT   = 'if statement'
ELSE_STATEMENT = 'else statement'

def evaluate_expression(expression: PowangAny):
    if expression.type == PowangNov.type:
        return False
    if expression.type == PowangBool.type:
        return expression.state
    if expression.type == PowangNumber.type:
        return expression.data != 0.0
    if expression.type == PowangString.type or expression.type == PowangList.type:
        return len(expression.data) > 0
    return False

def keyword_if(expression: Token):
    SCOPE.push(IF_EXPRESSION, False)
    if expression.type == TokenType.EXPRESSION:
        result = interpret_line(SCOPE.depth, expression.value)
    else:
        result = process_values(SCOPE.depth, [expression])[0]


    if not evaluate_expression(result):
        EXTERNAL_CONDITION.append(
            lambda indent, domain: (
                indent > SCOPE.depth or
                not (domain.type == TokenType.KEYWORD and domain.value in ['else', 'end'])
            )
        )
        return PowangBool(False)
    SCOPE.push(IF_STATEMENT, True)
    return PowangBool(True)

def keyword_else(expression: Token | None = None):
    if SCOPE.peek_name()[0] == IF_STATEMENT:
        EXTERNAL_CONDITION.append(
            lambda indent, domain: (
                indent > SCOPE.depth or
                not (domain.type == TokenType.KEYWORD and domain.value == 'end')
            )
        )
    else:
        assert SCOPE.peek_name()[0] == IF_EXPRESSION, error_syntax(
            "Encounter else without a corresponding if", [
                'Perhaps you missed an "end"'
            ]
        )

        if expression is not None:
            return keyword_if(expression)

        SCOPE.push(ELSE_STATEMENT, True)
    return PowangNov()

def keyword_end():
    assert SCOPE.depth > 0, error_syntax(
        "there's no active scope to end", [
            "trying to end global scope",
            'perhaps you meant "exit"?'
        ]
    )
    
    if SCOPE.peek_name()[0] == IF_EXPRESSION:
        SCOPE.pop(1)
    elif SCOPE.peek_name()[0] in [IF_STATEMENT, ELSE_STATEMENT]:
        SCOPE.pop(2)
    else:
        SCOPE.pop(1)
    return PowangNov()

def keyword_label(name: Token):
    assert name.type == TokenType.IDENTIFIER, error_syntax(
        "label's name must be an identifier", [
            f"expected {TokenType.to_str(TokenType.IDENTIFIER)}",
            f"but {TokenType.to_str(name.type)}"
        ]
    )
    
    assert name.value not in SCOPE_LABELS, error_logic(
        "redefinition of a label", [
            f"the label {name.value} already exists"
        ]
    )

    SCOPE_LABELS[name.value] = ACTUAL_LINE[0]
    SCOPE.push(name.value, True)
    return PowangString(name.value)

def keyword_goto(name: Token | None = None):
    if name is None:
        name = TokenNameValue(TokenType.IDENTIFIER, max(SCOPE_LABELS, key=lambda x: SCOPE_LABELS[x]))
    else:
        assert name.type == TokenType.IDENTIFIER, error_syntax(
            "label's name must be an identifier", [
                f"expected {TokenType.to_str(TokenType.IDENTIFIER)}",
                f"but {TokenType.to_str(name.type)} was provided"
            ]
        )
    
        assert name.value in SCOPE_LABELS, error_identifier_not_found(
            name.value, False
        )
    
    ACTUAL_LINE[0] = SCOPE_LABELS[name.value]
    
    next_labels = set[str]()
    for label_name, label_line in SCOPE_LABELS.items():
        if label_line > SCOPE_LABELS[name.value]:
            next_labels.add(label_name)
    
    for label in next_labels:
        SCOPE_LABELS.pop(label)

    
    while SCOPE.peek_name()[0] != name.value:
        SCOPE.pop()
    
    return PowangString(name.value)