"""Gradual static type checker for Powang.

This module implements the first vertical slice of gradual typing:

* typed declarations and inferred declarations
* annotated assignments
* binary/unary result types
* function-call arity and parameter checks when a signature is known
* return statements against the function annotation
* the postfix ``?`` error-propagation operator

The checker is deliberately conservative. Anything it does not understand is
skipped and treated as ``some``, which is compatible with everything. That is
what makes the typing gradual: unannotated programs keep running exactly as
before.
"""

import copy
import re
from pathlib import Path
from typing import Any, Optional

from .parser import Parser, NATI_TYPES, PATHS
from .simplify import simplify_program
from .state import get_state
from .module_loader import ModuleLoader
from .powang_types import (
    PowangArray,
    PowangHandle,
    PowangBoolean,
    PowangErrorValue,
    PowangFileStream,
    PowangFunction,
    PowangInteger,
    PowangMap,
    PowangSet,
    PowangNova,
    PowangNumber,
    PowangObjectType,
    PowangProject,
    PowangAnyType,
    PowangString,
    PowangChar,
    PowangTask,
    BUILTIN_OBJECT_TYPES,
)
from .error import (
    PowangError,
    powang_error_format,
    powang_error_type_match,
)
from .lexer.token import LexerTokenType, ParserTokenType
from .builtins.native_methods import NATIVE_METHOD_TYPES, NATIVE_METHOD_NAMES
from .operator_traits import (
    BINARY_OPERATOR_TRAITS,
    COMPARISON_OPERATOR_TRAIT,
    OPERATOR_TRAITS,
    OPERATOR_TRAIT_NAMES,
    UNARY_OPERATOR_TRAITS,
    trait_method,
    trait_return_type,
)
HANDLE = PowangHandle.type
PROJECT = PowangProject.type
ANY = PowangAnyType.type
NOVA = PowangNova.type
BOOLEAN = PowangBoolean.type
INTEGER = PowangInteger.type
NUMBER = PowangNumber.type
STRING = PowangString.type
ARRAY = PowangArray.type
MAP = PowangMap.type
SET = PowangSet.type
FUNCTION = PowangFunction.type
ERROR = PowangErrorValue.type
OBJECT = PowangObjectType.type
FILE = PowangFileStream.type
TASK = PowangTask.type

NATIVE_TYPE_NAMES = set(NATI_TYPES) | {FUNCTION, FILE, HANDLE}
ANY = PowangAnyType.type
NOVA = PowangNova.type
BOOLEAN = PowangBoolean.type
INTEGER = PowangInteger.type
NUMBER = PowangNumber.type
STRING = PowangString.type
CHAR = PowangChar.type
ARRAY = PowangArray.type
MAP = PowangMap.type
SET = PowangSet.type
FUNCTION = PowangFunction.type
ERROR = PowangErrorValue.type
OBJECT = PowangObjectType.type
OBJ = 'obj'
FILE = PowangFileStream.type
TASK = PowangTask.type

## `function` and `file` are runtime types but are absent from the parser's
## NATI_TYPES set, so they need explicit handling here.
NATIVE_TYPE_NAMES = set(NATI_TYPES) | {CHAR, FUNCTION, FILE, HANDLE, OBJ}

ARRAY_OPEN = f'{ARRAY}['
ARRAY_CLOSE = ']'
MIXED = 'mixed'
UNDEF = 'undef'


def _is_array_type(type_name: str) -> bool:
    return type_name == ARRAY or (
        isinstance(type_name, str)
        and type_name.startswith(ARRAY_OPEN)
        and type_name.endswith(ARRAY_CLOSE)
    )


def _array_element_type(type_name: str) -> str:
    if type_name == ARRAY:
        return ANY
    if _is_array_type(type_name):
        return type_name[len(ARRAY_OPEN):-len(ARRAY_CLOSE)]
    return ANY


def _is_tuple_type(type_name: str) -> bool:
    return type_name == 'tup' or (
        isinstance(type_name, str)
        and type_name.startswith('tup[')
        and type_name.endswith(']')
    )


def _array_of(element_type: str) -> str:
    if element_type == ANY:
        return f'{ARRAY}[{ANY}]'
    return f'{ARRAY}[{element_type}]'


def _is_set_type(type_name: str) -> bool:
    return type_name == SET or (
        isinstance(type_name, str)
        and type_name.startswith(f'{SET}[')
        and type_name.endswith(']')
    )


def _set_element_type(type_name: str) -> str:
    if type_name == SET:
        return ANY
    if _is_set_type(type_name):
        return type_name[len(SET) + 1:-1]
    return ANY


def _set_of(element_type: str) -> str:
    return f'{SET}[{element_type}]'


def _map_parts(type_name: str) -> tuple[str, str]:
    if not isinstance(type_name, str) or not type_name.startswith('map[') or not type_name.endswith(']'):
        return ANY, ANY
    parts = _type_arguments(type_name)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return ANY, ANY


def _type_arguments(type_name: str) -> list[str]:
    if not isinstance(type_name, str) or '[' not in type_name or not type_name.endswith(']'):
        return []
    inner = type_name[type_name.index('[') + 1:-1]
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in inner:
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
        if char == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        parts.append(''.join(current).strip())
    return parts


def _split_union(type_name: str) -> list[str]:
    """Split a rendered union at top-level ``|`` characters."""
    if not isinstance(type_name, str) or '|' not in type_name:
        return [type_name]
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in type_name:
        if char == '[':
            depth += 1
        elif char == ']':
            depth = max(0, depth - 1)
        if char == '|' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    parts.append(''.join(current).strip())
    return [part for part in parts if part]


def _union_of_types(types: list[str]) -> str:
    flattened: list[str] = []
    for type_name in types:
        for branch in _split_union(type_name):
            if branch == ANY:
                return ANY
            if branch not in flattened:
                flattened.append(branch)
    if not flattened:
        return ANY
    if len(flattened) == 1:
        return flattened[0]
    return ' | '.join(flattened)

NUMERIC_TYPES = {INTEGER, NUMBER}
COMPARISON_OPERATORS = {'==', '!=', '<', '>', '<=', '>='}
TYPE_COMPARISON_OPERATORS = {'::', '!:'}
LOGICAL_OPERATORS = {'&&', '||'}

BUILTIN_RETURN_TYPES: dict[str, str] = {
    'print': INTEGER,
    'println': INTEGER,
    'printf': INTEGER,
    'format': STRING,
    'error' : ERROR,
    'system': INTEGER,
    'input' : ANY,
    'inputf': ANY,
    'typeof': STRING,
    'typedeep': STRING,
    'size'  : INTEGER,
    'open'  : BOOLEAN,
    'close' : BOOLEAN,
    'write' : ANY,
    'read'  : STRING,
    ## Tasks are opaque to the checker: a spawned call is always `task`,
    ## while the awaited result type is unknowable without generics.
    'wait'  : ANY,
    'cancel': ANY,
    'task_status': STRING,
    ## Character helpers accept either a char or a one-character str.
    'is_digit'  : BOOLEAN,
    'is_alpha'  : BOOLEAN,
    'is_alnum'  : BOOLEAN,
    'is_space'  : BOOLEAN,
    'is_upper'  : BOOLEAN,
    'is_lower'  : BOOLEAN,
    'is_ascii'  : BOOLEAN,
    'ord'       : INTEGER,
    'chr'       : CHAR,
    'digit_value': INTEGER,
}


class _VariableInfo:
    __slots__ = ('type', 'annotated', 'weak', 'async_value')

    def __init__(
        self,
        type_name: str,
        annotated: bool,
        weak: bool = False,
        async_value: bool = False,
    ):
        self.type = type_name
        self.annotated = annotated
        self.weak = weak
        self.async_value = async_value


class _Signature:
    __slots__ = (
        'name',
        'parameter_names',
        'parameter_types',
        'parameter_weak',
        'min_argc',
        'return_type',
        'return_weak',
        'allows_error',
        'function_type',
        'type_parameters',
        'variadic',
        'variadic_index',
        'variadic_type',
        'type_parameter_constraints',
        'is_async',
    )

    def __init__(
        self,
        name: str,
        parameter_names: list[str],
        parameter_types: list[str],
        parameter_weak: list[bool],
        min_argc: int,
        return_type: str,
        return_weak: bool,
        allows_error: bool,
        function_type: str | None = None,
        type_parameters: list[str] | None = None,
        variadic: bool = False,
        variadic_index: int | None = None,
        variadic_type: str | None = None,
        type_parameter_constraints: dict[str, list[str]] | None = None,
        is_async: bool = False,
    ):
        self.name = name
        self.parameter_names = parameter_names
        self.parameter_types = parameter_types
        self.parameter_weak = parameter_weak
        self.min_argc = min_argc
        self.return_type = return_type
        self.return_weak = return_weak
        self.allows_error = allows_error
        self.function_type = function_type
        self.type_parameters = type_parameters or []
        self.variadic = variadic
        self.variadic_index = variadic_index
        self.variadic_type = variadic_type
        self.type_parameter_constraints = type_parameter_constraints or {}
        self.is_async = is_async


class _TraitInfo:
    __slots__ = (
        'name',
        'properties',
        'methods',
        'required_methods',
        'default_methods',
    )

    def __init__(self, name: str):
        self.name = name
        self.properties: dict[str, str] = {}
        self.methods: dict[str, list[_Signature]] = {}
        self.required_methods: set[str] = set()
        self.default_methods: set[str] = set()


class _ModuleTypeInfo:
    __slots__ = (
        'name',
        'path',
        'functions',
        'variables',
        'object_types',
        'traits',
        'all_object_types',
        'all_traits',
        'exports',
        'errors',
        'legacy',
        'loading',
    )

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self.functions: dict[str, list[_Signature]] = {}
        self.variables: dict[str, str] = {}
        self.object_types: dict[str, dict] = {}
        self.traits: dict[str, _TraitInfo] = {}
        self.all_object_types: dict[str, dict] = {}
        self.all_traits: dict[str, _TraitInfo] = {}
        self.exports: dict[str, str] = {}
        self.errors: list[PowangError] = []
        self.legacy = False
        self.loading = False


