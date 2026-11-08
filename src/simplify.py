"""AST simplification for literal boolean branches.

The simplifier runs after parsing and before checking and execution. It only
folds literal booleans, so it never evaluates user expressions or hides side
effects. Warnings are emitted before a branch is removed.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .lexer.token import LexerTokenType, ParserTokenType


def _bool_value(node: Any) -> Optional[bool]:
    if not isinstance(node, dict):
        return None
    node_type = node.get('type')
    value = node.get('value')
    if node_type == LexerTokenType.BOOLEAN_LITERAL and isinstance(value, bool):
        return value
    if node_type == LexerTokenType.IDENTIFIER and value in {'true', 'false'}:
        return value == 'true'
    return None


def _empty_block(origin: Any) -> dict:
    return {
        'type': ParserTokenType.BLOCK_STATEMENT,
        'value': [],
        'line': origin.get('line') if isinstance(origin, dict) else None,
        'column': origin.get('column') if isinstance(origin, dict) else None,
    }


def _warn(warn: Optional[Callable], message: str, node: Any, code: str) -> None:
    if warn is None:
        return
    line = node.get('line') if isinstance(node, dict) else None
    column = node.get('column') if isinstance(node, dict) else None
    warn(message, line, column, code=code)


def _simplify(node: Any, warn: Optional[Callable]) -> Any:
    if isinstance(node, list):
        return [_simplify(item, warn) for item in node]
    if not isinstance(node, dict):
        return node

    node_type = node.get('type')
    value = node.get('value')

    if node_type == ParserTokenType.IF_STATEMENT and isinstance(value, dict):
        condition = value.get('expression')
        literal = _bool_value(condition)
        block = value.get('block')
        else_block = value.get('else')

        if literal is False:
            _warn(
                warn,
                'condition is always false, this branch has no effect',
                condition,
                'PW211',
            )
            if else_block is not None:
                return _simplify(else_block, warn)
            return _empty_block(node)

        if literal is True:
            if else_block is not None:
                _warn(
                    warn,
                    'else branch is unreachable',
                    else_block,
                    'PW214',
                )
            return _simplify(block, warn)

        value['block'] = _simplify(block, warn)
        if else_block is not None:
            value['else'] = _simplify(else_block, warn)
        return node

    if isinstance(value, dict):
        node['value'] = _simplify(value, warn)
    elif isinstance(value, list):
        node['value'] = [_simplify(item, warn) for item in value]
    return node


def simplify_program(program_ast: Any, warn: Optional[Callable] = None) -> Any:
    """Simplify literal boolean branches and emit warnings."""
    return _simplify(program_ast, warn)
