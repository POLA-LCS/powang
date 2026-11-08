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

from pathlib import Path
from typing import Any, Optional

from .parser import Parser, NATI_TYPES, PATHS
from .simplify import simplify_program
from .state import get_state
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
    PowangTask,
)
from .error import (
    PowangError,
    powang_error_format,
    powang_error_type_match,
)
from .lexer.token import LexerTokenType, ParserTokenType
from .builtins.native_methods import NATIVE_METHOD_TYPES, NATIVE_METHOD_NAMES
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
ARRAY = PowangArray.type
MAP = PowangMap.type
SET = PowangSet.type
FUNCTION = PowangFunction.type
ERROR = PowangErrorValue.type
OBJECT = PowangObjectType.type
FILE = PowangFileStream.type
TASK = PowangTask.type

## `function` and `file` are runtime types but are absent from the parser's
## NATI_TYPES set, so they need explicit handling here.
NATIVE_TYPE_NAMES = set(NATI_TYPES) | {FUNCTION, FILE, HANDLE}

ARRAY_OPEN = f'{ARRAY}['
ARRAY_CLOSE = ']'
MIXED = 'mixed'


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
}


class _VariableInfo:
    __slots__ = ('type', 'annotated', 'weak')

    def __init__(self, type_name: str, annotated: bool, weak: bool = False):
        self.type = type_name
        self.annotated = annotated
        self.weak = weak


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
    ):
        self.name = name
        self.parameter_names = parameter_names
        self.parameter_types = parameter_types
        self.parameter_weak = parameter_weak
        self.min_argc = min_argc
        self.return_type = return_type
        self.return_weak = return_weak
        self.allows_error = allows_error


