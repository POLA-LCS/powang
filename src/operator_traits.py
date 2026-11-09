"""Built-in operator traits shared by the checker, runtime and LSP."""

from __future__ import annotations

## The required parameter types are deliberately gradual. A concrete method
## such as ``fun this.add(other: Point): Point`` satisfies ``add(any): any``
## because ``any`` is compatible in both directions. The checker then uses the
## concrete signature to verify the actual right operand and result type.
OPERATOR_TRAITS: dict[str, dict[str, object]] = {
    'Add': {'method': 'add', 'parameters': ('any',), 'returns': 'any'},
    'Subtract': {'method': 'subtract', 'parameters': ('any',), 'returns': 'any'},
    'Multiply': {'method': 'multiply', 'parameters': ('any',), 'returns': 'any'},
    'Divide': {'method': 'divide', 'parameters': ('any',), 'returns': 'any'},
    'Remainder': {'method': 'remainder', 'parameters': ('any',), 'returns': 'any'},
    'Negate': {'method': 'negate', 'parameters': (), 'returns': 'any'},
    'Compare': {'method': 'compare', 'parameters': ('any',), 'returns': 'int'},
}

BINARY_OPERATOR_TRAITS: dict[str, str] = {
    '+': 'Add',
    '-': 'Subtract',
    '*': 'Multiply',
    '/': 'Divide',
    '%': 'Remainder',
}

UNARY_OPERATOR_TRAITS: dict[str, str] = {
    '-': 'Negate',
}

COMPARISON_OPERATOR_TRAIT = 'Compare'
COMPARISON_OPERATORS = frozenset({'==', '!=', '<', '>', '<=', '>='})
OPERATOR_TRAIT_NAMES = frozenset(OPERATOR_TRAITS)
OPERATOR_METHOD_NAMES = frozenset(
    str(spec['method']) for spec in OPERATOR_TRAITS.values()
)


def trait_method(trait_name: str) -> str:
    return str(OPERATOR_TRAITS[trait_name]['method'])


def trait_return_type(trait_name: str) -> str:
    return str(OPERATOR_TRAITS[trait_name]['returns'])