class _TypeChecker:
    def __init__(
        self,
        path: Optional[str] = None,
        module_cache: Optional[dict[str, _ModuleTypeInfo]] = None,
    ):
        self.path = path
        ## Aliases belong to the run being checked, which is the active state
        ## at type_check time. A previous run's aliases are never visible.
        self.type_alias: dict[str, Any] = get_state().type_alias
        self.errors: list[PowangError] = []
        self.functions: dict[str, list[_Signature]] = {}
        self.object_types: dict[str, dict[str, Any]] = {}
        self.scopes: list[dict[str, _VariableInfo]] = [{}]
        self.module_cache: dict[str, _ModuleTypeInfo] = (
            module_cache if module_cache is not None else {}
        )
        self.imported_modules: dict[str, _ModuleTypeInfo] = {}
        self.module_values: dict[str, _ModuleTypeInfo] = {}
        self.type_owners: dict[str, tuple[_ModuleTypeInfo, str]] = {}

        # Current function context. ``None`` means top level.
        self.return_type: Optional[str] = None
        self.return_weak: bool = False
        self.return_allows_error: bool = False
        self.in_function: bool = False
        self.in_async_function: bool = False
        self.this_type: Optional[str] = None
        self.type_parameters: set[str] = set()
        self.current_type_parameters: set[str] = set()
        self.traits: dict[str, _TraitInfo] = {}
        self.current_type_parameter_constraints: dict[str, list[str]] = {}
        self.in_trait_body: Optional[tuple[str, str]] = None
        self._install_operator_traits()
        self.loop_labels: list[Optional[str]] = []
        self.loop_break_flags: list[bool] = []
        self._position: Optional[tuple[int, int]] = None

    def _install_operator_traits(self) -> None:
        for trait_name, spec in OPERATOR_TRAITS.items():
            trait = _TraitInfo(trait_name)
            method_name = trait_method(trait_name)
            parameter_types = [
                str(parameter) for parameter in spec.get('parameters', ())
            ]
            return_type = trait_return_type(trait_name)
            signature = _Signature(
                name=method_name,
                parameter_names=[
                    f'arg{index}' for index in range(len(parameter_types))
                ],
                parameter_types=parameter_types,
                parameter_weak=[False for _ in parameter_types],
                min_argc=len(parameter_types),
                return_type=return_type,
                return_weak=False,
                allows_error=False,
                function_type='fun[' + ', '.join(
                    [*parameter_types, return_type]
                ) + ']',
            )
            trait.methods[method_name] = [signature]
            trait.required_methods.add(method_name)
            self.traits[trait_name] = trait

    # ------------------------------------------------------------------ utils
    def _scope_push(self):
        self.scopes.append({})

    def _scope_pop(self):
        if len(self.scopes) > 1:
            self.scopes.pop()

    def _lookup(self, name: str) -> Optional[_VariableInfo]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def _bind(
        self,
        name: str,
        type_name: str,
        annotated: bool,
        weak: bool = False,
        async_value: bool = False,
    ):
        if not name:
            return
        if name in self.scopes[-1]:
            self._error(
                f"variable '{name}' is already declared in this scope",
                ["choose a different name or assign to the existing variable with '='"],
                where='variable declaration',
            )
        self.scopes[-1][name] = _VariableInfo(
            type_name, annotated, weak, async_value
        )

    def _error(self, message: str, details: Optional[list[str]] = None, where: str = 'type checker'):
        error = powang_error_format(
            'TYPE', where, message, details if details is not None else []
        )
        if self._position is not None:
            error.line = self._position[0] + 1
            error.column = self._position[1]
            error.text = error.render_text()
            error.args = (error.text,)
        self.errors.append(error)

    def _assign_error(self, where: str, expected: str, encountered: str):
        trait_name = self._trait_name(expected)
        if trait_name is not None:
            reason = self._trait_failure_reason(encountered, trait_name)
            if reason is not None:
                error = powang_error_format(
                    'TYPE', where,
                    f"type {self._display_type_name(encountered)} cannot satisfy {trait_name}",
                    [reason],
                )
                if self._position is not None:
                    error.line = self._position[0] + 1
                    error.column = self._position[1]
                    error.text = error.render_text()
                    error.args = (error.text,)
                self.errors.append(error)
                return
        error = powang_error_type_match(where, expected, encountered)
        if self._position is not None:
            error.line = self._position[0] + 1
            error.column = self._position[1]
            error.text = error.render_text()
            error.args = (error.text,)
        self.errors.append(error)

    @staticmethod
    def _identifier_name(node: Any) -> Optional[str]:
        if not isinstance(node, dict):
            return None
        if node.get('type') == LexerTokenType.IDENTIFIER:
            value = node.get('value')
            return value if isinstance(value, str) else None
        if node.get('type') == ParserTokenType.TYPE:
            inner = node.get('value')
            if isinstance(inner, dict):
                value = inner.get('value')
                if isinstance(value, str):
                    return value
        return None

    def _type_name_from_node(self, node: Any) -> Optional[str]:
        """Resolve a type name used after `as`, including `arr[...]`."""
        if not isinstance(node, dict):
            return None
        if node.get('type') == ParserTokenType.TYPE:
            inner = node.get('value')
            if isinstance(inner, dict):
                alternatives = inner.get('alternatives')
                if isinstance(alternatives, list) and alternatives:
                    return _union_of_types([
                        self._annotation_type(alternative, ANY)
                        for alternative in alternatives
                        if isinstance(alternative, dict)
                    ])
                if inner.get('value') == 'fun':
                    return self._annotation_type(node)
                name = inner.get('value')
                if isinstance(name, str):
                    generics = inner.get('generics')
                    base = 'any' if name == 'any' else self._normalized_type_name(name)
                    element_node = inner.get('element_type') or node.get('element_type')
                    if name == ARRAY and isinstance(element_node, dict):
                        return _array_of(self._type_name_from_node(element_node))
                    if isinstance(generics, list) and generics:
                        types = [self._type_name_from_node(g) for g in generics]
                        types = [t if t is not None else 'any' for t in types]
                        if inner.get('variadic'):
                            types.append('...')
                        if name == 'tup':
                            return 'tup[' + ', '.join(types) + ']'
                        if name in (PowangMap.type, 'map'):
                            return 'map[' + ', '.join(types) + ']'
                        if name in (PowangArray.type, 'arr'):
                            if types:
                                return _array_of(types[0])
                    return base
            return None
        if node.get('type') == LexerTokenType.IDENTIFIER:
            name = node.get('value')
            if not isinstance(name, str):
                return None
            if name == 'any':
                return 'any'
            return self._normalized_type_name(name)
        if node.get('type') == ParserTokenType.INDEX_EXPRESSION:
            value = node.get('value')
            if not isinstance(value, dict):
                return None
            target_name = self._identifier_name(value.get('target'))
            index_node = value.get('index')
            if target_name == ARRAY:
                element = self._type_name_from_node(index_node)
                if element is None:
                    return ARRAY
                return _array_of(element)
            if target_name == 'tup':
                if isinstance(index_node, dict) and index_node.get('type') == ParserTokenType.TUPLE_EXPRESSION:
                    elems = index_node.get('value', {}).get('elements', []) if isinstance(index_node.get('value'), dict) else index_node.get('elements', [])
                    if not isinstance(elems, list):
                        elems = []
                    types = [self._type_name_from_node(e) for e in elems]
                    types = [t if t is not None else ANY for t in types]
                    return 'tup[' + ', '.join(types) + ']'
                element = self._type_name_from_node(index_node)
                if element is None:
                    return 'tup'
                return 'tup[' + element + ']'
            if target_name == MAP:
                return MAP
            return None
        return None

    def _normalized_type_name(self, name: str) -> str:
        if name == "any" or name in self.type_parameters:
            return ANY
        if name == OBJ:
            return OBJ
        seen: set[str] = set()
        while name in self.type_alias and name not in seen:
            seen.add(name)
            alias = self.type_alias[name]
            if isinstance(alias, str):
                name = alias
            elif isinstance(alias, dict):
                name = alias.get('value', ANY)
            else:
                break
        if name in NATIVE_TYPE_NAMES:
            return name
        return f'{OBJECT}:{name}'

    def _annotation_type(self, type_node: Any, default: str = ANY) -> str:
        if not isinstance(type_node, dict):
            return default
        inner = type_node.get('value')
        if isinstance(inner, dict):
            alternatives = inner.get('alternatives')
            if isinstance(alternatives, list) and alternatives:
                return _union_of_types([
                    self._annotation_type(alternative, default)
                    for alternative in alternatives
                    if isinstance(alternative, dict)
                ])
            if inner.get('auto'):
                return ANY
            if inner.get('value') == 'fun':
                parameters = [
                    self._annotation_type(parameter, ANY)
                    for parameter in inner.get('parameters', [])
                    if isinstance(parameter, dict)
                ]
                return_node = inner.get('return_type')
                returns = self._annotation_type(return_node, ANY) if isinstance(return_node, dict) else ANY
                if inner.get('variadic') and parameters:
                    parameters[-1] = parameters[-1] + '...'
                parts = parameters + [returns]
                rendered = 'fun[' + ', '.join(parts) + ']'
                referenced = bool(inner.get('reference', False)) or bool(type_node.get('reference', False))
                return f'&{rendered}' if referenced else rendered
        reference = False
        if isinstance(inner, str):
            name = inner
            reference = bool(type_node.get('reference'))
        elif isinstance(inner, dict):
            name = inner.get('value')
            reference = bool(inner.get('reference'))
        else:
            return default
        if not isinstance(name, str) or not name:
            return default
        if name == FUNCTION:
            self._error(
                "'function' is not a type annotation",
                ["use fun[arg_types..., return_type] for function types"],
                where='type annotation',
            )
            return ANY
        resolved = self._normalized_type_name(name)
        element_node = type_node.get('element_type')
        if element_node is None and isinstance(inner, dict):
            element_node = inner.get('element_type')
        if resolved == ARRAY and element_node is not None:
            resolved = _array_of(self._annotation_type(element_node, ANY))
        if resolved == 'tup':
            generics = None
            if isinstance(inner, dict):
                generics = inner.get('generics')
            if isinstance(generics, list) and generics:
                types = [self._annotation_type(g, ANY) if isinstance(g, dict) else ANY for g in generics]
                if inner.get('variadic'):
                    types.append('...')
                resolved = 'tup[' + ', '.join(types) + ']'
        if resolved == MAP:
            generics = None
            if isinstance(inner, dict):
                generics = inner.get('generics')
            if isinstance(generics, list) and len(generics) >= 2:
                kt = self._annotation_type(generics[0], ANY) if isinstance(generics[0], dict) else ANY
                vt = self._annotation_type(generics[1], ANY) if isinstance(generics[1], dict) else ANY
                resolved = 'map[' + kt + ', ' + vt + ']'
        if resolved == SET:
            generics = None
            if isinstance(inner, dict):
                generics = inner.get('generics')
            if isinstance(generics, list) and generics:
                resolved = _set_of(self._annotation_type(generics[0], ANY))
        return f'&{resolved}' if reference else resolved

    @staticmethod
    def _annotation_reference(type_node: Any) -> bool:
        if not isinstance(type_node, dict):
            return False
        inner = type_node.get('value')
        if isinstance(inner, dict):
            return bool(inner.get('reference', False))
        return False

    @staticmethod
    def _annotation_weak(type_node: Any) -> bool:
        if not isinstance(type_node, dict):
            return False
        inner = type_node.get('value')
        if isinstance(inner, dict):
            return bool(inner.get('weak', False))
        return False

    @staticmethod
    def _annotation_error_union(type_node: Any) -> bool:
        if not isinstance(type_node, dict):
            return False
        inner = type_node.get('value')
        if isinstance(inner, dict):
            return bool(inner.get('error_union', False))
        return False

    def _union_branch_assignable(self, target: str, source: str, target_weak: bool = False) -> bool:
        """Match one union branch without unrelated numeric coercion.

        A union declares the set of accepted shapes. `int | str` must reject a
        number, even though a standalone `int` declaration may still truncate
        it through the legacy implicit cast rules.
        """
        if target == ANY or source == ANY:
            return True
        if target == source:
            return True
        if source == NOVA:
            return target_weak or target == NOVA
        if target == NOVA:
            return False
        if target.startswith('&') or source.startswith('&'):
            return target == source
        if target.startswith(f'{OBJECT}:'):
            return source == target
        if source.startswith(f'{OBJECT}:'):
            return False
        if _is_array_type(target) or _is_array_type(source):
            return self._assignable(target, source)
        if target.startswith(('tup[', 'map[')) or source.startswith(('tup[', 'map[')):
            return self._assignable(target, source)
        return False

    @staticmethod
    def _display_type_name(type_name: Any) -> Any:
        if isinstance(type_name, str) and type_name.startswith(f'{OBJECT}:'):
            return type_name.split(':', 1)[1]
        return type_name

    def _trait_name(self, type_name: Any) -> Optional[str]:
        if not isinstance(type_name, str):
            return None
        name = self._display_type_name(type_name)
        return name if isinstance(name, str) and name in self.traits else None

    def _normalized_object_name(self, type_name: Any) -> Optional[str]:
        if not isinstance(type_name, str):
            return None
        return self._display_type_name(type_name)

    def _method_signature_compatible(
        self,
        required: _Signature,
        actual: _Signature,
    ) -> bool:
        if required.variadic != actual.variadic:
            return False
        if required.variadic:
            fixed_required = required.variadic_index or 0
            fixed_actual = actual.variadic_index or 0
            if fixed_required != fixed_actual:
                return False
            for index in range(fixed_required):
                if not self._assignable(
                    actual.parameter_types[index],
                    required.parameter_types[index],
                ):
                    return False
            if required.variadic_type is not None and actual.variadic_type is not None:
                if not self._assignable(
                    actual.variadic_type,
                    required.variadic_type,
                ):
                    return False
        else:
            if len(required.parameter_types) != len(actual.parameter_types):
                return False
            for required_type, actual_type in zip(
                required.parameter_types,
                actual.parameter_types,
            ):
                if not self._assignable(actual_type, required_type):
                    return False
        if required.return_type == NOVA:
            return True
        return self._assignable(required.return_type, actual.return_type)

    def _trait_method_signature(
        self,
        type_name: str,
        trait_name: str,
        method_name: str,
    ) -> Optional[_Signature]:
        normalized = self._normalized_object_name(type_name)
        if normalized is None:
            return None
        if normalized == trait_name:
            trait = self.traits.get(trait_name)
            if trait is None:
                return None
            signatures = trait.methods.get(method_name)
            return signatures[0] if signatures else None
        info = self._object_type_info(normalized)
        if info is None:
            return None
        qualified = info.get('trait_methods', {}).get(
            trait_name, {}
        ).get(method_name)
        if qualified:
            return qualified[0]
        unqualified = info.get('methods', {}).get(method_name)
        if unqualified:
            return unqualified[0]
        trait = self.traits.get(trait_name)
        if trait is not None and method_name in trait.default_methods:
            signatures = trait.methods.get(method_name)
            return signatures[0] if signatures else None
        return None

    def _trait_satisfies_trait(self, source_name: str, target_name: str) -> bool:
        source = self.traits.get(source_name)
        target = self.traits.get(target_name)
        if source is None or target is None:
            return False
        for prop_name, required_type in target.properties.items():
            actual_type = source.properties.get(prop_name)
            if actual_type is None:
                return False
            if not self._assignable(required_type, actual_type):
                return False
        for method_name in target.required_methods:
            if method_name in target.default_methods:
                continue
            actual_signatures = source.methods.get(method_name)
            required_signatures = target.methods.get(method_name, [])
            if not actual_signatures:
                return False
            if not any(
                self._method_signature_compatible(required, actual)
                for required in required_signatures
                for actual in actual_signatures
            ):
                return False
        return True

    def _type_satisfies_trait(self, type_name: str, trait_name: str) -> bool:
        normalized = self._normalized_object_name(type_name)
        trait = self.traits.get(trait_name)
        if normalized is None or trait is None:
            return False
        if normalized == trait_name:
            return True
        if normalized in self.traits:
            return self._trait_satisfies_trait(normalized, trait_name)
        info = self._object_type_info(normalized)
        if info is None:
            return False
        props = info.get('props', {})
        for prop_name, required_type in trait.properties.items():
            actual_type = props.get(prop_name)
            if actual_type is None:
                return False
            if not self._assignable(required_type, actual_type):
                return False
        for method_name in trait.required_methods:
            if method_name in trait.default_methods:
                continue
            signature = self._trait_method_signature(
                normalized, trait_name, method_name
            )
            if signature is None:
                return False
            required_signatures = trait.methods.get(method_name, [])
            if not any(
                self._method_signature_compatible(required, signature)
                for required in required_signatures
            ):
                return False
        return True

    def _trait_failure_reason(
        self,
        type_name: Any,
        trait_name: str,
    ) -> Optional[str]:
        normalized = self._normalized_object_name(type_name)
        trait = self.traits.get(trait_name)
        if normalized is None or trait is None:
            return None
        if normalized in self.traits:
            if self._trait_satisfies_trait(normalized, trait_name):
                return None
            return f"trait {normalized} does not satisfy {trait_name}"
        info = self._object_type_info(normalized)
        if info is None:
            return f"type {normalized} is not a declared object type"
        props = info.get('props', {})
        for prop_name, required_type in trait.properties.items():
            actual_type = props.get(prop_name)
            if actual_type is None:
                return f"missing property {prop_name}"
            if not self._assignable(required_type, actual_type):
                return (
                    f"property {prop_name} has type {actual_type}, "
                    f"but the trait requires {required_type}"
                )
        for method_name in trait.required_methods:
            if method_name in trait.default_methods:
                continue
            signature = self._trait_method_signature(
                normalized, trait_name, method_name
            )
            if signature is None:
                return f"missing method {method_name}"
            required_signatures = trait.methods.get(method_name, [])
            if not any(
                self._method_signature_compatible(required, signature)
                for required in required_signatures
            ):
                return f"method {method_name} has an incompatible signature"
        return "does not satisfy the trait contract"

    def _assignable_trait(
        self,
        target: str,
        source: str,
        target_trait: Optional[str],
        source_trait: Optional[str],
    ) -> bool:
        if target_trait is not None and source_trait is not None:
            return target_trait == source_trait or \
                self._trait_satisfies_trait(source_trait, target_trait)
        if target_trait is not None:
            source_name = self._normalized_object_name(source)
            if source_name is None:
                return False
            if source_name == OBJ:
                return False
            return self._type_satisfies_trait(source_name, target_trait)
        return target == OBJ

    def _assignable(self, target: str, source: str, target_weak: bool = False) -> bool:
        if target == ANY or source == ANY:
            return True
        if target == UNDEF or source == UNDEF:
            return True
        if target in self.current_type_parameters or source in self.current_type_parameters:
            return True
        source_branches = _split_union(source)
        if len(source_branches) > 1:
            return all(self._assignable(target, branch, target_weak) for branch in source_branches)
        target_branches = _split_union(target)
        if len(target_branches) > 1:
            return any(
                self._union_branch_assignable(branch, source, target_weak)
                for branch in target_branches
            )
        target_trait = self._trait_name(target)
        source_trait = self._trait_name(source)
        if target_trait is not None or source_trait is not None:
            return self._assignable_trait(
                target, source, target_trait, source_trait
            )
        if target.startswith('&') or source.startswith('&'):
            return target == source
        if target == source:
            return True
        if target.startswith(('tup[', 'map[')) or source.startswith(('tup[', 'map[')):
            try:
                from . import typespec as _ts
                return _ts.assignable(_ts.type_of_str(target), _ts.type_of_str(source))
            except Exception:
                return False
        if _is_array_type(target) and _is_array_type(source):
            target_element = _array_element_type(target)
            source_element = _array_element_type(source)
            if target_element == ANY:
                return True
            if target_element == MIXED or source_element == MIXED:
                return target_element == source_element
            if source_element == ANY:
                return True
            return self._assignable(target_element, source_element)
        if _is_set_type(target) and _is_set_type(source):
            target_element = _set_element_type(target)
            source_element = _set_element_type(source)
            if target_element == ANY or source_element == ANY:
                return True
            return self._assignable(target_element, source_element)
        if target.startswith('fun[') or source.startswith('fun['):
            try:
                from . import typespec as _ts
                return _ts.assignable(_ts.type_of_str(target), _ts.type_of_str(source))
            except Exception:
                return False
        if source == NOVA:
            # Only weak declarations accept nova.
            return target_weak
        if target == NOVA:
            return False
        if target == OBJ:
            return source == OBJ or source.startswith(f'{OBJECT}:') or \
                source in BUILTIN_OBJECT_TYPES
        if source == OBJ:
            return False
        if target.startswith(f'{OBJECT}:'):
            # Constructors perform implicit conversion at runtime. Gradual
            # typing accepts the assignment and lets the runtime decide.
            return True
        if source.startswith(f'{OBJECT}:'):
            return False
        if target == INTEGER and source in (NUMBER, BOOLEAN):
            return True
        if target == NUMBER and source in (INTEGER, BOOLEAN):
            return True
        if target == BOOLEAN and (source in (INTEGER, NUMBER, STRING) or _is_array_type(source)):
            return True
        if target == STRING and source in (ERROR, CHAR):
            return True
        if _is_array_type(target) and source == MAP:
            return True
        if target == MAP and _is_array_type(source):
            return True
        return False

    # --------------------------------------------------------------- builtins
    _builtins_cache: Optional[dict] = None

    @classmethod
    def _builtins(cls) -> dict:
        if cls._builtins_cache is None:
            try:
                from .builtins.builtins import BUILTINS
                cls._builtins_cache = BUILTINS
            except Exception:
                cls._builtins_cache = {}
        return cls._builtins_cache

    # ---------------------------------------------------------------- program
    def run(self, program_ast: Any) -> list[PowangError]:
        if not isinstance(program_ast, (list, tuple)):
            return self.errors
        if 'Project' not in self.object_types:
            self.object_types['Project'] = {
                'props': dict(BUILTIN_OBJECT_TYPES[PROJECT]),
                'methods': {},
                'static_methods': {},
                'trait_methods': {},
                'type_parameters': [],
                'is_enum': False,
                'variants': [],
            }
        if getattr(get_state(), 'project_value', None) is not None and not self._has_project_declaration(program_ast):
            self.scopes[0]['project'] = _VariableInfo(PROJECT, True, False)
        for statement in program_ast:
            self._infer(statement)
        return self.errors

    @staticmethod
    def _has_project_declaration(program_ast: Any) -> bool:
        if not isinstance(program_ast, (list, tuple)):
            return False
        for statement in program_ast:
            if not isinstance(statement, dict):
                continue
            statement_type = statement.get('type')
            value = statement.get('value')
            if statement_type not in {
                ParserTokenType.DECLARATION_TYPED_VAR,
                ParserTokenType.DECLARATION_INTERPRET,
            } or not isinstance(value, dict):
                continue
            if value.get('identifier', {}).get('value') == 'project':
                return True
        return False

    # -------------------------------------------------------------- inference
    def _infer(self, node: Any) -> str:
        previous_position = self._position
        position = self._node_position(node)
        if position is not None:
            self._position = position
        try:
            return self._infer_inner(node)
        except PowangError as error:
            self.errors.append(error)
            return ANY
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            # A checker must tolerate unexpected AST shapes without hiding
            # internal programming errors such as NameError.
            return ANY
        finally:
            self._position = previous_position

    @staticmethod
    def _node_position(node: Any) -> Optional[tuple[int, int]]:
        if not isinstance(node, dict):
            return None
        line = node.get('line')
        column = node.get('column')
        if isinstance(line, int) and isinstance(column, int):
            return line, column
        value = node.get('value')
        if isinstance(value, dict):
            line = value.get('line')
            column = value.get('column')
            if isinstance(line, int) and isinstance(column, int):
                return line, column
            for key in ('identifier', 'callee', 'target', 'type', 'expression', 'property', 'owner', 'method'):
                child = value.get(key)
                if isinstance(child, dict):
                    position = _TypeChecker._node_position(child)
                    if position is not None:
                        return position
        return None

    def _infer_inner(self, node: Any) -> str:
        if not isinstance(node, dict) or not node:
            return ANY

        node_type = node.get('type')
        value = node.get('value')

        if node_type == LexerTokenType.IDENTIFIER:
            return self._infer_identifier(value)

        if node_type == LexerTokenType.NOVA_LITERAL:
            return NOVA
        if node_type == LexerTokenType.BOOLEAN_LITERAL:
            return BOOLEAN
        if node_type == LexerTokenType.INTEGER_LITERAL:
            return INTEGER
        if node_type == LexerTokenType.FLOATING_LITERAL:
            return NUMBER
        if node_type == LexerTokenType.STRING_LITERAL:
            return STRING
        if node_type == LexerTokenType.CHAR_LITERAL:
            return CHAR
        if node_type == ParserTokenType.INTERPOLATED_STRING:
            parts = value.get('parts') if isinstance(value, dict) else None
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and part.get('kind') == 'expression':
                        self._infer(part.get('value'))
            return STRING

        if node_type == ParserTokenType.UNARY_EXPRESSION:
            return self._infer_unary(value)
        if node_type == ParserTokenType.BINARY_EXPRESSION:
            return self._infer_binary(value)
        if node_type == ParserTokenType.CALL_EXPRESSION:
            return self._infer_call(value)
        if node_type == ParserTokenType.METHOD_CALL:
            return self._infer_method_call(value)
        if node_type == ParserTokenType.FUN_EXPRESSION:
            return self._infer_lambda(value)
        if node_type == ParserTokenType.INDEX_EXPRESSION:
            return self._infer_index(value)
        if node_type == ParserTokenType.SLICE_EXPRESSION:
            return self._infer_slice(value)
        if node_type == ParserTokenType.ACCESS_EXPRESSION:
            return self._infer_access(value)
        if node_type == ParserTokenType.SAFE_ACCESS_EXPRESSION:
            return self._infer_access(value)
        if node_type == ParserTokenType.INSTANTIATION:
            return self._infer_instantiation(value)
        if node_type == ParserTokenType.ARRAY_EXPRESSION:
            return self._infer_array(value)
        if node_type == ParserTokenType.TUPLE_EXPRESSION:
            elements = value.get('elements', []) if isinstance(value, dict) else []
            element_types = [self._infer(element) for element in elements]
            if not element_types:
                return 'tup'
            return 'tup[' + ', '.join(element_types) + ']'
        if node_type == ParserTokenType.KEY_VALUE_PAIR:
            self._infer(value.get('key'))
            self._infer(value.get('value'))
            return ANY
        if node_type == ParserTokenType.BLOCK_STATEMENT:
            return self._infer_block(value)

        if node_type == ParserTokenType.POSTFIX_UNWRAP:
            return self._infer_unwrap(value)

        if node_type == ParserTokenType.REFERENCE_EXPRESSION:
            return self._infer_reference(value)

        if node_type == ParserTokenType.SPAWN_EXPRESSION:
            return self._infer_spawn(value)

        if node_type == ParserTokenType.AWAIT_EXPRESSION:
            return self._infer_await(value)

        if node_type == ParserTokenType.MATCH_STATEMENT:
            return self._infer_match(value)
        if node_type == ParserTokenType.MATCH_EXPRESSION:
            return self._infer_match(value, as_expression=True)
        if node_type == ParserTokenType.DECLARATION_UNDEFINED:
            return self._infer_declaration_undefined(value)
        if node_type == ParserTokenType.DECLARATION_TYPED_VAR:
            return self._infer_declaration_typed(value)
        if node_type == ParserTokenType.DECLARATION_INTERPRET:
            return self._infer_declaration_interpret(value)
        if node_type == ParserTokenType.DESTRUCTURE_DECLARATION:
            return self._infer_destructure_declaration(value)
        if node_type == ParserTokenType.DECLARATION_FUN:
            self._check_function(node)
            return FUNCTION

        if node_type == ParserTokenType.ASSIGNMENT:
            return self._infer_assignment(value)
        if node_type == ParserTokenType.RETURN_EXPRESSION:
            return self._infer_return(value)
        if node_type == ParserTokenType.IF_STATEMENT:
            return self._infer_if(value)
        if node_type == ParserTokenType.TRY_STATEMENT:
            return self._infer_try(value)
        if node_type == ParserTokenType.FOR_STATEMENT:
            return self._infer_for(value)
        if node_type == ParserTokenType.FOR_EACH_STATEMENT:
            return self._infer_for_each(value)
        if node_type == ParserTokenType.LOOP_STATEMENT:
            return self._infer_loop(value)
        if node_type == ParserTokenType.BREAK_STATEMENT:
            self._check_loop_control('break', value)
            return ANY
        if node_type == ParserTokenType.CONTINUE_STATEMENT:
            self._check_loop_control('continue', value)
            return ANY
        if node_type == ParserTokenType.TRAIT_DECLARATION:
            return self._infer_trait_declaration(value)
        if node_type == ParserTokenType.TYPE_DECLARATION:
            return self._infer_type_declaration(value)
        if node_type == ParserTokenType.EXTERN_REFERENCE:
            return self._infer_extern(value)

        if node_type == ParserTokenType.USE_EXPRESSION:
            return self._infer_use(value)

        if node_type == ParserTokenType.MODULE_DECLARATION:
            return ANY

    # ------------------------------------------------------------ expressions
    def _infer_reference(self, value: Any) -> str:
        """Type of `&name`, `&this.name` and `&values[index]`."""
        if not isinstance(value, dict):
            return ANY
        target = value.get('target')
        if isinstance(target, dict):
            target_type = target.get('type')
            if target_type == ParserTokenType.ACCESS_EXPRESSION:
                resolved = self._infer_access(target.get('value'))
                return ANY if resolved in (ANY, NOVA) else f'&{resolved}'
            if target_type == ParserTokenType.INDEX_EXPRESSION:
                resolved = self._infer_index(target.get('value'))
                return ANY if resolved in (ANY, NOVA) else f'&{resolved}'
        name = self._identifier_name(target)
        if name is None:
            return ANY
        variable = self._lookup(name)
        if variable is None or variable.type in (ANY, NOVA):
            return ANY
        return f'&{variable.type}'

    def _infer_identifier(self, name: Any) -> str:
        if not isinstance(name, str):
            return ANY
        if name == NOVA:
            return NOVA
        if name in ('true', 'false'):
            return BOOLEAN
        if name == 'this':
            return self.this_type if self.this_type is not None else ANY
        if name == 'Project':
            return PROJECT
        if name in self.module_values:
            return f'module:{name}'
        variable = self._lookup(name)
        if variable is not None:
            return variable.type
        if name in self.functions:
            signatures = self.functions[name]
            function_types = [
                signature.function_type
                for signature in signatures
                if signature.function_type
            ]
            unique = list(dict.fromkeys(function_types))
            if len(unique) == 1:
                return unique[0]
            return FUNCTION
        if name in self.object_types:
            return f'{OBJECT}:{name}'
        return ANY

    def _infer_unary(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        operator = value.get('operator')
        operator_name = operator.get('value') if isinstance(operator, dict) else None
        right_type = self._infer(value.get('right'))
        overload = self._infer_unary_operator_overload(
            value, operator_name, right_type
        )
        if overload is not None:
            return overload
        if operator_name == '!':
            return BOOLEAN
        if operator_name == '-':
            return right_type if right_type in NUMERIC_TYPES else ANY
        if operator_name == '[-]':
            return right_type if right_type in {INTEGER, NUMBER, STRING, ARRAY} else ANY
        if operator_name == '+':
            return right_type
        return ANY

    def _operator_method_signatures(
        self,
        type_name: str,
        trait_name: str,
        method_name: str,
        where: str,
    ) -> list[tuple[str, _Signature]]:
        trait = self.traits.get(trait_name)
        if trait is None or method_name not in trait.methods:
            return []
        normalized = self._normalized_object_name(type_name)
        if normalized is not None and normalized in self.traits:
            return [
                (normalized, signature)
                for signature in self.traits[normalized].methods.get(
                    method_name, []
                )
            ]
        if normalized is not None:
            info = self._object_type_info(normalized)
            if info is None:
                return []
            qualified = info.get('trait_methods', {}).get(
                trait_name, {}
            ).get(method_name)
            if qualified:
                return [(trait_name, signature) for signature in qualified]
            methods = info.get('methods', {}).get(method_name, [])
            if methods:
                return [(trait_name, signature) for signature in methods]
            found: list[tuple[str, _Signature]] = []
            for qualifier, members in info.get('trait_methods', {}).items():
                signatures = members.get(method_name, [])
                found.extend(
                    (qualifier, signature) for signature in signatures
                )
            return found
        constraints = self.current_type_parameter_constraints.get(type_name)
        if constraints:
            available = self._trait_signatures_for_method(
                constraints, method_name
            )
            signatures: list[tuple[str, _Signature]] = []
            for constraint_name, trait_signatures in available:
                signatures.extend(
                    (constraint_name, signature)
                    for signature in trait_signatures
                )
            return signatures
        return []

    def _operator_operand_assignable(self, target: str, source: str) -> bool:
        if target in (ANY, UNDEF) or source in (ANY, UNDEF):
            return True
        target_branches = _split_union(target)
        if len(target_branches) > 1:
            return any(
                self._operator_operand_assignable(branch, source)
                for branch in target_branches
            )
        source_branches = _split_union(source)
        if len(source_branches) > 1:
            return all(
                self._operator_operand_assignable(target, branch)
                for branch in source_branches
            )
        if self._trait_name(target) is not None:
            return self._assignable(target, source)
        if target == OBJ:
            return source == OBJ or source.startswith(f'{OBJECT}:') or \
                source in BUILTIN_OBJECT_TYPES
        if target.startswith(f'{OBJECT}:'):
            return source == target
        return self._assignable(target, source)

    def _operator_signature_score(
        self,
        signature: _Signature,
        right_type: str,
    ) -> int:
        parameter = signature.parameter_types[0]
        if parameter == right_type:
            return 4
        if self._trait_name(parameter) is not None:
            return 3
        if parameter == OBJ:
            return 2
        if parameter in (ANY, UNDEF):
            return 1
        return 2

    def _infer_operator_overload(
        self,
        value: Any,
        operator_name: Optional[str],
        left_type: str,
        right_type: str,
    ) -> Optional[str]:
        if operator_name is None:
            return None
        if operator_name in COMPARISON_OPERATORS:
            trait_name = COMPARISON_OPERATOR_TRAIT
        else:
            trait_name = BINARY_OPERATOR_TRAITS.get(operator_name)
        if trait_name is None:
            return None
        method_name = trait_method(trait_name)
        where = f'operator {operator_name}'
        signatures = self._operator_method_signatures(
            left_type, trait_name, method_name, where
        )
        if not signatures:
            return None
        required = self.traits[trait_name].methods[method_name][0]
        valid: list[tuple[str, _Signature]] = []
        invalid: list[tuple[str, _Signature]] = []
        async_found = False
        for source_trait, signature in signatures:
            if signature.is_async:
                async_found = True
                continue
            if len(signature.parameter_types) != 1 or \
                    not self._method_signature_compatible(required, signature):
                invalid.append((source_trait, signature))
                continue
            if not self._operator_operand_assignable(
                signature.parameter_types[0], right_type
            ):
                invalid.append((source_trait, signature))
                continue
            valid.append((source_trait, signature))
        if not valid:
            if invalid:
                _, signature = invalid[0]
                if not self._method_signature_compatible(required, signature):
                    self._error(
                        f"operator method '{method_name}' does not satisfy {trait_name}.{method_name}",
                        [
                            f"required: {required.function_type}",
                            f"found: {signature.function_type}",
                        ],
                        where=where,
                    )
                elif len(signature.parameter_types) != 1:
                    self._error(
                        f"operator method '{method_name}' must accept exactly one operand",
                        [f"found: {signature.function_type}"],
                        where=where,
                    )
                else:
                    self._assign_error(
                        where, signature.parameter_types[0], right_type
                    )
                return ANY
            if async_found:
                self._error(
                    f"operator method '{method_name}' cannot be async",
                    ['remove async from the operator method'],
                    where=where,
                )
            return ANY
        best_score = max(
            self._operator_signature_score(signature, right_type)
            for _, signature in valid
        )
        best = [
            (source_trait, signature)
            for source_trait, signature in valid
            if self._operator_signature_score(signature, right_type) == best_score
        ]
        if len(best) > 1:
            first = best[0][1]
            for _, other in best[1:]:
                if not self._signatures_equivalent(first, other):
                    self._error(
                        'operator is ambiguous between multiple overloads',
                        [
                            f"candidate: {signature.function_type}"
                            for _, signature in best
                        ],
                        where=where,
                    )
                    return ANY
        source_trait, signature = best[0]
        if isinstance(value, dict):
            value['resolved_operator_trait'] = source_trait
        if operator_name in COMPARISON_OPERATORS:
            return BOOLEAN
        return signature.return_type

    def _infer_unary_operator_overload(
        self,
        value: Any,
        operator_name: Optional[str],
        right_type: str,
    ) -> Optional[str]:
        if operator_name is None:
            return None
        trait_name = UNARY_OPERATOR_TRAITS.get(operator_name)
        if trait_name is None:
            return None
        method_name = trait_method(trait_name)
        where = f'operator {operator_name}'
        signatures = self._operator_method_signatures(
            right_type, trait_name, method_name, where
        )
        if not signatures:
            return None
        required = self.traits[trait_name].methods[method_name][0]
        valid: list[tuple[str, _Signature]] = []
        invalid: list[tuple[str, _Signature]] = []
        async_found = False
        for source_trait, signature in signatures:
            if signature.is_async:
                async_found = True
                continue
            if signature.parameter_types or \
                    not self._method_signature_compatible(required, signature):
                invalid.append((source_trait, signature))
                continue
            valid.append((source_trait, signature))
        if not valid:
            if invalid:
                _, signature = invalid[0]
                if not self._method_signature_compatible(required, signature):
                    self._error(
                        f"operator method '{method_name}' does not satisfy {trait_name}.{method_name}",
                        [
                            f"required: {required.function_type}",
                            f"found: {signature.function_type}",
                        ],
                        where=where,
                    )
                else:
                    self._error(
                        f"operator method '{method_name}' must not accept operands",
                        [f"found: {signature.function_type}"],
                        where=where,
                    )
                return ANY
            if async_found:
                self._error(
                    f"operator method '{method_name}' cannot be async",
                    ['remove async from the operator method'],
                    where=where,
                )
            return ANY
        source_trait, signature = valid[0]
        if isinstance(value, dict):
            value['resolved_operator_trait'] = source_trait
        return signature.return_type

    def _infer_binary(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        operator = value.get('operator')
        operator_name = operator.get('value') if isinstance(operator, dict) else None
        left_node = value.get('left')
        right_node = value.get('right')

        if operator_name in TYPE_COMPARISON_OPERATORS:
            self._infer(left_node)
            if self._identifier_name(right_node) is None:
                self._infer(right_node)
            return BOOLEAN

        if operator_name == 'as':
            self._infer(left_node)
            target_type = self._type_name_from_node(right_node)
            if target_type is None:
                self._infer(right_node)
                return ANY
            return target_type

        if operator_name == '??':
            left_type = self._infer(left_node)
            right_type = self._infer(right_node)
            if left_type == NOVA:
                return right_type
            if right_type == NOVA:
                return left_type
            if left_type == ANY:
                return right_type
            if right_type == ANY:
                return left_type
            if left_type == right_type:
                return left_type
            if self._assignable(left_type, right_type):
                return left_type
            if self._assignable(right_type, left_type):
                return right_type
            return ANY

        if operator_name == ':>':
            left_type = self._infer(left_node)
            if isinstance(right_node, dict) and right_node.get('type') == ParserTokenType.CALL_EXPRESSION:
                call_value = dict(right_node.get('value') or {})
                call_value['arguments'] = [left_node] + list(call_value.get('arguments', []))
                return self._infer_call(call_value)
            if isinstance(right_node, dict) and right_node.get('type') == ParserTokenType.METHOD_CALL:
                method_value = dict(right_node.get('value') or {})
                owner = method_value.get('owner')
                owner_name = self._identifier_name(owner)
                arguments = [left_node] + list(method_value.get('arguments', []))
                argument_types = [self._infer(argument) for argument in arguments]
                method_name = self._identifier_name(method_value.get('method'))
                if owner_name in NATIVE_METHOD_TYPES and method_name is not None:
                    if method_name not in NATIVE_METHOD_NAMES.get(owner_name, frozenset()):
                        self._error(
                            f"'{owner_name}' has no member named '{method_name}'",
                            where='member access',
                        )
                        return ANY
                    return self._infer_native_method(owner_name, method_name, argument_types, arguments)
                return ANY
            if isinstance(right_node, dict) and right_node.get('type') == ParserTokenType.ACCESS_EXPRESSION:
                access = right_node.get('value')
                target = access.get('target') if isinstance(access, dict) else None
                target_name = self._identifier_name(target)
                method_name = self._identifier_name(access.get('property')) if isinstance(access, dict) else None
                if target_name in NATIVE_METHOD_TYPES and method_name is not None:
                    if method_name not in NATIVE_METHOD_NAMES.get(target_name, frozenset()):
                        self._error(
                            f"'{target_name}' has no member named '{method_name}'",
                            where='member access',
                        )
                        return ANY
                    return self._infer_native_method(target_name, method_name, [left_type])
                return ANY
            if isinstance(right_node, dict) and right_node.get('type') == LexerTokenType.IDENTIFIER:
                return self._infer_call({
                    'callee': right_node,
                    'arguments': [left_node],
                })
            self._infer(right_node)
            return ANY

        left_type = self._infer(left_node)
        right_type = self._infer(right_node)
        overload = self._infer_operator_overload(
            value, operator_name, left_type, right_type
        )
        if overload is not None:
            return overload

        if operator_name in LOGICAL_OPERATORS or operator_name in COMPARISON_OPERATORS:
            return BOOLEAN

        return self._binary_result(operator_name, left_type, right_type, bool(value.get('typed')))

    def _binary_result(self, operator: Optional[str], left: str, right: str, typed: bool) -> str:
        if operator is None:
            return ANY
        if left == ANY or right == ANY:
            return ANY
        if left == NOVA or right == NOVA:
            return ANY

        if operator == '+':
            if left == CHAR and right in {CHAR, STRING}:
                return STRING
            if left == STRING and right == CHAR:
                return STRING

        if operator == '*':
            if left == STRING and right in NUMERIC_TYPES:
                return STRING
            if right == STRING and left in NUMERIC_TYPES:
                return STRING
            if left == STRING and right == STRING:
                return INTEGER
            if _is_array_type(left) and right in NUMERIC_TYPES:
                return left
            if _is_array_type(right) and left in NUMERIC_TYPES:
                return right

        if operator == '/':
            if left == STRING and right in {INTEGER, STRING}:
                return ARRAY
            if _is_array_type(left) and right in NUMERIC_TYPES:
                return left
            if left in NUMERIC_TYPES and _is_array_type(right):
                return right

        if operator == '-' and _is_array_type(left):
            return left
        if operator == '+' and _is_array_type(left) and _is_array_type(right):
            return self._common_array_type(left, right)
        if operator == '+' and left == MAP and right == MAP:
            return MAP

        if left == BOOLEAN or right == BOOLEAN:
            if left == CHAR or right == CHAR:
                return ANY
            return BOOLEAN

        if left in NUMERIC_TYPES and right in NUMERIC_TYPES:
            # Untyped operations cast the right operand to the left type.
            # Typed operations cast the left operand to the right type.
            target = right if typed else left
            return target if target in NUMERIC_TYPES else ANY

        if left == right and left in {INTEGER, NUMBER, STRING, MAP, BOOLEAN}:
            return left
        if _is_array_type(left) and _is_array_type(right):
            return self._common_array_type(left, right)

        return ANY

    def _common_array_type(self, left: str, right: str) -> str:
        if left == right:
            return left
        left_element = _array_element_type(left)
        right_element = _array_element_type(right)
        if left_element == ANY:
            return right
        if right_element == ANY:
            return left
        if self._assignable(left_element, right_element):
            return left
        if self._assignable(right_element, left_element):
            return right
        return _array_of(_union_of_types([left_element, right_element]))

    def _check_trait_set_conflicts(
        self,
        type_name: str,
        trait_names: list[str],
        where: str,
    ) -> None:
        if len(trait_names) < 2:
            return
        normalized = self._normalized_object_name(type_name)
        info = self._object_type_info(normalized) if normalized is not None else None
        display = self._display_type_name(type_name)
        for index, first_name in enumerate(trait_names):
            first_trait = self.traits.get(first_name)
            if first_trait is None:
                continue
            for second_name in trait_names[index + 1:]:
                second_trait = self.traits.get(second_name)
                if second_trait is None:
                    continue
                shared = set(first_trait.methods) & set(second_trait.methods)
                for method_name in sorted(shared):
                    first_signatures = first_trait.methods[method_name]
                    second_signatures = second_trait.methods[method_name]
                    if not first_signatures or not second_signatures:
                        continue
                    if self._signatures_equivalent(
                        first_signatures[0], second_signatures[0]
                    ):
                        continue
                    if info is not None:
                        first_qualified = info.get('trait_methods', {}).get(
                            first_name, {}
                        ).get(method_name)
                        second_qualified = info.get('trait_methods', {}).get(
                            second_name, {}
                        ).get(method_name)
                        if first_qualified and second_qualified:
                            continue
                    self._error(
                        f"type {display} cannot satisfy {first_name} and {second_name}: method {method_name} has incompatible signatures. Add fun {first_name}.{method_name} and fun {second_name}.{method_name}.",
                        [
                            f"{first_name}.{method_name}: {first_signatures[0].function_type}",
                            f"{second_name}.{method_name}: {second_signatures[0].function_type}",
                        ],
                        where=where,
                    )
                    break

    def _check_type_parameter_constraints(
        self,
        signature: _Signature,
        mapping: dict[str, str],
        where: str,
    ) -> None:
        for parameter_name, trait_names in signature.type_parameter_constraints.items():
            actual_type = mapping.get(parameter_name)
            if actual_type is None or actual_type in (ANY, UNDEF, MIXED):
                continue
            branches = _split_union(actual_type)
            if len(branches) > 1:
                for branch in branches:
                    self._check_trait_constraint_branch(
                        branch, trait_names, parameter_name, where
                    )
            else:
                self._check_trait_constraint_branch(
                    actual_type, trait_names, parameter_name, where
                )

    def _check_trait_constraint_branch(
        self,
        actual_type: str,
        trait_names: list[str],
        parameter_name: str,
        where: str,
    ) -> None:
        for trait_name in trait_names:
            if trait_name not in self.traits:
                self._error(
                    f"unknown trait '{trait_name}' in constraint for '{parameter_name}'",
                    ['declare the trait before using it as a constraint'],
                    where=where,
                )
                continue
            if not self._type_satisfies_trait(actual_type, trait_name):
                reason = self._trait_failure_reason(actual_type, trait_name)
                self._error(
                    f"type {self._display_type_name(actual_type)} cannot satisfy {trait_name}",
                    [reason or 'does not satisfy the trait contract'],
                    where=where,
                )
        self._check_trait_set_conflicts(actual_type, trait_names, where)

    def _call_result(self, value: Any, signature: _Signature) -> str:
        if signature.is_async:
            if isinstance(value, dict):
                value['async_result_type'] = signature.return_type
            return TASK
        return signature.return_type

    def _infer_call(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        callee = value.get('callee')
        arguments = value.get('arguments')
        if not isinstance(arguments, list):
            arguments = []
        positional_nodes: list[Any] = []
        named_nodes: list[dict] = []
        for argument in arguments:
            if isinstance(argument, dict) and argument.get('type') == ParserTokenType.NAMED_ARGUMENT:
                named_nodes.append(argument)
            else:
                positional_nodes.append(argument)
        argument_types = [self._infer(argument) for argument in positional_nodes]
        type_arguments = value.get('type_arguments')
        type_argument_types = [
            self._annotation_type(type_node)
            for type_node in (type_arguments if isinstance(type_arguments, list) else [])
        ]
        module_callee = self._module_callee(callee)
        if module_callee is not None:
            info, member_name, label = module_callee
            signatures = info.functions.get(member_name)
            if not signatures:
                self._error(
                    f"module '{info.name}' has no function named '{member_name}'",
                    [f"exports: {', '.join(sorted(info.exports))}"],
                    where='function call',
                )
                return ANY
            alias = label.split('.', 1)[0]
            if label not in self.functions:
                self.functions[label] = [
                    self._qualify_signature(signature, info, alias)
                    for signature in signatures
                ]
            callee_name = label
        else:
            callee_name = self._identifier_name(callee)
            if callee_name is None:
                # Still walk the callee expression so nested checks are not lost.
                self._infer(callee)
                return ANY

        builtins = self._builtins()
        if callee_name in builtins:
            if named_nodes:
                self._error(
                    f"Builtin '{callee_name}' does not accept named arguments",
                    ['pass the arguments positionally'],
                    where=f'function call: {callee_name}',
                )
                return BUILTIN_RETURN_TYPES.get(callee_name, ANY)
            entry = builtins[callee_name]
            minimum = entry[0] if len(entry) > 0 else 0
            maximum = entry[1] if len(entry) > 1 else -1
            if maximum != -1 and len(argument_types) > maximum:
                self._error(
                    f"Builtin '{callee_name}' received too many arguments",
                    [f"expected at most {maximum}", f"but {len(argument_types)} were passed"],
                    where=f'function call: {callee_name}',
                )
            if len(argument_types) < minimum:
                self._error(
                    f"Builtin '{callee_name}' received too few arguments",
                    [f"expected at least {minimum}", f"but {len(argument_types)} were passed"],
                    where=f'function call: {callee_name}',
                )
            return BUILTIN_RETURN_TYPES.get(callee_name, ANY)

        if callee_name in self.functions:
            candidates = self.functions[callee_name]
            if type_argument_types:
                candidates = [
                    candidate for candidate in candidates
                    if len(candidate.type_parameters) == len(type_argument_types)
                ]
                if not candidates:
                    self._error(
                        f"No generic overload of '{callee_name}' accepts {len(type_argument_types)} type arguments",
                        [f"available templates: {len(self.functions[callee_name])}"],
                        where=f'function call: {callee_name}',
                    )
                    return ANY
            if named_nodes:
                if len(candidates) != 1:
                    self._error(
                        f"Named arguments for '{callee_name}' require a single overload",
                        [f"found {len(candidates)} overloads"],
                        where=f'function call: {callee_name}',
                    )
                    return self._call_result(value, candidates[0]) if candidates else ANY
                candidate = candidates[0]
                explicit_mapping: dict[str, str] = {}
                if type_argument_types:
                    explicit_mapping = dict(
                        zip(candidate.type_parameters, type_argument_types)
                    )
                    candidate = self._specialize_signature(
                        candidate, explicit_mapping
                    )
                fixed_count = (
                    candidate.variadic_index
                    if candidate.variadic and candidate.variadic_index is not None
                    else len(candidate.parameter_types)
                )
                ordered_types: list[Optional[str]] = [None] * fixed_count
                for index, argument_type in enumerate(argument_types):
                    if index < fixed_count:
                        ordered_types[index] = argument_type
                    elif candidate.variadic:
                        if candidate.variadic_type is not None and \
                                not self._assignable(candidate.variadic_type, argument_type):
                            self._assign_error(
                                f'function call: {callee_name}',
                                candidate.variadic_type,
                                argument_type,
                            )
                    else:
                        self._error(
                            f"Function '{callee_name}' received too many arguments",
                            [f"expected at most {fixed_count}"],
                            where=f'function call: {callee_name}',
                        )
                        break
                for named in named_nodes:
                    named_value = named.get('value')
                    if not isinstance(named_value, dict):
                        continue
                    name = self._identifier_name(named_value.get('name'))
                    if name is None:
                        continue
                    if name not in candidate.parameter_names[:fixed_count]:
                        self._error(
                            f"Function '{callee_name}' has no parameter named '{name}'",
                            [f"parameters: {', '.join(candidate.parameter_names[:fixed_count])}"],
                            where=f'function call: {callee_name}',
                        )
                        continue
                    index = candidate.parameter_names.index(name)
                    if ordered_types[index] is not None:
                        self._error(
                            f"Function '{callee_name}' received '{name}' more than once",
                            ['pass each named argument once'],
                            where=f'function call: {callee_name}',
                        )
                        continue
                    ordered_types[index] = self._infer(named_value.get('value'))
                for index, argument_type in enumerate(ordered_types):
                    if argument_type is None:
                        if index < candidate.min_argc:
                            self._error(
                                f"Function '{callee_name}' is missing required parameter '{candidate.parameter_names[index]}'",
                                [f"at least {candidate.min_argc} arguments are required"],
                                where=f'function call: {callee_name}',
                            )
                        continue
                    if not self._assignable(candidate.parameter_types[index], argument_type, candidate.parameter_weak[index]):
                        self._assign_error(
                            f'function call: {callee_name}',
                            candidate.parameter_types[index],
                            argument_type,
                        )
                if candidate.type_parameter_constraints:
                    constraint_mapping = explicit_mapping
                    if not constraint_mapping:
                        constraint_args = [
                            argument_type
                            for argument_type in ordered_types
                            if argument_type is not None
                        ]
                        constraint_mapping = self._infer_type_argument_mapping(
                            candidate, constraint_args
                        )
                    self._check_type_parameter_constraints(
                        candidate,
                        constraint_mapping,
                        f'function call: {callee_name}',
                    )
                return self._call_result(value, candidate)

            explicit_mapping: dict[str, str] = {}
            if type_argument_types:
                explicit_mapping = dict(
                    zip(candidates[0].type_parameters, type_argument_types)
                )
                candidates = [
                    self._specialize_signature(candidate, explicit_mapping)
                    for candidate in candidates
                ]
            matches = [
                candidate for candidate in candidates
                if self._signature_matches(candidate, argument_types)
            ]
            if matches:
                selected = matches[0]
                if not type_argument_types:
                    mapping = self._infer_type_argument_mapping(
                        selected, argument_types
                    )
                    if mapping:
                        selected = self._specialize_signature(selected, mapping)
                else:
                    mapping = explicit_mapping
                self._check_type_parameter_constraints(
                    selected,
                    mapping,
                    f'function call: {callee_name}',
                )
                return self._call_result(value, selected)
            self._error(
                f"No overload of '{callee_name}' accepts the given arguments",
                [
                    f"argument types: {', '.join(argument_types)}",
                    f"candidates: {len(candidates)}",
                ],
                where=f'function call: {callee_name}',
            )
            return self._call_result(value, candidates[0]) if candidates else ANY

        variable = self._lookup(callee_name)
        if variable is not None and isinstance(variable.type, str) and variable.type.startswith('fun['):
            signature = self._signature_from_function_type(variable.type, callee_name)
            if signature is None:
                return ANY
            if getattr(variable, 'async_value', False):
                signature.is_async = True
            mapping = self._infer_type_argument_mapping(signature, argument_types)
            if mapping:
                signature = self._specialize_signature(signature, mapping)
            if named_nodes:
                self._error(
                    f"Function value '{callee_name}' does not accept named arguments",
                    ['pass the arguments positionally'],
                    where=f'function call: {callee_name}',
                )
                return self._call_result(value, signature)
            if signature.variadic:
                fixed = signature.variadic_index if signature.variadic_index is not None else 0
                if len(argument_types) < signature.min_argc:
                    self._error(
                        f"Function value '{callee_name}' received too few arguments",
                        [f"expected at least {signature.min_argc}"],
                        where=f'function call: {callee_name}',
                    )
                    return self._call_result(value, signature)
                for index in range(min(fixed, len(argument_types))):
                    if not self._assignable(
                        signature.parameter_types[index],
                        argument_types[index],
                        signature.parameter_weak[index],
                    ):
                        self._assign_error(
                            f'function call: {callee_name}',
                            signature.parameter_types[index],
                            argument_types[index],
                        )
                        break
                if signature.variadic_type is not None:
                    for index in range(fixed, len(argument_types)):
                        if not self._assignable(
                            signature.variadic_type,
                            argument_types[index],
                        ):
                            self._assign_error(
                                f'function call: {callee_name}',
                                signature.variadic_type,
                                argument_types[index],
                            )
                            break
                return self._call_result(value, signature)
            if len(argument_types) > len(signature.parameter_types):
                self._error(
                    f"Function value '{callee_name}' received too many arguments",
                    [f"expected {len(signature.parameter_types)}"],
                    where=f'function call: {callee_name}',
                )
            elif len(argument_types) < len(signature.parameter_types):
                self._error(
                    f"Function value '{callee_name}' received too few arguments",
                    [f"expected {len(signature.parameter_types)}"],
                    where=f'function call: {callee_name}',
                )
            for expected, actual in zip(signature.parameter_types, argument_types):
                if not self._assignable(expected, actual):
                    self._assign_error(
                        f'function call: {callee_name}',
                        expected,
                        actual,
                    )
            return self._call_result(value, signature)

        # Unknown callees are skipped, never rejected.
        return ANY

    def _infer_spawn(self, value: Any) -> str:
        ## The enclosed call is still checked (arity, known signatures), but
        ## the expression's static type is always the opaque `task` handle.
        if isinstance(value, dict):
            call = value.get('call')
            call_type = self._infer(call)
            async_result = None
            if isinstance(call, dict):
                async_result = call.get('async_result_type')
                if async_result is None and isinstance(call.get('value'), dict):
                    async_result = call['value'].get('async_result_type')
            if async_result is not None:
                value['async_result_type'] = async_result
            elif call_type != TASK:
                value['async_result_type'] = call_type
        return TASK

    def _await_result_type(self, operand: Any) -> Optional[str]:
        if not isinstance(operand, dict):
            return None
        result = operand.get('async_result_type')
        if result is not None:
            return result
        inner = operand.get('value')
        if isinstance(inner, dict):
            return inner.get('async_result_type')
        return None

    def _infer_await(self, value: Any) -> str:
        if self.in_function and not self.in_async_function:
            self._error(
                "'await' is only valid inside an async function",
                ['mark the enclosing function as async'],
                where='await expression',
            )
        operand_type = self._infer(value)
        if operand_type not in (TASK, ANY):
            self._error(
                "'await' expects a task value",
                [f"but {operand_type} was encountered"],
                where='await expression',
            )
            return ANY
        return self._await_result_type(value) or ANY

    @staticmethod
    def _substitute_type_parameters(type_text: str, mapping: dict[str, str]) -> str:
        result = type_text
        for name, actual in mapping.items():
            result = re.sub(rf'\b{re.escape(name)}\b', actual, result)
        return result

    def _specialize_signature(
        self,
        signature: _Signature,
        mapping: dict[str, str],
    ) -> _Signature:
        if not mapping:
            return signature
        parameter_types = [
            self._substitute_type_parameters(type_text, mapping)
            for type_text in signature.parameter_types
        ]
        return_type = self._substitute_type_parameters(signature.return_type, mapping)
        variadic_type = (
            self._substitute_type_parameters(signature.variadic_type, mapping)
            if signature.variadic_type is not None
            else None
        )
        rendered_params = list(parameter_types)
        if signature.variadic and signature.variadic_index is not None and \
                0 <= signature.variadic_index < len(rendered_params):
            rendered_params[signature.variadic_index] = \
                rendered_params[signature.variadic_index] + '...'
        function_type = 'fun[' + ', '.join(rendered_params + [return_type]) + ']'
        return _Signature(
            signature.name,
            signature.parameter_names,
            parameter_types,
            signature.parameter_weak,
            signature.min_argc,
            return_type,
            signature.return_weak,
            signature.allows_error,
            function_type,
            signature.type_parameters,
            signature.variadic,
            signature.variadic_index,
            variadic_type,
            signature.type_parameter_constraints,
            signature.is_async,
        )

    def _infer_type_argument_mapping(
        self,
        signature: _Signature,
        argument_types: list[str],
    ) -> dict[str, str]:
        if not signature.type_parameters:
            return {}
        mapped: dict[str, list[str]] = {}
        fixed = (
            signature.variadic_index
            if signature.variadic and signature.variadic_index is not None
            else len(signature.parameter_types)
        )
        for index in range(min(fixed, len(argument_types))):
            parameter_type = signature.parameter_types[index]
            if parameter_type in signature.type_parameters and \
                    argument_types[index] != ANY:
                mapped.setdefault(parameter_type, []).append(argument_types[index])
        if signature.variadic and signature.variadic_type in signature.type_parameters:
            tail = argument_types[fixed:]
            if tail:
                for argument_type in tail:
                    if argument_type != ANY:
                        mapped.setdefault(signature.variadic_type, []).append(argument_type)
            else:
                mapped.setdefault(signature.variadic_type, []).append(UNDEF)
        return {
            name: _union_of_types(types)
            for name, types in mapped.items()
        }

    def _signature_matches(self, signature: _Signature, argument_types: list[str]) -> bool:
        if signature.variadic:
            fixed = signature.variadic_index if signature.variadic_index is not None else 0
            if len(argument_types) < signature.min_argc:
                return False
            for index in range(min(fixed, len(argument_types))):
                parameter_type = signature.parameter_types[index]
                parameter_weak = signature.parameter_weak[index]
                if parameter_type in signature.type_parameters:
                    continue
                if parameter_type == ANY or argument_types[index] == ANY:
                    continue
                if not self._assignable(parameter_type, argument_types[index], parameter_weak):
                    return False
            if signature.variadic_type is not None and \
                    signature.variadic_type not in signature.type_parameters:
                for index in range(fixed, len(argument_types)):
                    if argument_types[index] == ANY:
                        continue
                    if not self._assignable(signature.variadic_type, argument_types[index]):
                        return False
            return True
        if len(argument_types) > len(signature.parameter_types):
            return False
        if len(argument_types) < signature.min_argc:
            return False
        for index, argument_type in enumerate(argument_types):
            parameter_type = signature.parameter_types[index]
            parameter_weak = signature.parameter_weak[index]
            if parameter_type in signature.type_parameters:
                continue
            if parameter_type == ANY or argument_type == ANY:
                continue
            if not self._assignable(parameter_type, argument_type, parameter_weak):
                return False
        return True

    def _signature_from_function_type(self, type_text: str, name: str) -> Optional[_Signature]:
        from . import typespec as _ts
        try:
            spec = _ts.type_of_str(type_text)
        except Exception:
            return None
        if spec.kind is not _ts.Kind.FUNCTION:
            return None
        parameter_types = [_ts.render(parameter) for parameter in spec.params]
        return_type = _ts.render(spec.returns) if spec.returns is not None else ANY
        variadic = bool(spec.rest)
        variadic_index = len(parameter_types) - 1 if variadic and parameter_types else None
        variadic_type = parameter_types[-1] if variadic and parameter_types else None
        min_argc = len(parameter_types) - 1 if variadic else len(parameter_types)
        known_types = set(NATIVE_TYPE_NAMES) | set(self.object_types) | set(self.traits)
        type_parameters: list[str] = []
        for parameter_type in parameter_types:
            if parameter_type.isidentifier() and \
                    parameter_type[:1].isupper() and \
                    parameter_type not in known_types and \
                    parameter_type not in type_parameters:
                type_parameters.append(parameter_type)
        return _Signature(
            name,
            [f'arg{index}' for index in range(len(parameter_types))],
            parameter_types,
            [False] * len(parameter_types),
            max(0, min_argc),
            return_type,
            False,
            False,
            type_text,
            type_parameters,
            variadic,
            variadic_index,
            variadic_type,
        )

    def _collect_return_types(self, node: Any, result: Optional[list[str]] = None) -> list[str]:
        if result is None:
            result = []
        if isinstance(node, list):
            for item in node:
                self._collect_return_types(item, result)
            return result
        if not isinstance(node, dict):
            return result
        if node.get('type') == ParserTokenType.FUN_EXPRESSION:
            return result
        if node.get('type') == ParserTokenType.RETURN_EXPRESSION:
            result.append(self._infer(node.get('value')))
            return result
        value = node.get('value')
        if isinstance(value, dict):
            self._collect_return_types(value, result)
        elif isinstance(value, list):
            self._collect_return_types(value, result)
        return result

    def _infer_lambda(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        arguments = value.get('args')
        if not isinstance(arguments, list):
            arguments = []
        type_parameters = value.get('type_parameters')
        if not isinstance(type_parameters, list):
            type_parameters = []
        raw_constraints = value.get('type_parameter_constraints')
        type_parameter_constraints: dict[str, list[str]] = {}
        if isinstance(raw_constraints, dict):
            for parameter_name, trait_names in raw_constraints.items():
                if isinstance(parameter_name, str) and isinstance(trait_names, list):
                    type_parameter_constraints[parameter_name] = [
                        trait_name for trait_name in trait_names
                        if isinstance(trait_name, str)
                    ]
        variadic = bool(value.get('variadic'))
        is_async = bool(value.get('is_async'))
        variadic_index = value.get('variadic_index')
        if not isinstance(variadic_index, int):
            variadic_index = None
        parameter_names: list[str] = []
        parameter_types: list[str] = []
        parameter_weak: list[bool] = []
        for index, argument in enumerate(arguments):
            argument_value = argument.get('value') if isinstance(argument, dict) else None
            type_node = argument_value.get('type') if isinstance(argument_value, dict) else None
            parameter_names.append(
                self._identifier_name(argument_value.get('identifier'))
                if isinstance(argument_value, dict) else None
            )
            if not parameter_names[-1]:
                parameter_names[-1] = f'arg{index}'
            parameter_types.append(
                self._signature_annotation_type(type_node, type_parameters)
            )
            parameter_weak.append(self._annotation_weak(type_node))
        variadic_type = (
            parameter_types[variadic_index]
            if variadic and variadic_index is not None
            and 0 <= variadic_index < len(parameter_types)
            else None
        )
        name = value.get('name') if isinstance(value.get('name'), str) else None
        return_node = value.get('return')
        if isinstance(return_node, dict):
            return_type = self._signature_annotation_type(
                return_node, type_parameters, NOVA
            )
            return_weak = self._annotation_weak(return_node)
            allows_error = self._annotation_error_union(return_node)
        else:
            return_type = ANY
            return_weak = False
            allows_error = False
        min_argc = value.get('min_argc')
        if not isinstance(min_argc, int):
            min_argc = len(parameter_types)
        rendered_params = list(parameter_types)
        if variadic and variadic_index is not None and 0 <= variadic_index < len(rendered_params):
            rendered_params[variadic_index] = rendered_params[variadic_index] + '...'
        function_type = 'fun[' + ', '.join(rendered_params + [return_type]) + ']'
        signature = _Signature(
            name or '<lambda>',
            parameter_names,
            parameter_types,
            parameter_weak,
            min_argc,
            return_type,
            return_weak,
            allows_error,
            function_type,
            type_parameters,
            variadic,
            variadic_index,
            variadic_type,
            type_parameter_constraints,
            is_async,
        )
        previous = (
            self.return_type,
            self.return_weak,
            self.return_allows_error,
            self.in_function,
            self.this_type,
            self.current_type_parameters,
            self.current_type_parameter_constraints,
            self.in_async_function,
        )
        self.return_type = return_type
        self.return_weak = return_weak
        self.return_allows_error = allows_error
        self.in_function = True
        self.current_type_parameters = set(type_parameters)
        self.current_type_parameter_constraints = dict(type_parameter_constraints)
        self.in_async_function = is_async
        self._scope_push()
        try:
            for index, parameter_name in enumerate(parameter_names):
                bound_type = parameter_types[index]
                if variadic and variadic_index == index:
                    bound_type = _array_of(bound_type)
                self._bind(parameter_name, bound_type, True, parameter_weak[index])
            if name is not None:
                self._bind(name, signature.function_type or ANY, True, False)
            block = value.get('block')
            if isinstance(block, dict):
                self._infer(block)
            if return_node is None:
                collected = self._collect_return_types(block)
                if collected:
                    return_type = _union_of_types(collected)
                    signature.return_type = return_type
                    rendered_params = list(parameter_types)
                    if variadic and variadic_index is not None and 0 <= variadic_index < len(rendered_params):
                        rendered_params[variadic_index] = rendered_params[variadic_index] + '...'
                    signature.function_type = 'fun[' + ', '.join(rendered_params + [return_type]) + ']'
        finally:
            self._scope_pop()
            (
                self.return_type,
                self.return_weak,
                self.return_allows_error,
                self.in_function,
                self.this_type,
                self.current_type_parameters,
                self.current_type_parameter_constraints,
                self.in_async_function,
            ) = previous
        return signature.function_type or FUNCTION

    def _signatures_equivalent(
        self,
        left: _Signature,
        right: _Signature,
    ) -> bool:
        if left.variadic != right.variadic:
            return False
        if len(left.parameter_types) != len(right.parameter_types):
            return False
        for left_type, right_type in zip(
            left.parameter_types, right.parameter_types
        ):
            if not (
                self._assignable(left_type, right_type)
                and self._assignable(right_type, left_type)
            ):
                return False
        if left.variadic_type is not None and right.variadic_type is not None:
            if not (
                self._assignable(left.variadic_type, right.variadic_type)
                and self._assignable(right.variadic_type, left.variadic_type)
            ):
                return False
        return (
            self._assignable(left.return_type, right.return_type)
            and self._assignable(right.return_type, left.return_type)
        )

    def _trait_signatures_for_method(
        self,
        trait_names: list[str],
        method_name: str,
    ) -> list[tuple[str, list[_Signature]]]:
        available: list[tuple[str, list[_Signature]]] = []
        for trait_name in trait_names:
            trait = self.traits.get(trait_name)
            if trait is None:
                continue
            signatures = trait.methods.get(method_name)
            if signatures:
                available.append((trait_name, signatures))
        return available

    def _infer_trait_qualified_call(
        self,
        value: Any,
        trait_name: str,
        method_name: str,
        argument_types: list[str],
    ) -> str:
        trait = self.traits.get(trait_name)
        if trait is None:
            return ANY
        signatures = trait.methods.get(method_name)
        if not signatures:
            self._error(
                f"trait '{trait_name}' has no method named '{method_name}'",
                [f"methods: {', '.join(sorted(trait.methods.keys()))}"],
                where='trait-qualified call',
            )
            return ANY
        if not argument_types:
            self._error(
                f"trait-qualified call '{trait_name}.{method_name}' needs a receiver",
                ['pass the receiver as the first argument'],
                where='trait-qualified call',
            )
            return ANY
        receiver_type = argument_types[0]
        if receiver_type != ANY and \
                not self._type_satisfies_trait(receiver_type, trait_name):
            reason = self._trait_failure_reason(receiver_type, trait_name)
            self._error(
                f"type {self._display_type_name(receiver_type)} cannot satisfy {trait_name}",
                [reason or 'does not satisfy the trait contract'],
                where='trait-qualified call',
            )
            return ANY
        method_argument_types = argument_types[1:]
        matches = [
            signature for signature in signatures
            if self._signature_matches(signature, method_argument_types)
        ]
        if not matches:
            self._error(
                f"No overload of '{trait_name}.{method_name}' accepts the given arguments",
                [f"argument types: {', '.join(method_argument_types)}"],
                where='trait-qualified call',
            )
            return self._call_result(value, signatures[0])
        value['resolved_trait'] = trait_name
        return self._call_result(value, matches[0])

    def _infer_trait_value_method(
        self,
        value: Any,
        trait_name: str,
        method_name: str,
        argument_types: list[str],
    ) -> str:
        trait = self.traits.get(trait_name)
        if trait is None:
            return ANY
        signatures = trait.methods.get(method_name)
        if not signatures:
            self._error(
                f"trait '{trait_name}' has no method named '{method_name}'",
                [f"methods: {', '.join(sorted(trait.methods.keys()))}"],
                where='method call',
            )
            return ANY
        matches = [
            signature for signature in signatures
            if self._signature_matches(signature, argument_types)
        ]
        if not matches:
            self._error(
                f"No overload of '{trait_name}.{method_name}' accepts the given arguments",
                [f"argument types: {', '.join(argument_types)}"],
                where='method call',
            )
            return self._call_result(value, signatures[0])
        value['resolved_trait'] = trait_name
        return self._call_result(value, matches[0])

    def _infer_constrained_method_call(
        self,
        value: Any,
        parameter_name: str,
        method_name: str,
        argument_types: list[str],
    ) -> Optional[str]:
        constraints = self.current_type_parameter_constraints.get(
            parameter_name, []
        )
        if not constraints:
            return None
        available = self._trait_signatures_for_method(constraints, method_name)
        if not available:
            self._error(
                f"type parameter '{parameter_name}' has no method named '{method_name}'",
                [f"constraints: {', '.join(constraints)}"],
                where='method call',
            )
            return ANY
        if len(available) > 1:
            first = available[0][1][0]
            for trait_name, signatures in available[1:]:
                if signatures and not self._signatures_equivalent(first, signatures[0]):
                    names = ' and '.join(name for name, _ in available)
                    self._error(
                        f"generic parameter {parameter_name} is constrained by {names}, which require incompatible signatures for {method_name}. Use a single trait constraint or a trait-qualified call.",
                        [
                            f"{name}.{method_name}: {signatures[0].function_type}"
                            for name, signatures in available
                            if signatures
                        ],
                        where='method call',
                    )
                    return ANY
        trait_name, signatures = available[0]
        matches = [
            signature for signature in signatures
            if self._signature_matches(signature, argument_types)
        ]
        if not matches:
            self._error(
                f"No overload of '{trait_name}.{method_name}' accepts the given arguments",
                [f"argument types: {', '.join(argument_types)}"],
                where='method call',
            )
            return self._call_result(value, signatures[0])
        value['resolved_trait'] = trait_name
        return self._call_result(value, matches[0])

    def _infer_concrete_trait_method(
        self,
        value: Any,
        object_name: str,
        method_name: str,
        argument_types: list[str],
    ) -> Optional[str]:
        info = self._object_type_info(object_name)
        if info is None:
            return None
        qualified: list[tuple[str, list[_Signature]]] = []
        for trait_name, methods in info.get('trait_methods', {}).items():
            signatures = methods.get(method_name)
            if signatures:
                qualified.append((trait_name, signatures))
        if qualified:
            if len(qualified) > 1:
                first = qualified[0][1][0]
                for trait_name, signatures in qualified[1:]:
                    if signatures and not self._signatures_equivalent(first, signatures[0]):
                        names = ' and '.join(
                            f'{name}.{method_name}' for name, _ in qualified
                        )
                        self._error(
                            f"call to {method_name} is ambiguous between {names}. Cast the value to one trait or use Trait.method.",
                            [
                                f"{name}.{method_name}: {signatures[0].function_type}"
                                for name, signatures in qualified
                                if signatures
                            ],
                            where='method call',
                        )
                        return ANY
            trait_name, signatures = qualified[0]
            matches = [
                signature for signature in signatures
                if self._signature_matches(signature, argument_types)
            ]
            if not matches:
                self._error(
                    f"No overload of '{trait_name}.{method_name}' accepts the given arguments",
                    [f"argument types: {', '.join(argument_types)}"],
                    where='method call',
                )
                return self._call_result(value, signatures[0])
            value['resolved_trait'] = trait_name
            return self._call_result(value, matches[0])
        defaults: list[tuple[str, list[_Signature]]] = []
        for trait in self.traits.values():
            if method_name not in trait.default_methods:
                continue
            if not self._type_satisfies_trait(object_name, trait.name):
                continue
            signatures = trait.methods.get(method_name, [])
            if signatures:
                defaults.append((trait.name, signatures))
        if defaults:
            if len(defaults) > 1:
                first = defaults[0][1][0]
                for trait_name, signatures in defaults[1:]:
                    if signatures and not self._signatures_equivalent(first, signatures[0]):
                        names = ' and '.join(
                            f'{name}.{method_name}' for name, _ in defaults
                        )
                        self._error(
                            f"call to {method_name} is ambiguous between {names}. Cast the value to one trait or use Trait.method.",
                            [
                                f"{name}.{method_name}: {signatures[0].function_type}"
                                for name, signatures in defaults
                                if signatures
                            ],
                            where='method call',
                        )
                        return ANY
            trait_name, signatures = defaults[0]
            matches = [
                signature for signature in signatures
                if self._signature_matches(signature, argument_types)
            ]
            if not matches:
                self._error(
                    f"No overload of '{trait_name}.{method_name}' accepts the given arguments",
                    [f"argument types: {', '.join(argument_types)}"],
                    where='method call',
                )
                return self._call_result(value, signatures[0])
            value['resolved_trait'] = trait_name
            return self._call_result(value, matches[0])
        return None

    def _infer_module_method(
        self,
        alias: str,
        info: _ModuleTypeInfo,
        method_name: str,
        argument_types: list[str],
        call_node: Any = None,
    ) -> str:
        signatures = info.functions.get(method_name)
        if not signatures:
            variable_type = info.variables.get(method_name)
            if isinstance(variable_type, str) and variable_type.startswith('fun['):
                signature = self._signature_from_function_type(variable_type, method_name)
                if signature is not None:
                    signatures = [signature]
        if not signatures:
            self._error(
                f"module '{info.name}' has no function named '{method_name}'",
                [f"exports: {', '.join(sorted(info.exports))}"],
                where='function call',
            )
            return ANY
        label = f'{alias}.{method_name}'
        if label not in self.functions:
            self.functions[label] = [
                self._qualify_signature(signature, info, alias)
                for signature in signatures
            ]
        candidates = self.functions[label]
        matches = [
            candidate for candidate in candidates
            if self._signature_matches(candidate, argument_types)
        ]
        if matches:
            selected = matches[0]
            mapping = self._infer_type_argument_mapping(
                selected, argument_types
            )
            if mapping:
                selected = self._specialize_signature(selected, mapping)
            self._check_type_parameter_constraints(
                selected, mapping, f'function call: {label}'
            )
            return self._call_result(call_node, selected)
        candidate = candidates[0]
        if candidate.variadic:
            if len(argument_types) < candidate.min_argc:
                self._error(
                    f"Function '{label}' received too few arguments",
                    [f"expected at least {candidate.min_argc}"],
                    where=f'function call: {label}',
                )
        elif len(argument_types) > len(candidate.parameter_types):
            self._error(
                f"Function '{label}' received too many arguments",
                [f"expected at most {len(candidate.parameter_types)}"],
                where=f'function call: {label}',
            )
        elif len(argument_types) < candidate.min_argc:
            self._error(
                f"Function '{label}' received too few arguments",
                [f"expected at least {candidate.min_argc}"],
                where=f'function call: {label}',
            )
        else:
            for index, argument_type in enumerate(argument_types):
                expected = candidate.parameter_types[index]
                if argument_type == ANY:
                    continue
                if not self._assignable(
                    expected,
                    argument_type,
                    candidate.parameter_weak[index],
                ):
                    self._assign_error(
                        f'function call: {label}',
                        expected,
                        argument_type,
                    )
                    break
        return self._call_result(call_node, candidate)

    def _infer_method_call(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        owner_node = value.get('owner')
        owner_name = self._identifier_name(owner_node)
        method_name = self._identifier_name(value.get('method'))
        arguments = value.get('arguments')
        argument_nodes = arguments if isinstance(arguments, list) else []
        argument_types = [self._infer(argument) for argument in argument_nodes]
        if owner_name is not None and owner_name in self.traits and method_name is not None:
            return self._infer_trait_qualified_call(
                value, owner_name, method_name, argument_types
            )
        if owner_name in NATIVE_METHOD_TYPES and method_name is not None:
            if method_name not in NATIVE_METHOD_NAMES.get(owner_name, frozenset()):
                self._error(
                    f"'{owner_name}' has no member named '{method_name}'",
                    [f"available members: {', '.join(sorted(NATIVE_METHOD_NAMES.get(owner_name, ())))}"],
                    where='member access',
                )
                return ANY
            return self._infer_native_method(owner_name, method_name, argument_types, argument_nodes)
        owner_type = self._infer(owner_node)
        if isinstance(owner_type, str) and owner_type.startswith('module:'):
            module_name = owner_type.split(':', 1)[1]
            info = self.module_values.get(module_name)
            if info is not None and method_name is not None:
                return self._infer_module_method(
                    module_name, info, method_name, argument_types, value
                )
        if isinstance(owner_type, str):
            owner_trait = self._trait_name(owner_type)
            if owner_trait is not None and method_name is not None:
                return self._infer_trait_value_method(
                    value, owner_trait, method_name, argument_types
                )
            if owner_type in self.current_type_parameter_constraints and \
                    method_name is not None:
                constrained = self._infer_constrained_method_call(
                    value, owner_type, method_name, argument_types
                )
                if constrained is not None:
                    return constrained
        if owner_name is not None and owner_name in self.object_types:
            static_info = self.object_types[owner_name]
            static_methods = static_info.get('static_methods', {}).get(method_name)
            if static_methods:
                has_named = any(
                    isinstance(node, dict) and isinstance(node.get('name'), str)
                    for node in argument_nodes
                )
                if has_named:
                    return self._call_result(value, static_methods[0])
                matches = [signature for signature in static_methods if self._signature_matches(signature, argument_types)]
                return self._call_result(
                    value, matches[0] if matches else static_methods[0]
                )
            self._error(
                f"'{owner_name}' has no static method named '{method_name}'",
                [f"available static methods: {', '.join(sorted(static_info.get('static_methods', {}).keys()))}"],
                where='static method call',
            )
            return ANY
        if method_name is not None and isinstance(owner_type, str):
            owner_head = owner_type.lstrip('&').split('[', 1)[0]
            if owner_head in NATIVE_METHOD_TYPES:
                if argument_nodes:
                    argument_types = [owner_type] + argument_types
                return self._infer_native_method(owner_head, method_name, argument_types)
        if method_name is not None and isinstance(owner_type, str) and owner_type.startswith(f'{OBJECT}:'):
            object_name = owner_type.split(':', 1)[1]
            info = self._object_type_info(object_name)
            if info is not None:
                methods = info.get('methods', {}).get(method_name)
                if methods:
                    return self._call_result(value, methods[0])
                trait_result = self._infer_concrete_trait_method(
                    value, object_name, method_name, argument_types
                )
                if trait_result is not None:
                    return trait_result
                if self.in_trait_body is not None and \
                        info.get('trait_name') == self.in_trait_body[0]:
                    trait_name, trait_method = self.in_trait_body
                    self._error(
                        f"trait method {trait_method} uses member {method_name} which is not declared in the trait. Declare {method_name} in the trait or remove the usage.",
                        [
                            f"declared members: {', '.join(sorted(info.get('methods', {}).keys()))}",
                        ],
                        where='trait default method',
                    )
                    return ANY
                self._error(
                    f"'{object_name}' has no method named '{method_name}'",
                    [f"available methods: {', '.join(sorted(info.get('methods', {}).keys()))}"],
                    where='method call',
                )
                return ANY
        return ANY

    def _infer_native_method(
        self,
        receiver_type: str,
        method_name: str,
        argument_types: list[str],
        argument_nodes: Optional[list[Any]] = None,
    ) -> str:
        receiver_argument = argument_types[0] if argument_types else ANY
        is_reference = isinstance(receiver_argument, str) and receiver_argument.startswith('&')
        receiver = receiver_argument[1:] if is_reference else receiver_argument
        if receiver == ANY:
            return ANY

        def mutating_return() -> str:
            return receiver_argument if is_reference else receiver

        if receiver_type == ARRAY:
            element = _array_element_type(receiver)
            if method_name == 'push':
                value_type = argument_types[1] if len(argument_types) > 1 else ANY
                if is_reference and value_type != ANY and not self._union_branch_assignable(element, value_type):
                    self._assign_error('native method: arr.push', element, value_type)
                return mutating_return() if is_reference else _array_of(_union_of_types([element, value_type]))
            if method_name == 'add':
                addition = argument_types[1] if len(argument_types) > 1 else ANY
                addition_element = _array_element_type(addition) if _is_array_type(addition) else _set_element_type(addition) if _is_set_type(addition) else ANY
                if is_reference and addition_element != ANY and not self._union_branch_assignable(element, addition_element):
                    self._assign_error('native method: arr.add', element, addition_element)
                return mutating_return() if is_reference else _array_of(_union_of_types([element, addition_element]))
            if method_name in {'pop', 'put', 'popval', 'reverse', 'clear', 'set'}:
                return mutating_return()
            if method_name in {'popget', 'get'}:
                return element
            if method_name == 'size':
                return INTEGER
        if receiver_type == MAP:
            key_type, value_type = _map_parts(receiver)
            if method_name == 'has':
                return BOOLEAN
            if method_name == 'popget':
                return value_type
            if method_name == 'get':
                return value_type
            if method_name in {'pop', 'merge', 'clear'}:
                return mutating_return()
            if method_name == 'keys':
                return _array_of(key_type)
            if method_name == 'values':
                return _array_of(value_type)
            if method_name == 'size':
                return INTEGER
        if receiver_type == STRING:
            if method_name in {'add', 'sub', 'mul', 'reverse'}:
                return mutating_return() if is_reference else STRING
            if method_name == 'div':
                return _array_of(STRING)
            if method_name == 'get':
                return CHAR
            if method_name == 'chars':
                return _array_of(CHAR)
            if method_name in {'count', 'size'}:
                return INTEGER
        if receiver_type == CHAR:
            if method_name == 'code':
                return INTEGER
            if method_name == 'to_str':
                return STRING
            if method_name in {
                'is_digit', 'is_alpha', 'is_alnum', 'is_space',
                'is_upper', 'is_lower', 'is_ascii',
            }:
                return BOOLEAN
        if receiver_type == 'tup':
            if method_name == 'get':
                if argument_nodes and len(argument_nodes) > 1:
                    index_node = argument_nodes[1]
                    if isinstance(index_node, dict) and index_node.get('type') == LexerTokenType.INTEGER_LITERAL:
                        index = index_node.get('value')
                        elements = _type_arguments(receiver)
                        if isinstance(index, int) and 0 <= index < len(elements):
                            return elements[index]
                return ANY
            if method_name == 'size':
                return INTEGER
            if method_name == 'to_arr':
                return _array_of(ANY)
            if method_name in {'reverse', 'add'}:
                return 'tup'
        if receiver_type == SET:
            element = _set_element_type(receiver)
            if method_name in {'has', 'popget'}:
                return BOOLEAN
            if method_name == 'union':
                other = argument_types[1] if len(argument_types) > 1 else ANY
                other_element = _set_element_type(other)
                if is_reference:
                    if other_element != ANY and not self._union_branch_assignable(element, other_element):
                        self._assign_error('native method: set.union', element, other_element)
                    return mutating_return()
                return _set_of(_union_of_types([element, other_element]))
            if method_name in {'add', 'pop', 'intersection', 'difference', 'clear'}:
                return mutating_return()
            if method_name == 'size':
                return INTEGER
            if method_name == 'to_arr':
                return _array_of(element)
        if receiver_type == FILE:
            if method_name == 'open':
                return FILE
            if method_name == 'read':
                return STRING
            if method_name in {'write', 'close'}:
                return BOOLEAN
        if receiver_type == TASK:
            if method_name == 'status':
                return STRING
            if method_name in {'wait', 'cancel'}:
                return ANY
        return ANY

    def _infer_index(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        target_type = self._infer(value.get('target'))
        self._infer(value.get('index'))
        if target_type == STRING:
            return CHAR
        if _is_array_type(target_type):
            return _array_element_type(target_type)
        # Map values have no statically known element type in this slice.
        return ANY

    def _infer_slice(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        target_type = self._infer(value.get('target'))
        start = value.get('start')
        end = value.get('end')
        if start is not None:
            self._infer(start)
        if end is not None:
            self._infer(end)
        if target_type == STRING:
            return STRING
        if _is_array_type(target_type):
            return target_type
        if target_type == 'tup' or target_type.startswith('tup['):
            return target_type
        return ANY

    def _infer_access(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        target_type = self._infer(value.get('target'))
        property_name = self._identifier_name(value.get('property'))
        if property_name is None:
            return ANY
        if isinstance(target_type, str) and target_type.startswith('module:'):
            module_name = target_type.split(':', 1)[1]
            info = self.module_values.get(module_name)
            if info is not None:
                if property_name in info.functions:
                    signatures = info.functions[property_name]
                    if len(signatures) == 1 and signatures[0].function_type:
                        return self._qualify_signature(
                            signatures[0], info, module_name
                        ).function_type or FUNCTION
                    return FUNCTION
                if property_name in info.variables:
                    return self._qualify_type_text(
                        info.variables[property_name], info, module_name
                    )
                if property_name in info.object_types:
                    return f'{OBJECT}:{module_name}.{property_name}'
                if property_name in info.traits:
                    return f'{OBJECT}:{module_name}.{property_name}'
                self._error(
                    f"module '{module_name}' has no member named '{property_name}'",
                    [f"exports: {', '.join(sorted(info.exports))}"],
                    where='member access',
                )
                return ANY
        if target_type == OBJ:
            self._error(
                "member access on 'obj' requires a cast or trait",
                ["cast the value to a concrete type first"],
                where='member access',
            )
            return ANY
        if target_type == PROJECT:
            props = BUILTIN_OBJECT_TYPES[PROJECT]
            if property_name in props:
                return props[property_name]
            self._error(
                f"Project has no property named '{property_name}'",
                [f"fields: {', '.join(props)}"],
                where='member access',
            )
            return ANY
        if target_type == ERROR:
            return {
                'kind': STRING,
                'message': STRING,
                'details': ARRAY,
                'where': STRING,
                'line': INTEGER,
                'column': INTEGER,
                'cause': ERROR,
                'frames': ARRAY,
            }.get(property_name, ANY)
        if isinstance(target_type, str) and target_type.startswith(f'{OBJECT}:'):
            object_name = target_type.split(':', 1)[1]
            if object_name in self.traits:
                trait = self.traits[object_name]
                if property_name in trait.properties:
                    return trait.properties[property_name]
                self._error(
                    f"trait '{object_name}' has no property named '{property_name}'",
                    [f"properties: {', '.join(sorted(trait.properties.keys()))}"],
                    where='member access',
                )
                return ANY
            info = self._object_type_info(object_name)
            if info is not None:
                props = info.get('props', {})
                if property_name in props:
                    return props[property_name]
                if self.in_trait_body is not None and \
                        info.get('trait_name') == self.in_trait_body[0]:
                    trait_name, method_name = self.in_trait_body
                    self._error(
                        f"trait method {method_name} uses member {property_name} which is not declared in the trait. Declare {property_name} in the trait or remove the usage.",
                        [f"declared members: {', '.join(sorted(props.keys()))}"],
                        where='trait default method',
                    )
                    return ANY
                if info.get('is_enum'):
                    return f'{OBJECT}:{object_name}'
                self._error(
                    f"'{object_name}' has no member named '{property_name}'",
                    [f"available members: {', '.join(sorted(props.keys()))}"],
                    where='member access',
                )
        return ANY

    @staticmethod
    def _is_auto_type_node(type_node: Any) -> bool:
        if not isinstance(type_node, dict):
            return False
        inner = type_node.get('value')
        return isinstance(inner, dict) and (bool(inner.get('auto')) or inner.get('value') == 'auto')

    def _resolve_construction_name(self, name: str) -> str:
        seen: set[str] = set()
        while name in self.type_alias and name not in seen:
            seen.add(name)
            alias = self.type_alias[name]
            if not isinstance(alias, dict):
                break
            if alias.get('alternatives'):
                return name
            name = alias.get('value', name)
        return name

    def _infer_instantiation(self, value: Any) -> str:
        start = len(self.errors)
        line = value.get('line') if isinstance(value, dict) else None
        column = value.get('column') if isinstance(value, dict) else None
        try:
            return self._infer_instantiation_inner(value)
        finally:
            for error in self.errors[start:]:
                if getattr(error, 'line', None) is None and isinstance(line, int):
                    error.line = line + 1
                    error.column = column if isinstance(column, int) else 0

    @staticmethod
    def _substitute_signature(signature: _Signature, replacements: dict[str, str]) -> _Signature:
        def replace(type_name: str) -> str:
            for parameter, actual in replacements.items():
                type_name = type_name.replace(parameter, actual)
            return type_name
        return _Signature(
            signature.name,
            list(signature.parameter_names),
            [replace(type_name) for type_name in signature.parameter_types],
            list(signature.parameter_weak),
            signature.min_argc,
            replace(signature.return_type),
            signature.return_weak,
            signature.allows_error,
        )

    def _infer_instantiation_inner(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        type_reference = value.get('type_ref')
        if not isinstance(type_reference, dict):
            return ANY
        raw_name = type_reference.get('name')
        if not isinstance(raw_name, str):
            return ANY
        name = self._resolve_construction_name(raw_name)
        normalized = self._normalized_type_name(name)
        type_parameters = [
            parameter for parameter in type_reference.get('type_parameters', [])
            if isinstance(parameter, dict)
        ]
        alias = self.type_alias.get(raw_name)
        if isinstance(alias, dict) and not type_parameters:
            if alias.get('value') == ARRAY and isinstance(alias.get('element_type'), dict):
                type_parameters = [alias['element_type']]
            elif isinstance(alias.get('generics'), list) and alias.get('generics'):
                type_parameters = [g for g in alias['generics'] if isinstance(g, dict)]

        positional_nodes: list[Any] = []
        named_nodes: list[dict] = []
        for argument in value.get('arguments', []):
            if not isinstance(argument, dict):
                continue
            argument_name = argument.get('name')
            if isinstance(argument_name, str):
                named_nodes.append(argument)
            else:
                positional_nodes.append(argument.get('value'))
        argument_types = [self._infer(argument) for argument in positional_nodes]
        named = bool(value.get('named'))

        if normalized == PROJECT:
            fields = list(BUILTIN_OBJECT_TYPES[PROJECT])
            if len(argument_types) > len(fields):
                self._error(
                    "Project received too many positional fields",
                    [f"expected at most {len(fields)}", f"fields: {', '.join(fields)}"],
                    where='project construction',
                )
            else:
                for index, argument_type in enumerate(argument_types):
                    expected = BUILTIN_OBJECT_TYPES[PROJECT][fields[index]]
                    if argument_type != ANY and not self._assignable(expected, argument_type):
                        self._assign_error('project construction', expected, argument_type)
            for named_node in named_nodes:
                field_name = named_node.get('name')
                if not isinstance(field_name, str):
                    continue
                if field_name not in fields:
                    self._error(
                        f"Project has no field named '{field_name}'",
                        [f"fields: {', '.join(fields)}"],
                        where='project construction',
                    )
                    continue
                value_node = named_node.get('value')
                if value_node is not None:
                    value_type = self._infer(value_node)
                    expected = BUILTIN_OBJECT_TYPES[PROJECT][field_name]
                    if value_type != ANY and not self._assignable(expected, value_type):
                        self._assign_error('project construction', expected, value_type)
            return PROJECT

        if normalized in NATIVE_TYPE_NAMES:
            if named or named_nodes:
                self._error(
                    "Native construction does not accept named arguments",
                    ["use positional arguments"],
                    where='native construction',
                )
            if normalized == NOVA:
                if argument_types:
                    self._error(
                        "nova construction takes no arguments",
                        [f"but {len(argument_types)} were given"],
                        where='native construction',
                    )
                return NOVA
            if normalized in (INTEGER, NUMBER, STRING, CHAR, BOOLEAN):
                if len(argument_types) != 1:
                    self._error(
                        f"{normalized} construction takes exactly one argument",
                        [f"but {len(argument_types)} were given"],
                        where='native construction',
                    )
                    return normalized
                return normalized
            if normalized == MAP:
                for argument_node in positional_nodes:
                    if not isinstance(argument_node, dict) or \
                            argument_node.get('type') != ParserTokenType.KEY_VALUE_PAIR:
                        self._error(
                            "map construction requires key >> value entries",
                            ["write each entry as key >> value"],
                            where='map construction',
                        )
                        break
                return MAP
            if normalized == SET:
                if type_parameters:
                    if len(type_parameters) != 1:
                        self._error(
                            "set construction expects exactly one element type",
                            [f"but {len(type_parameters)} were given"],
                            where='set construction',
                        )
                        return ANY
                    if not self._is_auto_type_node(type_parameters[0]):
                        element_type = self._annotation_type(type_parameters[0])
                        for argument_type in argument_types:
                            if argument_type == ANY:
                                continue
                            if not self._assignable(element_type, argument_type):
                                self._assign_error('set construction', element_type, argument_type)
                        return _set_of(element_type)
                return _set_of(_union_of_types(argument_types))
            if normalized == ARRAY:
                if type_parameters:
                    if len(type_parameters) != 1:
                        self._error(
                            "arr construction expects exactly one element type",
                            [f"but {len(type_parameters)} were given"],
                            where='array construction',
                        )
                        return ANY
                    if not self._is_auto_type_node(type_parameters[0]):
                        element_type = self._annotation_type(type_parameters[0])
                        for argument_type in argument_types:
                            if argument_type == ANY:
                                continue
                            if not self._assignable(element_type, argument_type):
                                self._assign_error('array construction', element_type, argument_type)
                        return _array_of(element_type)
                return _array_of(_union_of_types(argument_types))
            if normalized == 'tup':
                variadic = bool(type_reference.get('variadic'))
                if type_parameters:
                    if variadic:
                        if len(argument_types) < len(type_parameters):
                            self._error(
                                "tuple construction arity does not match its type",
                                [
                                    f"type declares at least {len(type_parameters)} elements",
                                    f"but {len(argument_types)} were given",
                                ],
                                where='tuple construction',
                            )
                            return ANY
                        element_parameters = (
                            type_parameters[:-1]
                            + [type_parameters[-1]] * (len(argument_types) - len(type_parameters) + 1)
                        )
                    else:
                        if len(type_parameters) != len(argument_types):
                            self._error(
                                "tuple construction arity does not match its type",
                                [
                                    f"type declares {len(type_parameters)} elements",
                                    f"but {len(argument_types)} were given",
                                ],
                                where='tuple construction',
                            )
                            return ANY
                        element_parameters = type_parameters
                    result: list[str] = []
                    for parameter, argument_type in zip(element_parameters, argument_types):
                        if self._is_auto_type_node(parameter):
                            result.append(argument_type)
                            continue
                        expected = self._annotation_type(parameter)
                        if argument_type != ANY and not self._assignable(expected, argument_type):
                            self._assign_error('tuple construction', expected, argument_type)
                        result.append(expected)
                    return 'tup[' + ', '.join(result) + ']'
                if not argument_types:
                    return 'tup'
                return 'tup[' + ', '.join(argument_types) + ']'
            return ANY
        object_name = name
        info = self._object_type_info(object_name)
        if info is None:
            return f'{OBJECT}:{object_name}'
        constructors: list[_Signature] = info.get('methods', {}).get('constructor', [])
        declared_parameters = info.get('type_parameters') or []
        if declared_parameters and type_parameters:
            replacements = {
                f'object:{parameter}': self._annotation_type(actual)
                for parameter, actual in zip(declared_parameters, type_parameters)
            }
            constructors = [
                self._substitute_signature(signature, replacements)
                for signature in constructors
            ]
        if not constructors:
            return f'{OBJECT}:{object_name}'

        if named or named_nodes:
            provided_types: dict[str, str] = {}
            seen_named_names: set[str] = set()
            for named_node in named_nodes:
                raw_name = named_node.get('name')
                parameter_name = raw_name if isinstance(raw_name, str) else self._identifier_name(raw_name)
                if parameter_name is None:
                    continue
                if parameter_name in seen_named_names:
                    self._error(
                        f"Constructor for '{object_name}' received '{parameter_name}' more than once",
                        ["pass each named argument once"],
                        where='instantiation',
                    )
                    continue
                seen_named_names.add(parameter_name)
                provided_types[parameter_name] = self._infer(named_node.get('value'))
            provided = set(provided_types)
            candidates = [
                candidate for candidate in constructors
                if provided.issubset(set(candidate.parameter_names))
                and all(
                    candidate.parameter_names[index] in provided
                    for index in range(min(candidate.min_argc, len(candidate.parameter_names)))
                )
            ]

            def candidate_matches(candidate: _Signature) -> bool:
                for index, parameter_name in enumerate(candidate.parameter_names):
                    if parameter_name in provided_types:
                        if not self._assignable(
                            candidate.parameter_types[index],
                            provided_types[parameter_name],
                            candidate.parameter_weak[index],
                        ):
                            return False
                    elif index < candidate.min_argc:
                        return False
                return True

            matching = [candidate for candidate in candidates if candidate_matches(candidate)]
            candidate = (
                matching[0] if matching
                else candidates[0] if candidates
                else constructors[0]
            )
            ordered: list[Optional[str]] = [None] * len(candidate.parameter_types)
            unknown_name_seen = False
            for parameter_name, named_type in provided_types.items():
                if parameter_name not in candidate.parameter_names:
                    unknown_name_seen = True
                    self._error(
                        f"Constructor for '{object_name}' has no parameter named '{parameter_name}'",
                        [f"parameters: {', '.join(candidate.parameter_names)}"],
                        where='instantiation',
                    )
                    continue
                index = candidate.parameter_names.index(parameter_name)
                if ordered[index] is not None:
                    self._error(
                        f"Constructor for '{object_name}' received '{parameter_name}' more than once",
                        ["pass each named argument once"],
                        where='instantiation',
                    )
                    continue
                ordered[index] = named_type
            for index, argument_type in enumerate(ordered):
                if argument_type is None:
                    if index < candidate.min_argc and not unknown_name_seen:
                        self._error(
                            f"Constructor for '{object_name}' is missing required argument '{candidate.parameter_names[index]}'",
                            [f"parameters: {', '.join(candidate.parameter_names)}"],
                            where='instantiation',
                        )
                    continue
                if not self._assignable(candidate.parameter_types[index], argument_type, candidate.parameter_weak[index]):
                    self._assign_error(
                        f'constructor: {object_name}',
                        candidate.parameter_types[index],
                        argument_type,
                    )
            return f'{OBJECT}:{object_name}'

        matches = [
            candidate for candidate in constructors
            if self._signature_matches(candidate, argument_types)
        ]
        if matches:
            return f'{OBJECT}:{object_name}'
        if len(constructors) == 1:
            candidate = constructors[0]
            if len(argument_types) < candidate.min_argc:
                for index in range(len(argument_types), candidate.min_argc):
                    self._error(
                        f"Constructor for '{object_name}' is missing required argument '{candidate.parameter_names[index]}'",
                        [f"parameters: {', '.join(candidate.parameter_names)}"],
                        where='instantiation',
                    )
            elif len(argument_types) > len(candidate.parameter_types):
                self._error(
                    f"Constructor for '{object_name}' received too many arguments",
                    [f"expected at most {len(candidate.parameter_types)}"],
                    where='instantiation',
                )
            else:
                for index, argument_type in enumerate(argument_types):
                    if self._assignable(
                        candidate.parameter_types[index],
                        argument_type,
                        candidate.parameter_weak[index],
                    ):
                        continue
                    self._assign_error(
                        f'constructor: {object_name}',
                        candidate.parameter_types[index],
                        argument_type,
                    )
            return f'{OBJECT}:{object_name}'
        self._error(
            f"No constructor of '{object_name}' accepts the given arguments",
            [
                f"argument types: {', '.join(argument_types)}",
                f"candidates: {len(constructors)}",
            ],
            where='instantiation',
        )
        return f'{OBJECT}:{object_name}'

    def _infer_array(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        elements = value.get('elements')
        if not isinstance(elements, list):
            return MAP if value.get('type') == MAP else ARRAY
        if value.get('type') == MAP:
            for element in elements:
                self._infer(element)
            return MAP
        element_types = [self._infer(element) for element in elements]
        if not element_types:
            return ARRAY
        return _array_of(_union_of_types(element_types))

    def _infer_block(self, statements: Any) -> str:
        if not isinstance(statements, list):
            return ANY
        self._scope_push()
        try:
            for statement in statements:
                self._infer(statement)
        finally:
            self._scope_pop()
        return ANY

    def _infer_unwrap(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        operand = value.get('expression')
        operand_type = self._infer(operand)

        if not self.in_function:
            self._error(
                "The postfix '?' operator is only valid inside a function",
                ["it propagates an error by returning from the current function"],
                where='unwrap operator',
            )
        elif not self.return_allows_error:
            self._error(
                "The postfix '?' operator requires an error-union return annotation",
                ["the enclosing function must end its return type with '?'"],
                where='unwrap operator',
            )

        if not isinstance(operand, dict) or operand.get('type') != ParserTokenType.CALL_EXPRESSION:
            self._error(
                "The operand of the postfix '?' operator must be a function call",
                ["write the call first, for example: value := find(id)?;"],
                where='unwrap operator',
            )
            return ANY

        return ANY if operand_type == ERROR else operand_type

    # ------------------------------------------------------------ declarations
    def _infer_declaration_undefined(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        type_node = value.get('type')
        declared_type = self._annotation_type(type_node)
        self._bind(name or '', declared_type, True, self._annotation_weak(type_node))
        return declared_type

    def _expression_is_async_function_value(self, expression: Any) -> bool:
        if not isinstance(expression, dict):
            return False
        if expression.get('type') == ParserTokenType.FUN_EXPRESSION:
            expression_value = expression.get('value')
            return isinstance(expression_value, dict) and bool(
                expression_value.get('is_async')
            )
        if expression.get('type') == LexerTokenType.IDENTIFIER:
            name = self._identifier_name(expression)
            if name is None:
                return False
            variable = self._lookup(name)
            if variable is not None:
                return bool(getattr(variable, 'async_value', False))
            signatures = self.functions.get(name)
            if signatures:
                return any(signature.is_async for signature in signatures)
        return False

    def _infer_declaration_typed(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        type_node = value.get('type')
        declared_type = self._annotation_type(type_node)
        weak = self._annotation_weak(type_node)
        expression = value.get('expression')
        source_type = self._infer(expression)
        async_value = self._expression_is_async_function_value(expression)
        if isinstance(source_type, str) and source_type.startswith('&'):
            self._error(
                'references cannot be stored',
                [
                    'a reference only lives for the duration of one call',
                    'use &variable directly as a &parameter argument',
                ],
                where='variable declaration',
            )
        if not self._assignable(declared_type, source_type, weak):
            self._assign_error(
                f'variable declaration: {name}' if name else 'variable declaration',
                declared_type,
                source_type,
            )
        self._bind(name or '', declared_type, True, weak, async_value)
        return declared_type

    def _infer_declaration_interpret(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        expression = value.get('expression')
        source_type = self._infer(expression)
        async_value = self._expression_is_async_function_value(expression)
        if isinstance(source_type, str) and source_type.startswith('&'):
            self._error(
                'references cannot be stored',
                [
                    'a reference only lives for the duration of one call',
                    'use &variable directly as a &parameter argument',
                ],
                where='variable declaration',
            )
        inferred_type = source_type if source_type else ANY
        self._bind(name or '', inferred_type, False, False, async_value)
        return inferred_type

    def _infer_destructure_declaration(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        pattern = value.get('pattern')
        if not isinstance(pattern, dict):
            return ANY
        pattern_value = pattern.get('value')
        if not isinstance(pattern_value, dict):
            pattern_value = pattern
        entries = pattern_value.get('entries')
        if not isinstance(entries, list):
            entries = []
        group_type_node = pattern_value.get('group_type')
        group_reference = bool(pattern_value.get('group_reference'))
        source_type = self._infer(value.get('expression'))

        array_element = _array_element_type(source_type) if _is_array_type(source_type) else ANY
        object_props: Optional[dict] = None
        if isinstance(source_type, str) and source_type.startswith(f'{OBJECT}:'):
            object_name = source_type.split(':', 1)[1]
            info = self._object_type_info(object_name)
            if info is not None:
                object_props = info.get('props', {})

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = self._identifier_name(entry.get('identifier'))
            if name is None:
                continue
            type_node = entry.get('type')
            reference = bool(entry.get('reference')) or group_reference
            explicit = True
            if type_node is not None:
                entry_type = self._annotation_type(type_node)
            elif group_type_node is not None:
                entry_type = self._annotation_type(group_type_node)
            elif object_props is not None:
                entry_type = object_props.get(name, ANY)
                explicit = False
            else:
                entry_type = array_element
                explicit = False
            if entry_type == MIXED:
                entry_type = ANY

            if explicit and not reference:
                source_entry_type = object_props.get(name, ANY) if object_props is not None else array_element
                if source_entry_type == MIXED:
                    source_entry_type = ANY
                if source_entry_type != ANY and entry_type != ANY and \
                        not self._assignable(entry_type, source_entry_type):
                    self._assign_error(f'destructuring: {name}', entry_type, source_entry_type)

            self._bind(name, entry_type, explicit or reference, False)
        return source_type

    def _infer_assignment(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        target = value.get('target')
        source_type = self._infer(value.get('expression'))
        if isinstance(source_type, str) and source_type.startswith('&'):
            self._error(
                'references cannot be stored',
                [
                    'a reference only lives for the duration of one call',
                    'use &variable directly as a &parameter argument',
                ],
                where='assignment',
            )
        if not isinstance(target, dict):
            return source_type

        target_type = target.get('type')
        if target_type == LexerTokenType.IDENTIFIER:
            name = self._identifier_name(target)
            variable = self._lookup(name) if name is not None else None
            if variable is not None:
                variable.async_value = self._expression_is_async_function_value(
                    value.get('expression')
                )
            if variable is not None and variable.annotated:
                if not self._assignable(variable.type, source_type, variable.weak):
                    self._assign_error(
                        f'assignment to: {name}',
                        variable.type,
                        source_type,
                    )
        elif target_type == ParserTokenType.ACCESS_EXPRESSION:
            declared_type = self._infer_access(target.get('value'))
            if declared_type not in (ANY, NOVA, ERROR):
                if not self._assignable(declared_type, source_type):
                    self._assign_error('property assignment', declared_type, source_type)
        elif target_type == ParserTokenType.INDEX_EXPRESSION:
            declared_type = self._infer_index(target.get('value'))
            if declared_type not in (ANY, NOVA, ERROR, MIXED):
                if not self._assignable(declared_type, source_type):
                    self._assign_error('index assignment', declared_type, source_type)
        else:
            self._infer(target)
        return source_type

    def _infer_return(self, expression: Any) -> str:
        source_type = self._infer(expression)
        if not self.in_function or self.return_type is None:
            # Top-level return is a runtime concern; the checker skips it.
            return source_type
        if source_type == ANY:
            return source_type
        if self.return_allows_error and source_type == ERROR:
            return source_type
        if not self._assignable(self.return_type, source_type, self.return_weak):
            self._assign_error('function return', self.return_type, source_type)
        return source_type

    # -------------------------------------------------------------- statements
    def _infer_if(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        self._scope_push()
        try:
            self._infer(value.get('expression'))
            self._infer(value.get('block'))
        finally:
            self._scope_pop()
        else_block = value.get('else')
        if else_block is not None:
            self._infer(else_block)
        return ANY

    def _tuple_element_types(self, type_name: str) -> tuple[list[str], bool]:
        if type_name == 'tup':
            return [], False
        try:
            from . import typespec as _ts
            spec = _ts.type_of_str(type_name)
            if spec.kind is _ts.Kind.NAMED and spec.name == 'tup':
                return [_ts.render(arg) for arg in spec.args], bool(spec.rest)
        except Exception:
            pass
        return [], False

    def _check_sequence_entries(
        self,
        entries: list,
        element_types: list[str],
        tuple_rest: bool,
        rest: Any,
    ) -> None:
        if element_types and not tuple_rest:
            if rest is None and len(entries) != len(element_types):
                self._error(
                    f"tuple pattern has {len(entries)} elements but the subject tuple has {len(element_types)}",
                    ['add or remove pattern elements, or use ...rest'],
                    where='match pattern',
                )
            elif rest is not None and len(entries) > len(element_types):
                self._error(
                    f"tuple pattern has {len(entries)} fixed elements but the subject tuple has {len(element_types)}",
                    ['remove pattern elements'],
                    where='match pattern',
                )
        for index, entry in enumerate(entries):
            if index < len(element_types):
                entry_type = element_types[index]
            elif tuple_rest and element_types:
                entry_type = element_types[-1]
            else:
                entry_type = ANY
            self._check_match_pattern(entry, entry_type)
        if isinstance(rest, dict) and isinstance(rest.get('name'), str):
            remaining = element_types[len(entries):]
            rest_type = 'tup[' + ', '.join(remaining) + ']' if remaining else 'tup'
            self._bind(rest['name'], rest_type, False, False)

    def _pattern_compatible(self, pattern: Any, type_name: str) -> bool:
        kind = pattern.get('kind') if isinstance(pattern, dict) else None
        if kind in {'wildcard', 'binding'}:
            return True
        if type_name in (ANY, MIXED):
            return True
        if kind == 'range':
            return type_name in (INTEGER, NUMBER)
        if kind == 'literal':
            literal_type = self._infer(pattern.get('value'))
            if literal_type in (ANY, MIXED):
                return True
            return self._assignable(type_name, literal_type)
        if kind == 'array':
            return type_name in (ARRAY, 'tup') or \
                _is_array_type(type_name) or _is_tuple_type(type_name)
        if kind == 'tuple':
            return type_name == 'tup' or _is_tuple_type(type_name)
        if kind == 'object':
            name = pattern.get('type_name')
            return type_name in (OBJ, OBJECT) or \
                type_name == f'{OBJECT}:{name}' or type_name == name
        return True

    def _check_match_pattern(self, pattern: Any, subject_type: str) -> None:
        if not isinstance(pattern, dict):
            return
        subject_unknown = subject_type in (ANY, MIXED)
        kind = pattern.get('kind')
        if kind not in {'wildcard', 'binding'}:
            branches = _split_union(subject_type)
            if len(branches) > 1:
                for branch in branches:
                    if self._pattern_compatible(pattern, branch):
                        self._check_match_pattern(pattern, branch)
                        return
        if kind == 'wildcard':
            return
        if kind == 'literal':
            literal_type = self._infer(pattern.get('value'))
            if not subject_unknown and literal_type not in (ANY, MIXED):
                if not self._assignable(subject_type, literal_type):
                    self._assign_error('match pattern', subject_type, literal_type)
            return
        if kind == 'binding':
            name = self._identifier_name(pattern.get('value'))
            type_node = pattern.get('type')
            if type_node is not None:
                bind_type = self._annotation_type(type_node)
                if not subject_unknown and not self._assignable(bind_type, subject_type):
                    self._assign_error('match pattern', bind_type, subject_type)
            else:
                bind_type = subject_type
            if bind_type == MIXED:
                bind_type = ANY
            self._bind(name or '', bind_type, type_node is not None, False)
            return
        if kind == 'range':
            start_type = self._infer(pattern.get('start'))
            end_type = self._infer(pattern.get('end'))
            for bound_type in (start_type, end_type):
                if bound_type in (ANY, MIXED):
                    continue
                if bound_type not in (INTEGER, NUMBER):
                    self._assign_error('match range', NUMBER, bound_type)
            if not subject_unknown and subject_type not in (INTEGER, NUMBER):
                self._assign_error('match range', NUMBER, subject_type)
            return
        if kind in {'array', 'tuple'}:
            entries = pattern.get('entries')
            entries = entries if isinstance(entries, list) else []
            rest = pattern.get('rest')
            if kind == 'array':
                if _is_array_type(subject_type) or subject_type == ARRAY:
                    element_type = _array_element_type(subject_type)
                    for entry in entries:
                        self._check_match_pattern(entry, element_type)
                    if isinstance(rest, dict) and isinstance(rest.get('name'), str):
                        self._bind(rest['name'], _array_of(element_type), False, False)
                    return
                if _is_tuple_type(subject_type):
                    element_types, tuple_rest = self._tuple_element_types(subject_type)
                    self._check_sequence_entries(entries, element_types, tuple_rest, rest)
                    return
                if not subject_unknown:
                    self._error(
                        f"array pattern cannot match subject type {subject_type}",
                        ['use an arr or tup subject'],
                        where='match pattern',
                    )
                for entry in entries:
                    self._check_match_pattern(entry, ANY)
                if isinstance(rest, dict) and isinstance(rest.get('name'), str):
                    self._bind(rest['name'], ARRAY, False, False)
                return
            if _is_tuple_type(subject_type):
                element_types, tuple_rest = self._tuple_element_types(subject_type)
                self._check_sequence_entries(entries, element_types, tuple_rest, rest)
                return
            if not subject_unknown:
                self._error(
                    f"tuple pattern cannot match subject type {subject_type}",
                    ['use a tup subject'],
                    where='match pattern',
                )
            for entry in entries:
                self._check_match_pattern(entry, ANY)
            if isinstance(rest, dict) and isinstance(rest.get('name'), str):
                self._bind(rest['name'], 'tup', False, False)
            return
        if kind == 'object':
            type_name = pattern.get('type_name')
            info = self._object_type_info(type_name)
            if info is None:
                self._error(
                    f"unknown object type '{type_name}' in match pattern",
                    ['declare the type before matching it'],
                    where='match pattern',
                )
                return
            object_type = f'{OBJECT}:{type_name}'
            if not subject_unknown and subject_type != OBJ and \
                    not self._assignable(object_type, subject_type):
                self._assign_error('match pattern', object_type, subject_type)
            props = info.get('props', {})
            entries = pattern.get('entries')
            entries = entries if isinstance(entries, list) else []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                field = entry.get('field')
                if field not in props:
                    self._error(
                        f"'{type_name}' has no property named '{field}'",
                        [f"properties: {', '.join(sorted(props.keys()))}"],
                        where='match pattern',
                    )
                    continue
                self._check_match_pattern(entry.get('pattern'), props[field])
            return
        self._error(
            f"unknown match pattern kind '{kind}'",
            ['use a literal, binding, array, tuple, object or range pattern'],
            where='match pattern',
        )

    @staticmethod
    def _pattern_literal_key(node: Any) -> Optional[tuple]:
        if not isinstance(node, dict):
            return None
        node_type = node.get('type')
        if node_type == LexerTokenType.BOOLEAN_LITERAL:
            return ('bool', 'true' if node.get('value') else 'false')
        if node_type == LexerTokenType.IDENTIFIER and node.get('value') in {'true', 'false'}:
            return ('bool', node.get('value'))
        if node_type == LexerTokenType.INTEGER_LITERAL:
            return ('int', node.get('value'))
        if node_type == LexerTokenType.FLOATING_LITERAL:
            return ('num', node.get('value'))
        if node_type == LexerTokenType.STRING_LITERAL:
            return ('str', node.get('value'))
        if node_type == LexerTokenType.NOVA_LITERAL:
            return ('nova',)
        if node_type == ParserTokenType.ACCESS_EXPRESSION:
            value = node.get('value')
            if isinstance(value, dict):
                target = value.get('target')
                prop = value.get('property')
                target_name = target.get('value') if isinstance(target, dict) else None
                prop_name = prop.get('value') if isinstance(prop, dict) else None
                if isinstance(target_name, str) and isinstance(prop_name, str):
                    return ('enum', target_name, prop_name)
        return None

    @staticmethod
    def _pattern_static_number(node: Any) -> Optional[float]:
        if not isinstance(node, dict):
            return None
        node_type = node.get('type')
        if node_type == LexerTokenType.INTEGER_LITERAL:
            return float(node.get('value'))
        if node_type == LexerTokenType.FLOATING_LITERAL:
            return float(node.get('value'))
        if node_type == ParserTokenType.UNARY_EXPRESSION:
            value = node.get('value')
            if isinstance(value, dict):
                operator = value.get('operator')
                operator_value = operator.get('value') if isinstance(operator, dict) else None
                number = _TypeChecker._pattern_static_number(value.get('right'))
                if number is None:
                    return None
                if operator_value == '-':
                    return -number
                if operator_value == '+':
                    return number
        return None

    @staticmethod
    def _match_range_bounds(pattern: Any) -> Optional[tuple[float, float]]:
        if not isinstance(pattern, dict):
            return None
        start = _TypeChecker._pattern_static_number(pattern.get('start'))
        end = _TypeChecker._pattern_static_number(pattern.get('end'))
        if start is None or end is None:
            return None
        return start, end

    def _match_case_is_catch_all(self, pattern: Any, subject_type: str) -> bool:
        if not isinstance(pattern, dict):
            return False
        kind = pattern.get('kind')
        if kind == 'wildcard':
            return True
        if kind == 'binding':
            type_node = pattern.get('type')
            if type_node is None:
                return True
            bind_type = self._annotation_type(type_node)
            return bind_type == ANY or subject_type not in (ANY, MIXED)
        return False

    def _warn_non_exhaustive(
        self,
        subject_type: str,
        covered_bool: set[str],
        covered_enum: set[tuple[str, str]],
        value: Any,
    ) -> None:
        line = value.get('line') if isinstance(value, dict) else None
        column = value.get('column') if isinstance(value, dict) else None
        if subject_type == BOOLEAN:
            missing = [name for name in ('true', 'false') if name not in covered_bool]
            if missing:
                get_state().warn(
                    'match on bool is not exhaustive; missing ' + ', '.join(missing),
                    line if isinstance(line, int) else None,
                    column if isinstance(column, int) else None,
                    code='PW215',
                )
            return
        name = subject_type
        if isinstance(name, str) and name.startswith(OBJECT + ':'):
            name = name[len(OBJECT) + 1:]
        info = self._object_type_info(name) if isinstance(name, str) else None
        if info is not None and info.get('is_enum'):
            variants = [v for v in info.get('variants', []) if isinstance(v, str)]
            covered = {
                variant for enum_name, variant in covered_enum
                if enum_name == name
            }
            missing = [variant for variant in variants if variant not in covered]
            if missing:
                get_state().warn(
                    f'match on {name} is not exhaustive; missing ' + ', '.join(missing),
                    line if isinstance(line, int) else None,
                    column if isinstance(column, int) else None,
                    code='PW215',
                )

    def _infer_match(self, value: Any, as_expression: bool = False) -> str:
        if not isinstance(value, dict):
            return ANY
        subject_type = self._infer(value.get('subject'))
        cases = value.get('cases')
        result_types: list[str] = []
        catch_all = False
        covered_bool: set[str] = set()
        covered_enum: set[tuple[str, str]] = set()
        covered_literals: set[tuple] = set()
        covered_ranges: list[tuple[float, float]] = []
        if isinstance(cases, list):
            for case in cases:
                if not isinstance(case, dict):
                    continue
                self._scope_push()
                try:
                    pattern = case.get('pattern')
                    unreachable_reason: Optional[str] = None
                    if catch_all:
                        unreachable_reason = 'an earlier case matches every value'
                    elif isinstance(pattern, dict):
                        kind = pattern.get('kind')
                        if kind == 'literal':
                            key = self._pattern_literal_key(pattern.get('value'))
                            if key is not None and key in covered_literals:
                                unreachable_reason = 'the same value is already covered'
                            number = self._pattern_static_number(pattern.get('value'))
                            if unreachable_reason is None and number is not None:
                                for lower, upper in covered_ranges:
                                    if lower <= number < upper:
                                        unreachable_reason = 'an earlier range covers this value'
                                        break
                        elif kind == 'range':
                            bounds = self._match_range_bounds(pattern)
                            if bounds is not None:
                                for lower, upper in covered_ranges:
                                    if lower <= bounds[0] and bounds[1] <= upper:
                                        unreachable_reason = 'an earlier range covers this range'
                                        break
                    if unreachable_reason is not None:
                        pattern_line = (
                            pattern.get('line')
                            if isinstance(pattern, dict)
                            else case.get('line')
                        )
                        pattern_column = (
                            pattern.get('column')
                            if isinstance(pattern, dict)
                            else case.get('column')
                        )
                        get_state().warn(
                            f'unreachable match case: {unreachable_reason}',
                            pattern_line if isinstance(pattern_line, int) else None,
                            pattern_column if isinstance(pattern_column, int) else None,
                            code='PW216',
                        )
                    self._check_match_pattern(pattern, subject_type)
                    guard = case.get('guard')
                    if guard is not None:
                        self._infer(guard)
                    if as_expression:
                        if case.get('is_expression'):
                            case_type = self._infer(case.get('value'))
                            if case_type not in (ANY, NOVA):
                                result_types.append(case_type)
                        else:
                            self._infer(case.get('block'))
                    else:
                        self._infer(case.get('block'))
                    if guard is None and isinstance(pattern, dict):
                        if self._match_case_is_catch_all(pattern, subject_type):
                            catch_all = True
                        kind = pattern.get('kind')
                        if kind == 'literal':
                            key = self._pattern_literal_key(pattern.get('value'))
                            if key is not None:
                                covered_literals.add(key)
                                if key[0] == 'bool':
                                    covered_bool.add(key[1])
                                elif key[0] == 'enum':
                                    covered_enum.add((key[1], key[2]))
                        elif kind == 'range':
                            bounds = self._match_range_bounds(pattern)
                            if bounds is not None:
                                covered_ranges.append(bounds)
                finally:
                    self._scope_pop()
        if not catch_all:
            self._warn_non_exhaustive(
                subject_type, covered_bool, covered_enum, value
            )
        if as_expression:
            return _union_of_types(result_types) if result_types else ANY
        return ANY


    def _infer_try(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        self._infer(value.get('block'))
        catches = value.get('catches')
        if isinstance(catches, list):
            for catch in catches:
                if not isinstance(catch, dict):
                    continue
                self._scope_push()
                try:
                    name = self._identifier_name(catch.get('name'))
                    if name is not None:
                        self._bind(name, ERROR, False)
                    self._infer(catch.get('block'))
                finally:
                    self._scope_pop()
        finally_block = value.get('finally_block')
        if finally_block is not None:
            self._infer(finally_block)
        return ANY

    def _push_loop_label(self, label: Optional[str]) -> None:
        if label is not None and label in self.loop_labels:
            self._error(
                f"loop label '{label}' is already in use",
                ["choose a different label"],
                where='loop',
            )
        self.loop_labels.append(label)
        self.loop_break_flags.append(False)

    def _pop_loop_label(self) -> None:
        self.loop_labels.pop()
        self.loop_break_flags.pop()

    def _check_loop_control(self, keyword: str, value: Any) -> None:
        if not self.loop_labels:
            self._error(
                f"'{keyword}' is only valid inside a loop",
                ["move it into a loop body"],
                where='loop control',
            )
            return
        label = value.get('label') if isinstance(value, dict) else None
        if label is not None and label not in self.loop_labels:
            self._error(
                f"unknown loop label '{label}'",
                ["the label must name an enclosing loop"],
                where='loop control',
            )
            return
        if keyword == 'break':
            if label is None:
                self.loop_break_flags[-1] = True
            else:
                index = len(self.loop_labels) - 1 - self.loop_labels[::-1].index(label)
                self.loop_break_flags[index] = True

    @staticmethod
    def _literal_bool(node: Any) -> Optional[bool]:
        if not isinstance(node, dict):
            return None
        if node.get('type') == LexerTokenType.IDENTIFIER and node.get('value') in {'true', 'false'}:
            return node.get('value') == 'true'
        return None

    def _infer_loop(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        self._push_loop_label(value.get('label'))
        try:
            condition = value.get('condition')
            if condition is not None:
                self._infer(condition)
            self._infer(value.get('block'))
            unconditional = condition is None or self._literal_bool(condition) is True
            if unconditional and not self.loop_break_flags[-1]:
                line = value.get('line')
                column = value.get('column')
                get_state().warn(
                    'loop has no break',
                    line if isinstance(line, int) else None,
                    column if isinstance(column, int) else None,
                    code='PW210',
                )
        finally:
            self._pop_loop_label()
        return ANY

    def _infer_for(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        self._scope_push()
        self._push_loop_label(value.get('label'))
        try:
            self._infer(value.get('start_expression'))
            middle = value.get('middle_expression')
            if middle is not None:
                self._infer(middle)
            last = value.get('last_expression')
            if last is not None:
                self._infer(last)
            self._infer(value.get('block'))
        finally:
            self._pop_loop_label()
            self._scope_pop()
        return ANY

    def _infer_for_each(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        self._scope_push()
        self._push_loop_label(value.get('label'))
        try:
            iterable_node = value.get('expression')
            iterable_type = self._infer(iterable_node)
            iterator = value.get('iterator')
            element_type = _array_element_type(iterable_type) if _is_array_type(iterable_type) else ANY
            if _is_set_type(iterable_type):
                element_type = _set_element_type(iterable_type)
            if iterable_type == STRING:
                element_type = CHAR
            literal_elements = self._literal_array_elements(iterable_node)

            if literal_elements is not None and isinstance(iterator, dict):
                self._check_for_each_elements(literal_elements, iterator)

            iterator_kind = iterator.get('type') if isinstance(iterator, dict) else None
            iterator_value = iterator.get('value') if isinstance(iterator, dict) else None
            if isinstance(iterator_value, dict):
                if iterator_kind == ParserTokenType.DECLARATION_UNDEFINED and iterator_value.get('inferred'):
                    ## Bare `for x >> values` takes the arr element type.
                    name = self._identifier_name(iterator_value.get('identifier'))
                    bind_type = element_type if element_type not in (ANY, MIXED) else ANY
                    self._bind(name or '', bind_type, False, False)
                else:
                    declared_type = self._annotation_type(iterator_value.get('type'))
                    if literal_elements is None and declared_type not in (ANY, NOVA) and element_type not in (ANY, MIXED):
                        weak = self._annotation_weak(iterator_value.get('type'))
                        if not self._assignable(declared_type, element_type, weak):
                            self._assign_error('for each iterator', declared_type, element_type)
                    self._infer(iterator)
            else:
                self._infer(iterator)

            if_expression = value.get('if_expression')
            if if_expression is not None:
                self._infer(if_expression)
            self._infer(value.get('block'))
        finally:
            self._pop_loop_label()
            self._scope_pop()
        return ANY

    def _literal_array_elements(self, node: Any) -> Optional[list]:
        if not isinstance(node, dict):
            return None
        if node.get('type') == ParserTokenType.ARRAY_EXPRESSION:
            elements = node.get('value', {}).get('elements') if isinstance(node.get('value'), dict) else None
            return elements if isinstance(elements, list) else None
        if node.get('type') == ParserTokenType.INSTANTIATION:
            value = node.get('value')
            if not isinstance(value, dict):
                return None
            type_reference = value.get('type_ref')
            if not isinstance(type_reference, dict) or type_reference.get('name') != ARRAY:
                return None
            arguments = value.get('arguments')
            if not isinstance(arguments, list):
                return None
            return [
                argument.get('value')
                for argument in arguments
                if isinstance(argument, dict) and argument.get('name') is None
            ]
        return None

    def _check_for_each_elements(self, elements: list, iterator: dict) -> None:
        iterator_type = iterator.get('type')
        if iterator_type not in {
            ParserTokenType.DECLARATION_UNDEFINED,
            ParserTokenType.DECLARATION_TYPED_VAR,
        }:
            return
        iterator_value = iterator.get('value')
        if not isinstance(iterator_value, dict):
            return
        type_node = iterator_value.get('type')
        declared_type = self._annotation_type(type_node)
        if declared_type == ANY:
            return
        weak = self._annotation_weak(type_node)
        for element in elements:
            element_type = self._infer(element)
            if element_type == ANY:
                continue
            if not self._assignable(declared_type, element_type, weak):
                self._assign_error('for each iterator', declared_type, element_type)
                return

    # ------------------------------------------------------------- user types
    def _infer_trait_declaration(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        if name is None:
            return ANY
        if name in OPERATOR_TRAIT_NAMES:
            self._error(
                f"trait '{name}' is reserved for operator overloading",
                ['choose a different trait name'],
                where='trait declaration',
            )
            return ANY
        if name in self.traits:
            self._error(
                f"trait '{name}' is already declared",
                ['choose a different trait name'],
                where='trait declaration',
            )
            return ANY
        trait = _TraitInfo(name)
        properties = value.get('properties')
        if isinstance(properties, list):
            for prop in properties:
                prop_value = prop.get('value') if isinstance(prop, dict) else None
                if not isinstance(prop_value, dict):
                    continue
                prop_name = self._identifier_name(prop_value.get('identifier'))
                if prop_name is None:
                    continue
                trait.properties[prop_name] = self._annotation_type(
                    prop_value.get('type')
                )
        method_nodes: list[tuple[Any, _Signature]] = []
        methods = value.get('methods')
        if isinstance(methods, list):
            for method in methods:
                if not isinstance(method, dict):
                    continue
                signature = self._make_signature(method)
                if signature is None:
                    continue
                trait.methods.setdefault(signature.name, []).append(signature)
                method_value = method.get('value')
                if not isinstance(method_value, dict):
                    continue
                if method_value.get('signature_only') or \
                        method_value.get('block') is None:
                    trait.required_methods.add(signature.name)
                else:
                    trait.default_methods.add(signature.name)
                    method_nodes.append((method, signature))
        self.traits[name] = trait
        synthetic_name = f'__trait_{name}'
        self.object_types[synthetic_name] = {
            'props': dict(trait.properties),
            'methods': {
                method_name: list(signatures)
                for method_name, signatures in trait.methods.items()
            },
            'static_methods': {},
            'type_parameters': [],
            'is_enum': False,
            'variants': [],
            'trait_name': name,
        }
        previous = self.in_trait_body
        try:
            for method, signature in method_nodes:
                self.in_trait_body = (name, signature.name)
                self._check_function_body(
                    method,
                    signature,
                    this_type=f'{OBJECT}:{synthetic_name}',
                )
        finally:
            self.in_trait_body = previous
        return f'{OBJECT}:{name}'

    def _infer_type_declaration(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        if name is None:
            return ANY
        if name in OPERATOR_TRAIT_NAMES:
            self._error(
                f"type name '{name}' is reserved for operator overloading",
                ['choose a different type name'],
                where='type declaration',
            )
            return ANY
        info = {
            'props': {},
            'methods': {},
            'static_methods': {},
            'trait_methods': {},
            'type_parameters': list(value.get('type_parameters') or []),
            'is_enum': bool(value.get('is_enum')),
            'variants': list(value.get('variants') or []),
        }
        self.object_types[name] = info
        previous_parameters = self.type_parameters
        self.type_parameters = set(value.get('type_parameters') or [])

        self._scope_push()
        try:
            properties = value.get('properties')
            if isinstance(properties, list):
                for entry in properties:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    _, prop = entry
                    if not isinstance(prop, dict):
                        continue
                    prop_value = prop.get('value')
                    if not isinstance(prop_value, dict):
                        continue
                    prop_name = self._identifier_name(prop_value.get('identifier'))
                    prop_type = self._annotation_type(prop_value.get('type'))
                    if prop_name is not None:
                        info['props'][prop_name] = prop_type
                    self._infer(prop)

            methods = value.get('methods')
            signatures: list[tuple[dict, _Signature, bool]] = []
            if isinstance(methods, list):
                for entry in methods:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    _, method = entry
                    if not isinstance(method, dict):
                        continue
                    if self._identifier_name(method.get('value', {}).get('identifier')) == 'constructor':
                        saved_parameters = self.type_parameters
                        self.type_parameters = set()
                        signature = self._make_signature(method)
                        self.type_parameters = saved_parameters
                    else:
                        signature = self._make_signature(method)
                    if signature is not None and signature.name:
                        qualifier = self._identifier_name(
                            method.get('value', {}).get('trait_qualifier')
                        )
                        if qualifier is not None:
                            trait = self.traits.get(qualifier)
                            if trait is None:
                                self._error(
                                    f"unknown trait '{qualifier}' in method declaration",
                                    ['declare the trait before implementing it'],
                                    where='trait-qualified method',
                                )
                                continue
                            required_signatures = trait.methods.get(signature.name)
                            if not required_signatures:
                                self._error(
                                    f"trait '{qualifier}' has no method named '{signature.name}'",
                                    [f"methods: {', '.join(sorted(trait.methods.keys()))}"],
                                    where='trait-qualified method',
                                )
                                continue
                            if not any(
                                self._method_signature_compatible(required, signature)
                                for required in required_signatures
                            ):
                                required = required_signatures[0]
                                self._error(
                                    f"method {name}.{qualifier}.{signature.name}() does not match the signature required by {qualifier}.{signature.name}()",
                                    [
                                        f"required: {required.function_type}",
                                        f"found: {signature.function_type}",
                                    ],
                                    where='trait-qualified method',
                                )
                                continue
                            info['trait_methods'].setdefault(
                                qualifier, {}
                            ).setdefault(signature.name, []).append(signature)
                            signatures.append((method, signature, True))
                            continue
                        is_instance = (
                            signature.name == 'constructor'
                            or bool(method.get('value', {}).get('instance_method'))
                        )
                        target = info['methods'] if is_instance else info['static_methods']
                        target.setdefault(signature.name, []).append(signature)
                        signatures.append((method, signature, is_instance))
            if isinstance(methods, list):
                for method, signature, is_instance in signatures:
                    self._check_function(
                        method,
                        this_type=f'{OBJECT}:{name}' if is_instance and signature.name != 'constructor' else None,
                        register=False,
                    )
        finally:
            self._scope_pop()
            self.type_parameters = previous_parameters
        return f'{OBJECT}:{name}'

    # --------------------------------------------------------------- functions
    def _signature_annotation_type(
        self,
        type_node: Any,
        type_parameters: list[str],
        default: str = ANY,
    ) -> str:
        inner = type_node.get('value') if isinstance(type_node, dict) else None
        if isinstance(inner, str) and inner in type_parameters:
            return inner
        if isinstance(inner, dict):
            name = inner.get('value')
            if isinstance(name, str) and name in type_parameters and \
                    not inner.get('generics'):
                return name
        return self._annotation_type(type_node, default)

    def _make_signature(self, function_node: Any) -> Optional[_Signature]:
        if not isinstance(function_node, dict):
            return None
        value = function_node.get('value')
        if not isinstance(value, dict):
            return None
        name = self._identifier_name(value.get('identifier'))
        if name is None:
            return None
        arguments = value.get('args')
        if not isinstance(arguments, list):
            arguments = []
        type_parameters = value.get('type_parameters')
        if not isinstance(type_parameters, list):
            type_parameters = []
        raw_constraints = value.get('type_parameter_constraints')
        type_parameter_constraints: dict[str, list[str]] = {}
        if isinstance(raw_constraints, dict):
            for parameter_name, trait_names in raw_constraints.items():
                if isinstance(parameter_name, str) and isinstance(trait_names, list):
                    type_parameter_constraints[parameter_name] = [
                        trait_name for trait_name in trait_names
                        if isinstance(trait_name, str)
                    ]
        variadic = bool(value.get('variadic'))
        variadic_index = value.get('variadic_index')
        if not isinstance(variadic_index, int):
            variadic_index = None

        parameter_names: list[str] = []
        parameter_types: list[str] = []
        parameter_weak: list[bool] = []
        for argument in arguments:
            if not isinstance(argument, dict):
                parameter_names.append('')
                parameter_types.append(ANY)
                parameter_weak.append(False)
                continue
            argument_value = argument.get('value')
            type_node = argument_value.get('type') if isinstance(argument_value, dict) else None
            parameter_name = self._identifier_name(argument_value.get('identifier')) if isinstance(argument_value, dict) else None
            parameter_names.append(parameter_name or '')
            parameter_types.append(
                self._signature_annotation_type(type_node, type_parameters)
            )
            parameter_weak.append(self._annotation_weak(type_node))

        min_argc = value.get('min_argc')
        if not isinstance(min_argc, int):
            min_argc = len(parameter_types)
        variadic_type = (
            parameter_types[variadic_index]
            if variadic and variadic_index is not None and 0 <= variadic_index < len(parameter_types)
            else None
        )

        return_node = value.get('return')
        if return_node is None:
            return_type = NOVA
            return_weak = False
            allows_error = False
        else:
            return_type = self._signature_annotation_type(
                return_node, type_parameters, NOVA
            )
            return_weak = self._annotation_weak(return_node)
            allows_error = self._annotation_error_union(return_node)

        rendered_params = list(parameter_types)
        if variadic and variadic_index is not None and 0 <= variadic_index < len(rendered_params):
            rendered_params[variadic_index] = rendered_params[variadic_index] + '...'
        function_type = 'fun[' + ', '.join(rendered_params + [return_type]) + ']'
        return _Signature(
            name,
            parameter_names,
            parameter_types,
            parameter_weak,
            min_argc,
            return_type,
            return_weak,
            allows_error,
            function_type,
            type_parameters,
            variadic,
            variadic_index,
            variadic_type,
            type_parameter_constraints,
            bool(value.get('is_async')),
        )

    def _check_function(self, function_node: Any, this_type: Optional[str] = None, register: bool = True) -> Optional[_Signature]:
        signature = self._make_signature(function_node)
        if signature is None:
            return None
        if register:
            self.functions.setdefault(signature.name, []).append(signature)
        self._check_function_body(function_node, signature, this_type)
        return signature

    def _check_function_body(self, function_node: Any, signature: _Signature, this_type: Optional[str]) -> None:
        value = function_node.get('value') if isinstance(function_node, dict) else None
        if not isinstance(value, dict):
            return

        for parameter_name, trait_names in signature.type_parameter_constraints.items():
            for trait_name in trait_names:
                if trait_name not in self.traits:
                    self._error(
                        f"unknown trait '{trait_name}' in constraint for '{parameter_name}'",
                        ['declare the trait before using it as a constraint'],
                        where='function declaration',
                    )

        previous = (
            self.return_type,
            self.return_weak,
            self.return_allows_error,
            self.in_function,
            self.this_type,
            self.loop_labels,
            self.loop_break_flags,
            self.current_type_parameters,
            self.current_type_parameter_constraints,
            self.in_async_function,
        )
        self.return_type = signature.return_type
        self.return_weak = signature.return_weak
        self.return_allows_error = signature.allows_error
        self.in_function = True
        self.this_type = this_type
        self.loop_labels = []
        self.loop_break_flags = []
        self.current_type_parameters = set(signature.type_parameters)
        self.current_type_parameter_constraints = dict(
            signature.type_parameter_constraints
        )
        self.in_async_function = signature.is_async

        self._scope_push()
        try:
            arguments = value.get('args')
            if isinstance(arguments, list):
                for index, argument in enumerate(arguments):
                    argument_value = argument.get('value') if isinstance(argument, dict) else None
                    type_node = argument_value.get('type') if isinstance(argument_value, dict) else None
                    if signature.variadic and signature.variadic_index == index:
                        name = self._identifier_name(argument_value.get('identifier'))
                        element_type = signature.parameter_types[index]
                        self._bind(
                            name or '',
                            _array_of(element_type),
                            True,
                            signature.parameter_weak[index],
                        )
                        continue
                    if self._annotation_reference(type_node):
                        ## Inside the body a reference parameter behaves like
                        ## the target variable's own type.
                        name = self._identifier_name(argument_value.get('identifier'))
                        bound_type = self._annotation_type(type_node)
                        if bound_type.startswith('&'):
                            bound_type = bound_type[1:]
                        self._bind(name or '', bound_type, True, False)
                    else:
                        name = self._identifier_name(
                            argument_value.get('identifier')
                        ) if isinstance(argument_value, dict) else None
                        bound_type = signature.parameter_types[index]
                        self._bind(
                            name or '',
                            bound_type,
                            True,
                            signature.parameter_weak[index],
                        )
                        expression = argument_value.get('expression') \
                            if isinstance(argument_value, dict) else None
                        if expression is not None:
                            expression_type = self._infer(expression)
                            if not self._assignable(
                                bound_type, expression_type
                            ):
                                self._assign_error(
                                    'default argument',
                                    bound_type,
                                    expression_type,
                                )
            block = value.get('block')
            if isinstance(block, dict) and block.get('value') is not None:
                self._infer(block)
        finally:
            self._scope_pop()
            (
                self.return_type,
                self.return_weak,
                self.return_allows_error,
                self.in_function,
                self.this_type,
                self.loop_labels,
                self.loop_break_flags,
                self.current_type_parameters,
                self.current_type_parameter_constraints,
                self.in_async_function,
            ) = previous

    # ---------------------------------------------------------------- modules
    def _infer_use(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        info = self._load_import(value)
        if info is None:
            return ANY
        if info.errors:
            details = []
            for error in info.errors[:3]:
                text = str(error).replace('\r', '').strip()
                if not text:
                    continue
                compact = " ".join(
                    part.strip()
                    for part in text.splitlines()
                    if part.strip()
                )
                details.append(compact[:500])
            self._error(
                f"module '{info.name}' has type errors",
                details,
                where='import',
            )
        if value.get('wildcard'):
            self._import_wildcard(info)
        else:
            alias = value.get('alias') or info.name
            self._bind_module_alias(alias, info)
        return ANY

    def _load_import(self, value: dict) -> Optional[_ModuleTypeInfo]:
        kind = value.get('kind', 'name')
        name = value.get('name', '')
        level = value.get('level', 0)
        if not isinstance(level, int):
            level = 0
        base_value = value.get('base')
        base = Path(base_value) if isinstance(base_value, str) and base_value else None
        try:
            loader = ModuleLoader(state=get_state())
            path = loader.resolve(kind, name, base, level)
        except Exception as error:
            self._error(
                f"cannot resolve module '{name}'",
                [str(error)],
                where='import',
            )
            return None
        return self._load_module_info(path)

    def _load_module_info(self, path: Path) -> Optional[_ModuleTypeInfo]:
        resolved = path.resolve()
        key = str(resolved)
        cached = self.module_cache.get(key)
        if cached is not None:
            if cached.loading:
                self._error(
                    f"cyclic module import involving '{cached.name}'",
                    ['modules cannot import each other in a cycle'],
                    where='import',
                )
            return cached
        if not resolved.exists():
            self._error(
                f"cannot find module '{resolved.stem}'",
                [f"looked for {resolved}"],
                where='import',
            )
            return None
        if resolved.is_dir():
            sources = sorted(resolved.glob('*.po'))
            module_name = resolved.name
        else:
            sources = [resolved]
            module_name = resolved.stem
        if not sources:
            self._error(
                f"module directory '{resolved}' is empty",
                ['add at least one .po file'],
                where='import',
            )
            return None

        info = _ModuleTypeInfo(module_name, resolved)
        info.loading = True
        self.module_cache[key] = info
        state = get_state()
        saved_alias = state.type_alias
        saved_user_types = state.user_types
        state.type_alias = {}
        state.user_types = set()
        try:
            program_ast: list[Any] = []
            for source in sources:
                try:
                    content = source.read_text(encoding='utf-8')
                except OSError as error:
                    info.errors.append(powang_error_format(
                        'MODULE', f'module: {source}',
                        'cannot read module file', [str(error)],
                    ))
                    continue
                try:
                    parser = Parser(content, source_path=source)
                    program_ast.extend(parser.parse())
                except PowangError as error:
                    info.errors.append(error)
                except Exception as error:
                    info.errors.append(powang_error_format(
                        'MODULE', f'module: {source}',
                        'module parse failed', [str(error)],
                    ))
            if program_ast:
                child = _TypeChecker(
                    str(sources[0]),
                    module_cache=self.module_cache,
                )
                child.run(program_ast)
                info.errors.extend(child.errors)
                info.all_object_types = dict(child.object_types)
                info.all_traits = dict(child.traits)
                self._collect_module_exports(info, child, program_ast)
        finally:
            state.type_alias = saved_alias
            state.user_types = saved_user_types
            info.loading = False
        return info

    @staticmethod
    def _exported_statement_name(statement: dict) -> Optional[str]:
        statement_type = statement.get('type')
        value = statement.get('value')
        if not isinstance(value, dict):
            return None
        if statement_type in {
            ParserTokenType.DECLARATION_FUN,
            ParserTokenType.TYPE_DECLARATION,
            ParserTokenType.TRAIT_DECLARATION,
            ParserTokenType.DECLARATION_UNDEFINED,
            ParserTokenType.DECLARATION_TYPED_VAR,
            ParserTokenType.DECLARATION_INTERPRET,
            ParserTokenType.CONST_DECLARATION,
        }:
            identifier = value.get('identifier')
            if isinstance(identifier, dict):
                return identifier.get('value')
        if statement_type == ParserTokenType.EXTERN_REFERENCE:
            powang = value.get('powang')
            if isinstance(powang, dict):
                powang_value = powang.get('value')
                if isinstance(powang_value, dict):
                    identifier = powang_value.get('identifier')
                    if isinstance(identifier, dict):
                        return identifier.get('value')
        return None

    @staticmethod
    def _exported_statement_kind(statement: dict) -> str:
        statement_type = statement.get('type')
        if statement_type in {
            ParserTokenType.DECLARATION_FUN,
            ParserTokenType.EXTERN_REFERENCE,
        }:
            return 'function'
        if statement_type == ParserTokenType.TYPE_DECLARATION:
            return 'type'
        if statement_type == ParserTokenType.TRAIT_DECLARATION:
            return 'trait'
        return 'variable'

    def _collect_module_exports(
        self,
        info: _ModuleTypeInfo,
        child: '_TypeChecker',
        program_ast: list[Any],
    ) -> None:
        exported: dict[str, str] = {}
        has_exports = False
        for statement in program_ast:
            if not isinstance(statement, dict) or not statement.get('exported'):
                continue
            has_exports = True
            name = self._exported_statement_name(statement)
            if name is None:
                continue
            exported[name] = self._exported_statement_kind(statement)
        if not has_exports:
            info.legacy = True
            for name in child.functions:
                exported.setdefault(name, 'function')
            for name in child.object_types:
                if name == PROJECT:
                    continue
                exported.setdefault(name, 'type')
            for name in child.traits:
                exported.setdefault(name, 'trait')
            for name, variable in child.scopes[0].items():
                if name == 'project':
                    continue
                if isinstance(variable.type, str) and \
                        variable.type.startswith('module:'):
                    continue
                exported.setdefault(name, 'variable')
        info.exports = exported
        for name, kind in exported.items():
            if kind == 'function':
                info.functions[name] = list(child.functions.get(name, []))
            elif kind == 'type':
                type_info = child.object_types.get(name)
                if type_info is not None:
                    info.object_types[name] = type_info
            elif kind == 'trait':
                trait_info = child.traits.get(name)
                if trait_info is not None:
                    info.traits[name] = trait_info
            elif kind == 'variable':
                variable = child.scopes[0].get(name)
                if variable is not None:
                    info.variables[name] = variable.type

    def _import_wildcard(self, info: _ModuleTypeInfo) -> None:
        for name, signatures in info.functions.items():
            if name in self.functions:
                self._error(
                    f"wildcard import collides with function '{name}'",
                    [f"module '{info.name}' exports '{name}'"],
                    where='import',
                )
                continue
            self.functions[name] = list(signatures)
        for name, type_info in info.object_types.items():
            if name in self.object_types:
                self._error(
                    f"wildcard import collides with type '{name}'",
                    [f"module '{info.name}' exports '{name}'"],
                    where='import',
                )
                continue
            self.object_types[name] = copy.deepcopy(type_info)
        for name, trait_info in info.traits.items():
            if name in self.traits:
                self._error(
                    f"wildcard import collides with trait '{name}'",
                    [f"module '{info.name}' exports '{name}'"],
                    where='import',
                )
                continue
            self.traits[name] = copy.deepcopy(trait_info)
        for name, type_name in info.variables.items():
            if name in self.scopes[-1]:
                self._error(
                    f"wildcard import collides with variable '{name}'",
                    [f"module '{info.name}' exports '{name}'"],
                    where='import',
                )
                continue
            self.scopes[-1][name] = _VariableInfo(
                self._qualify_type_text(type_name, info, info.name),
                True,
                False,
            )

    def _bind_module_alias(self, alias: str, info: _ModuleTypeInfo) -> None:
        if alias in self.scopes[-1]:
            self._error(
                f"module alias '{alias}' is already declared",
                ['choose a different alias'],
                where='import',
            )
            return
        self.scopes[-1][alias] = _VariableInfo(f'module:{alias}', True, False)
        self.module_values[alias] = info
        self.imported_modules[alias] = info
        for name, type_info in info.object_types.items():
            qualified = f'{alias}.{name}'
            self.object_types[qualified] = copy.deepcopy(type_info)
            self.type_owners[qualified] = (info, name)
        for name, trait_info in info.traits.items():
            qualified = f'{alias}.{name}'
            self.traits[qualified] = copy.deepcopy(trait_info)

    @staticmethod
    def _qualify_type_text(
        text: str,
        info: _ModuleTypeInfo,
        alias: str,
    ) -> str:
        if not isinstance(text, str):
            return text
        for name, kind in info.exports.items():
            if kind in {'type', 'trait'}:
                text = re.sub(
                    rf'\bobject:{re.escape(name)}\b',
                    f'object:{alias}.{name}',
                    text,
                )
        return text

    def _qualify_signature(
        self,
        signature: _Signature,
        info: _ModuleTypeInfo,
        alias: str,
    ) -> _Signature:
        constraints: dict[str, list[str]] = {}
        for parameter_name, trait_names in signature.type_parameter_constraints.items():
            constraints[parameter_name] = [
                f'{alias}.{trait_name}' if trait_name in info.traits else trait_name
                for trait_name in trait_names
            ]
        return _Signature(
            signature.name,
            list(signature.parameter_names),
            [
                self._qualify_type_text(type_text, info, alias)
                for type_text in signature.parameter_types
            ],
            list(signature.parameter_weak),
            signature.min_argc,
            self._qualify_type_text(signature.return_type, info, alias),
            signature.return_weak,
            signature.allows_error,
            self._qualify_type_text(signature.function_type or '', info, alias),
            list(signature.type_parameters),
            signature.variadic,
            signature.variadic_index,
            self._qualify_type_text(signature.variadic_type, info, alias)
            if signature.variadic_type is not None else None,
            constraints,
            signature.is_async,
        )

    def _module_callee(
        self,
        callee: Any,
    ) -> Optional[tuple[_ModuleTypeInfo, str, str]]:
        if not isinstance(callee, dict) or \
                callee.get('type') != ParserTokenType.ACCESS_EXPRESSION:
            return None
        access = callee.get('value')
        if not isinstance(access, dict):
            return None
        alias = self._identifier_name(access.get('target'))
        member_name = self._identifier_name(access.get('property'))
        if alias is None or member_name is None:
            return None
        info = self.module_values.get(alias)
        if info is None:
            return None
        return info, member_name, f'{alias}.{member_name}'

    def _object_type_info(self, object_name: str) -> Optional[dict]:
        info = self.object_types.get(object_name)
        if info is not None:
            return info
        owner = self.type_owners.get(object_name)
        if owner is not None:
            module_info, original_name = owner
            return module_info.all_object_types.get(original_name)
        return None

    # ----------------------------------------------------------------- extern
    def _infer_extern(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        powang = value.get('powang')
        if isinstance(powang, dict):
            powang_type = powang.get('type')
            if powang_type == ParserTokenType.DECLARATION_FUN:
                self._check_function(powang, register=True)
            elif powang_type == ParserTokenType.TYPE_DECLARATION:
                self._infer_type_declaration(powang.get('value'))
        return ANY


def type_check(program_ast: Any, path: Optional[str] = None) -> list[PowangError]:
    """Check a parsed program AST and return the list of type errors."""
    return _TypeChecker(path).run(program_ast)


def check_source(source: str, path: Optional[str] = None) -> list[PowangError]:
    """Parse and type-check a source string."""
    ## `use` resolution reads these globals. The CLI sets them before calling
    ## here; direct callers get sane defaults instead of a KeyError.
    if 'ABSOLUTE' not in PATHS:
        PATHS['ABSOLUTE'] = Path(path).resolve() if path is not None else Path.cwd() / 'powang.py'
    if path is not None:
        PATHS['RELATIVE'] = Path(path).resolve()
    elif 'RELATIVE' not in PATHS:
        PATHS['RELATIVE'] = PATHS['ABSOLUTE']
    program_ast = Parser(source, source_path=path).parse()
    program_ast = simplify_program(program_ast, get_state().warn)
    return type_check(program_ast, path)