class _TypeChecker:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        ## Aliases belong to the run being checked, which is the active state
        ## at type_check time. A previous run's aliases are never visible.
        self.type_alias: dict[str, Any] = get_state().type_alias
        self.errors: list[PowangError] = []
        self.functions: dict[str, list[_Signature]] = {}
        self.object_types: dict[str, dict[str, Any]] = {}
        self.scopes: list[dict[str, _VariableInfo]] = [{}]

        # Current function context. ``None`` means top level.
        self.return_type: Optional[str] = None
        self.return_weak: bool = False
        self.return_allows_error: bool = False
        self.in_function: bool = False
        self.this_type: Optional[str] = None
        self.type_parameters: set[str] = set()
        self.loop_labels: list[Optional[str]] = []
        self.loop_break_flags: list[bool] = []
        self._position: Optional[tuple[int, int]] = None

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

    def _bind(self, name: str, type_name: str, annotated: bool, weak: bool = False):
        if not name:
            return
        if name in self.scopes[-1]:
            self._error(
                f"variable '{name}' is already declared in this scope",
                ["choose a different name or assign to the existing variable with '='"],
                where='variable declaration',
            )
        self.scopes[-1][name] = _VariableInfo(type_name, annotated, weak)

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

    def _assignable(self, target: str, source: str, target_weak: bool = False) -> bool:
        if target == ANY or source == ANY:
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
        if source == NOVA:
            # Only weak declarations accept nova.
            return target_weak
        if target == NOVA:
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
        if target == STRING and source == ERROR:
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
                'props': {
                    'modules': 'arr[str]',
                    'paths': 'arr[str]',
                    'logLevel': 'str',
                    'allowSystem': 'bool',
                },
                'methods': {},
            }
        if getattr(get_state(), 'project_value', None) is not None and not self._has_project_declaration(program_ast):
            self.scopes[0]['project'] = _VariableInfo(f'{OBJECT}:Project', True, False)
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
            for key in ('identifier', 'callee', 'target', 'type', 'expression', 'property'):
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
        if node_type == ParserTokenType.INDEX_EXPRESSION:
            return self._infer_index(value)
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

        if node_type == ParserTokenType.MATCH_STATEMENT:
            return self._infer_match(value)
        if node_type == ParserTokenType.MATCH_EXPRESSION:
            self._infer(value.get('subject'))
            result_type = ANY
            for case in value.get('cases', []) if isinstance(value.get('cases'), list) else []:
                if not isinstance(case, dict):
                    continue
                pattern = case.get('pattern')
                if isinstance(pattern, dict) and pattern.get('kind') == 'binding':
                    name = self._identifier_name(pattern.get('value'))
                    if name is not None:
                        self._scope_push()
                        try:
                            self._bind(name, ANY, False)
                            guard = case.get('guard')
                            if guard is not None:
                                self._infer(guard)
                            if case.get('is_expression'):
                                case_type = self._infer(case.get('value'))
                                if result_type == ANY:
                                    result_type = case_type
                        finally:
                            self._scope_pop()
                else:
                    guard = case.get('guard')
                    if guard is not None:
                        self._infer(guard)
                    if case.get('is_expression'):
                        case_type = self._infer(case.get('value'))
                        if result_type == ANY:
                            result_type = case_type
            return result_type
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
        if node_type == ParserTokenType.TYPE_DECLARATION:
            return self._infer_type_declaration(value)
        if node_type == ParserTokenType.EXTERN_REFERENCE:
            return self._infer_extern(value)

        if node_type == ParserTokenType.MODULE_DECLARATION:
            return ANY

    # ------------------------------------------------------------ expressions
    def _infer_reference(self, value: Any) -> str:
        """Type of `&name`: a reference to the target variable's type."""
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('target'))
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
            return f'{OBJECT}:Project'
        variable = self._lookup(name)
        if variable is not None:
            return variable.type
        if name in self.functions:
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
        if operator_name == '!':
            return BOOLEAN
        if operator_name == '-':
            return right_type if right_type in NUMERIC_TYPES else ANY
        if operator_name == '[-]':
            return right_type if right_type in {INTEGER, NUMBER, STRING, ARRAY} else ANY
        if operator_name == '+':
            return right_type
        return ANY

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
            if named_nodes:
                if len(candidates) != 1:
                    self._error(
                        f"Named arguments for '{callee_name}' require a single overload",
                        [f"found {len(candidates)} overloads"],
                        where=f'function call: {callee_name}',
                    )
                    return candidates[0].return_type if candidates else ANY
                candidate = candidates[0]
                ordered_types: list[Optional[str]] = [None] * len(candidate.parameter_types)
                for index, argument_type in enumerate(argument_types):
                    if index >= len(ordered_types):
                        self._error(
                            f"Function '{callee_name}' received too many arguments",
                            [f"expected at most {len(ordered_types)}"],
                            where=f'function call: {callee_name}',
                        )
                        break
                    ordered_types[index] = argument_type
                for named in named_nodes:
                    named_value = named.get('value')
                    if not isinstance(named_value, dict):
                        continue
                    name = self._identifier_name(named_value.get('name'))
                    if name is None:
                        continue
                    if name not in candidate.parameter_names:
                        self._error(
                            f"Function '{callee_name}' has no parameter named '{name}'",
                            [f"parameters: {', '.join(candidate.parameter_names)}"],
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
                return candidate.return_type

            matches = [
                candidate for candidate in candidates
                if self._signature_matches(candidate, argument_types)
            ]
            if matches:
                return matches[0].return_type
            self._error(
                f"No overload of '{callee_name}' accepts the given arguments",
                [
                    f"argument types: {', '.join(argument_types)}",
                    f"candidates: {len(candidates)}",
                ],
                where=f'function call: {callee_name}',
            )
            return candidates[0].return_type if candidates else ANY

        # A function value stored in a variable has no statically known
        # signature. Unknown callees are skipped, never rejected.
        return ANY

    def _infer_spawn(self, value: Any) -> str:
        ## The enclosed call is still checked (arity, known signatures), but
        ## the expression's static type is always the opaque `task` handle.
        if isinstance(value, dict):
            self._infer(value.get('call'))
        return TASK

    def _signature_matches(self, signature: _Signature, argument_types: list[str]) -> bool:
        if len(argument_types) > len(signature.parameter_types):
            return False
        if len(argument_types) < signature.min_argc:
            return False
        for index, argument_type in enumerate(argument_types):
            parameter_type = signature.parameter_types[index]
            parameter_weak = signature.parameter_weak[index]
            if parameter_type == ANY or argument_type == ANY:
                continue
            if not self._assignable(parameter_type, argument_type, parameter_weak):
                return False
        return True

    def _infer_method_call(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        owner_node = value.get('owner')
        owner_name = self._identifier_name(owner_node)
        method_name = self._identifier_name(value.get('method'))
        arguments = value.get('arguments')
        argument_nodes = arguments if isinstance(arguments, list) else []
        argument_types = [self._infer(argument) for argument in argument_nodes]
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
        if owner_name is not None and owner_name in self.object_types:
            static_info = self.object_types[owner_name]
            static_methods = static_info.get('static_methods', {}).get(method_name)
            if static_methods:
                has_named = any(
                    isinstance(node, dict) and isinstance(node.get('name'), str)
                    for node in argument_nodes
                )
                if has_named:
                    return static_methods[0].return_type
                matches = [signature for signature in static_methods if self._signature_matches(signature, argument_types)]
                return matches[0].return_type if matches else static_methods[0].return_type
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
            info = self.object_types.get(object_name)
            if info is not None:
                methods = info.get('methods', {}).get(method_name)
                if methods:
                    return methods[0].return_type
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
            if method_name in {'add', 'sub', 'mul', 'reverse', 'get'}:
                return mutating_return() if is_reference else STRING
            if method_name == 'div':
                return _array_of(STRING)
            if method_name in {'count', 'size'}:
                return INTEGER
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
            return STRING
        if _is_array_type(target_type):
            return _array_element_type(target_type)
        # Map values have no statically known element type in this slice.
        return ANY

    def _infer_access(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        target_type = self._infer(value.get('target'))
        property_name = self._identifier_name(value.get('property'))
        if property_name is None:
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
            info = self.object_types.get(object_name)
            if info is not None:
                props = info.get('props', {})
                if property_name in props:
                    return props[property_name]
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

        if normalized == f'{OBJECT}:Project':
            for named_node in named_nodes:
                field_name = named_node.get('name')
                if isinstance(field_name, str) and field_name not in {
                    "modules", "paths", "logLevel", "allowSystem"
                }:
                    self._error(
                        f"Project has no field named '{field_name}'",
                        ["fields: modules, paths, logLevel, allowSystem"],
                        where='project construction',
                    )
            return f'{OBJECT}:Project'

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
            if normalized in (INTEGER, NUMBER, STRING, BOOLEAN):
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
        info = self.object_types.get(object_name)
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

    def _infer_declaration_typed(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        type_node = value.get('type')
        declared_type = self._annotation_type(type_node)
        weak = self._annotation_weak(type_node)
        source_type = self._infer(value.get('expression'))
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
        self._bind(name or '', declared_type, True, weak)
        return declared_type

    def _infer_declaration_interpret(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        source_type = self._infer(value.get('expression'))
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
        self._bind(name or '', inferred_type, False, False)
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
            info = self.object_types.get(object_name)
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

    def _infer_match(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        subject_type = self._infer(value.get('subject'))
        cases = value.get('cases')
        if isinstance(cases, list):
            for case in cases:
                if not isinstance(case, dict):
                    continue
                self._scope_push()
                try:
                    pattern = case.get('pattern')
                    if isinstance(pattern, dict):
                        kind = pattern.get('kind')
                        if kind == 'binding':
                            name = self._identifier_name(pattern.get('value'))
                            type_node = pattern.get('type')
                            bind_type = self._annotation_type(type_node) if type_node is not None else subject_type
                            if type_node is not None and subject_type != ANY:
                                if not self._assignable(bind_type, subject_type):
                                    self._assign_error('match pattern', bind_type, subject_type)
                            if bind_type == MIXED:
                                bind_type = ANY
                            self._bind(name or '', bind_type, type_node is not None, False)
                        elif kind == 'literal':
                            self._infer(pattern.get('value'))
                    guard = case.get('guard')
                    if guard is not None:
                        self._infer(guard)
                    self._infer(case.get('block'))
                finally:
                    self._scope_pop()
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
    def _infer_type_declaration(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ANY
        name = self._identifier_name(value.get('identifier'))
        if name is None:
            return ANY
        info = {
            'props': {},
            'methods': {},
            'static_methods': {},
            'type_parameters': list(value.get('type_parameters') or []),
            'is_enum': bool(value.get('is_enum')),
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
            parameter_types.append(self._annotation_type(type_node))
            parameter_weak.append(self._annotation_weak(type_node))

        min_argc = value.get('min_argc')
        if not isinstance(min_argc, int):
            min_argc = len(parameter_types)

        return_node = value.get('return')
        if return_node is None:
            return_type = NOVA
            return_weak = False
            allows_error = False
        else:
            return_type = self._annotation_type(return_node, NOVA)
            return_weak = self._annotation_weak(return_node)
            allows_error = self._annotation_error_union(return_node)

        return _Signature(
            name,
            parameter_names,
            parameter_types,
            parameter_weak,
            min_argc,
            return_type,
            return_weak,
            allows_error,
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

        previous = (
            self.return_type,
            self.return_weak,
            self.return_allows_error,
            self.in_function,
            self.this_type,
            self.loop_labels,
            self.loop_break_flags,
        )
        self.return_type = signature.return_type
        self.return_weak = signature.return_weak
        self.return_allows_error = signature.allows_error
        self.in_function = True
        self.this_type = this_type
        self.loop_labels = []
        self.loop_break_flags = []

        self._scope_push()
        try:
            arguments = value.get('args')
            if isinstance(arguments, list):
                for argument in arguments:
                    argument_value = argument.get('value') if isinstance(argument, dict) else None
                    type_node = argument_value.get('type') if isinstance(argument_value, dict) else None
                    if self._annotation_reference(type_node):
                        ## Inside the body a reference parameter behaves like
                        ## the target variable's own type.
                        name = self._identifier_name(argument_value.get('identifier'))
                        bound_type = self._annotation_type(type_node)
                        if bound_type.startswith('&'):
                            bound_type = bound_type[1:]
                        self._bind(name or '', bound_type, True, False)
                    else:
                        self._infer(argument)
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
            ) = previous

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
