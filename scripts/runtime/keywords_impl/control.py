from ...lexing.token import Token, TokenType, TokenNameValue
from ...interpret import process_values, interpret_expression
from ...types import *
from ...memory import MEMORY, SCOPE_LABELS
from ...runtime.external_condition import *
from ...error import *

IF_EXPRESSION  = 'if expression'
IF_STATEMENT   = 'if statement'
ELSE_STATEMENT = 'else statement'

def keyword_if(expression: Token, quick_true: Token | None = None, quick_false: Token | None = None, ends: Token | None = None):
    return_result: PowangAny = PowangNov()

    if ends is not None:
        assert ends.type == TokenType.KEYWORD, error_bad_token(
            TokenType.to_str(ends.type), TokenType.to_str(TokenType.KEYWORD), [
                'quick if only accepts the "ends" keyword in this case',
        ])

        assert ends.value == 'ends', error_bad_token(
            ends.value, 'ends', [
                "quick if only accepts the 'ends' keyword in this case",
        ])

    MEMORY.push(IF_EXPRESSION, False)
    if expression.type == TokenType.EXPRESSION:
        result = interpret_expression(MEMORY.indent_depth, expression.value)
    else:
        result = process_values(MEMORY.indent_depth, [expression])[0]

    expr_eval = PowangBool.eval_expression(result)

    if not expr_eval.data:
        if quick_false is not None:
            if quick_false.type == TokenType.EXPRESSION:
                quick_value = interpret_expression(MEMORY.indent_depth, quick_false.value)
            else:
                quick_value = process_values(MEMORY.indent_depth, [quick_false])[0]
            return_result = PowangCopyConstruct(quick_value)
        if ends is None:
            EXTERNAL_CONDITION.append(
                lambda indent, domain: (
                    indent > MEMORY.indent_depth or
                    not (domain.type == TokenType.KEYWORD and domain.value in {'else', 'ends'})
                )
            )
    else:
        if quick_true is not None:
            if quick_true.type == TokenType.EXPRESSION:
                quick_value = interpret_expression(MEMORY.indent_depth, quick_true.value)
            else:
                quick_value = process_values(MEMORY.indent_depth, [quick_true])[0]
            return_result = PowangCopyConstruct(quick_value)
        if ends is None:
            MEMORY.push(IF_STATEMENT, True)

    if ends is not None:
        MEMORY.pop(1)  # Remove IF_EXPRESSION scope

    return return_result

def keyword_else_else_if(expression: Token | None = None):
    if MEMORY.peek_scope().name == IF_STATEMENT:
        EXTERNAL_CONDITION.append(
            lambda indent, domain: (
                indent > MEMORY.indent_depth or
                not (domain.type == TokenType.KEYWORD and domain.value in {'else', 'ends'})
            )
        )
    else:
        assert MEMORY.peek_scope().name == IF_EXPRESSION, error_syntax(
            "Encounter else without a corresponding if", [
                'Perhaps you missed an "end"'
            ]
        )

        if expression is not None:
            return keyword_if(expression)

        MEMORY.push(ELSE_STATEMENT, True)
    return PowangNov()

def keyword_ends():
    if MEMORY.peek_scope().name == IF_EXPRESSION:
        MEMORY.pop(1)
        return PowangNov()

    assert MEMORY.indent_depth > 0, error_syntax(
        "there's no active scope to end", [
            "trying to end global scope",
            'perhaps you meant "exit"?'
        ]
    )

    if MEMORY.peek_scope().name in [IF_STATEMENT, ELSE_STATEMENT]:
        MEMORY.pop(2)
    else:
        MEMORY.pop(1)
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
    MEMORY.push(name.value, True)
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


    while MEMORY.peek_scope().name != name.value:
        MEMORY.pop()

    return PowangString(name.value)