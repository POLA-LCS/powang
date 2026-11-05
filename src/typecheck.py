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
from .state import get_state
from .powang_types import (
    PowangArray,
    PowangBoolean,
    PowangErrorValue,
    PowangFileStream,
    PowangFunction,
    PowangInteger,
    PowangMap,
    PowangNova,
    PowangNumber,
    PowangObjectType,
    PowangSome,
    PowangString,
    PowangTask,
)
from .error import (
    PowangError,
    powang_error_format,
    powang_error_type_match,
)
from .lexer.token import LexerTokenType, ParserTokenType

SOME = PowangSome.type
NOVA = PowangNova.type
BOOLEAN = PowangBoolean.type
INTEGER = PowangInteger.type
NUMBER = PowangNumber.type
STRING = PowangString.type
ARRAY = PowangArray.type
MAP = PowangMap.type
FUNCTION = PowangFunction.type
ERROR = PowangErrorValue.type
OBJECT = PowangObjectType.type
FILE = PowangFileStream.type
TASK = PowangTask.type

## `function` and `file` are runtime types but are absent from the parser's
## NATI_TYPES set, so they need explicit handling here.
NATIVE_TYPE_NAMES = set(NATI_TYPES) | {FUNCTION, FILE}

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
        return SOME
    if _is_array_type(type_name):
        return type_name[len(ARRAY_OPEN):-len(ARRAY_CLOSE)]
    return SOME


def _array_of(element_type: str) -> str:
    if element_type == SOME:
        return f'{ARRAY}[{SOME}]'
    return f'{ARRAY}[{element_type}]'

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
    'input' : SOME,
    'inputf': SOME,
    'typeof': STRING,
    'size'  : INTEGER,
    'open'  : BOOLEAN,
    'close' : BOOLEAN,
    'write' : SOME,
    'read'  : STRING,
    ## Tasks are opaque to the checker: a spawned call is always `task`,
    ## while the awaited result type is unknowable without generics.
    'wait'  : SOME,
    'cancel': SOME,
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
        self.scopes[-1][name] = _VariableInfo(type_name, annotated, weak)

    def _error(self, message: str, details: Optional[list[str]] = None, where: str = 'type checker'):
        self.errors.append(powang_error_format(
            'TYPE', where, message, details if details is not None else []
        ))

    def _assign_error(self, where: str, expected: str, encountered: str):
        self.errors.append(powang_error_type_match(where, expected, encountered))

    @staticmethod
    def _identifier_name(node: Any) -> Optional[str]:
        if not isinstance(node, dict):
            return None
        if node.get('type') != LexerTokenType.IDENTIFIER:
            return None
        value = node.get('value')
        return value if isinstance(value, str) else None

    def _type_name_from_node(self, node: Any) -> Optional[str]:
        """Resolve a type name used after `as`, including `arr[...]`."""
        if not isinstance(node, dict):
            return None
        if node.get('type') == LexerTokenType.IDENTIFIER:
            name = node.get('value')
            if not isinstance(name, str):
                return None
            if name == 'any':
                return SOME
            return self._normalized_type_name(name)
        if node.get('type') == ParserTokenType.INDEX_EXPRESSION:
            value = node.get('value')
            if not isinstance(value, dict):
                return None
            if self._identifier_name(value.get('target')) != ARRAY:
                return None
            element = self._type_name_from_node(value.get('index'))
            if element is None:
                return ARRAY
            return _array_of(element)
        return None

    def _normalized_type_name(self, name: str) -> str:
        seen: set[str] = set()
        while name in self.type_alias and name not in seen:
            seen.add(name)
            alias = self.type_alias[name]
            if isinstance(alias, str):
                name = alias
            elif isinstance(alias, dict):
                name = alias.get('value', SOME)
            else:
                break
        if name in NATIVE_TYPE_NAMES:
            return name
        return f'{OBJECT}:{name}'

    def _annotation_type(self, type_node: Any, default: str = SOME) -> str:
        if not isinstance(type_node, dict):
            return default
        inner = type_node.get('value')
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
            resolved = _array_of(self._annotation_type(element_node, SOME))
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

    def _assignable(self, target: str, source: str, target_weak: bool = False) -> bool:
        if target == SOME or source == SOME:
            return True
        if target.startswith('&') or source.startswith('&'):
            return target == source
        if target == source:
            return True
        if _is_array_type(target) and _is_array_type(source):
            target_element = _array_element_type(target)
            source_element = _array_element_type(source)
            if target_element == SOME:
                return True
            if target_element == MIXED or source_element == MIXED:
                return target_element == source_element
            if source_element == SOME:
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
        for statement in program_ast:
            self._infer(statement)
        return self.errors

    # -------------------------------------------------------------- inference
    def _infer(self, node: Any) -> str:
        try:
            return self._infer_inner(node)
        except Exception:
            # A type checker must never crash on an unexpected AST shape.
            return SOME

    def _infer_inner(self, node: Any) -> str:
        if not isinstance(node, dict) or not node:
            return SOME

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
        if node_type == ParserTokenType.ARRAY_EXPRESSION:
            return self._infer_array(value)
        if node_type == ParserTokenType.TUPLE_EXPRESSION:
            for element in value.get('elements', []) if isinstance(value, dict) else []:
                self._infer(element)
            return 'tup'
        if node_type == ParserTokenType.KEY_VALUE_PAIR:
            self._infer(value.get('key'))
            self._infer(value.get('value'))
            return SOME
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
        if node_type == ParserTokenType.TYPE_DECLARATION:
            return self._infer_type_declaration(value)
        if node_type == ParserTokenType.EXTERN_REFERENCE:
            return self._infer_extern(value)

        # USE_EXPRESSION and any unknown shape: gradual skip.
        return SOME

    # ------------------------------------------------------------ expressions
    def _infer_reference(self, value: Any) -> str:
        """Type of `&name`: a reference to the target variable's type."""
        if not isinstance(value, dict):
            return SOME
        name = self._identifier_name(value.get('target'))
        if name is None:
            return SOME
        variable = self._lookup(name)
        if variable is None or variable.type in (SOME, NOVA):
            return SOME
        return f'&{variable.type}'

    def _infer_identifier(self, name: Any) -> str:
        if not isinstance(name, str):
            return SOME
        if name == NOVA:
            return NOVA
        if name in ('true', 'false'):
            return BOOLEAN
        if name == 'this':
            return self.this_type if self.this_type is not None else SOME
        variable = self._lookup(name)
        if variable is not None:
            return variable.type
        if name in self.functions:
            return FUNCTION
        if name in self.object_types:
            return f'{OBJECT}:{name}'
        return SOME

    def _infer_unary(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        operator = value.get('operator')
        operator_name = operator.get('value') if isinstance(operator, dict) else None
        right_type = self._infer(value.get('right'))
        if operator_name == '!':
            return BOOLEAN
        if operator_name == '-':
            return right_type if right_type in NUMERIC_TYPES else SOME
        if operator_name == '[-]':
            return right_type if right_type in {INTEGER, NUMBER, STRING, ARRAY} else SOME
        if operator_name == '+':
            return right_type
        return SOME

    def _infer_binary(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
                return SOME
            return target_type

        if operator_name == '??':
            left_type = self._infer(left_node)
            right_type = self._infer(right_node)
            if left_type == NOVA:
                return right_type
            if right_type == NOVA:
                return left_type
            if left_type == SOME:
                return right_type
            if right_type == SOME:
                return left_type
            if left_type == right_type:
                return left_type
            if self._assignable(left_type, right_type):
                return left_type
            if self._assignable(right_type, left_type):
                return right_type
            return SOME

        if operator_name == ':>':
            if isinstance(right_node, dict) and right_node.get('type') == ParserTokenType.CALL_EXPRESSION:
                call_value = dict(right_node.get('value') or {})
                call_value['arguments'] = [left_node] + list(call_value.get('arguments', []))
                return self._infer_call(call_value)
            self._infer(left_node)
            self._infer(right_node)
            return SOME

        left_type = self._infer(left_node)
        right_type = self._infer(right_node)

        if operator_name in LOGICAL_OPERATORS or operator_name in COMPARISON_OPERATORS:
            return BOOLEAN

        return self._binary_result(operator_name, left_type, right_type, bool(value.get('typed')))

    def _binary_result(self, operator: Optional[str], left: str, right: str, typed: bool) -> str:
        if operator is None:
            return SOME
        if left == SOME or right == SOME:
            return SOME
        if left == NOVA or right == NOVA:
            return SOME

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
            return target if target in NUMERIC_TYPES else SOME

        if left == right and left in {INTEGER, NUMBER, STRING, MAP, BOOLEAN}:
            return left
        if _is_array_type(left) and _is_array_type(right):
            return self._common_array_type(left, right)

        return SOME

    def _common_array_type(self, left: str, right: str) -> str:
        if left == right:
            return left
        left_element = _array_element_type(left)
        right_element = _array_element_type(right)
        if left_element == SOME:
            return right
        if right_element == SOME:
            return left
        if self._assignable(left_element, right_element):
            return left
        if self._assignable(right_element, left_element):
            return right
        return _array_of(SOME)

    def _infer_call(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
            return SOME

        builtins = self._builtins()
        if callee_name in builtins:
            if named_nodes:
                self._error(
                    f"Builtin '{callee_name}' does not accept named arguments",
                    ['pass the arguments positionally'],
                    where=f'function call: {callee_name}',
                )
                return BUILTIN_RETURN_TYPES.get(callee_name, SOME)
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
            return BUILTIN_RETURN_TYPES.get(callee_name, SOME)

        if callee_name in self.functions:
            candidates = self.functions[callee_name]
            if named_nodes:
                if len(candidates) != 1:
                    self._error(
                        f"Named arguments for '{callee_name}' require a single overload",
                        [f"found {len(candidates)} overloads"],
                        where=f'function call: {callee_name}',
                    )
                    return candidates[0].return_type if candidates else SOME
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
            return candidates[0].return_type if candidates else SOME

        # A function value stored in a variable has no statically known
        # signature. Unknown callees are skipped, never rejected.
        return SOME

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
            if parameter_type == SOME or argument_type == SOME:
                continue
            if not self._assignable(parameter_type, argument_type, parameter_weak):
                return False
        return True

    def _infer_method_call(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        owner_type = self._infer(value.get('owner'))
        method_name = self._identifier_name(value.get('method'))
        arguments = value.get('arguments')
        if isinstance(arguments, list):
            for argument in arguments:
                self._infer(argument)
        if method_name is not None and isinstance(owner_type, str) and owner_type.startswith(f'{OBJECT}:'):
            object_name = owner_type.split(':', 1)[1]
            info = self.object_types.get(object_name)
            if info is not None:
                methods = info.get('methods', {}).get(method_name)
                if methods:
                    return methods[0].return_type
        return SOME

    def _infer_index(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        target_type = self._infer(value.get('target'))
        self._infer(value.get('index'))
        if target_type == STRING:
            return STRING
        if _is_array_type(target_type):
            return _array_element_type(target_type)
        # Map values have no statically known element type in this slice.
        return SOME

    def _infer_access(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        target_type = self._infer(value.get('target'))
        property_name = self._identifier_name(value.get('property'))
        if property_name is None:
            return SOME
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
            }.get(property_name, SOME)
        if isinstance(target_type, str) and target_type.startswith(f'{OBJECT}:'):
            object_name = target_type.split(':', 1)[1]
            info = self.object_types.get(object_name)
            if info is not None:
                return info.get('props', {}).get(property_name, SOME)
        return SOME

    def _infer_array(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
        common = element_types[0]
        for element_type in element_types[1:]:
            if element_type == common or common == SOME:
                continue
            if self._assignable(common, element_type):
                continue
            if self._assignable(element_type, common):
                common = element_type
                continue
            common = MIXED
            break
        return _array_of(common)

    def _infer_block(self, statements: Any) -> str:
        if not isinstance(statements, list):
            return SOME
        self._scope_push()
        try:
            for statement in statements:
                self._infer(statement)
        finally:
            self._scope_pop()
        return SOME

    def _infer_unwrap(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
            return SOME

        return SOME if operand_type == ERROR else operand_type

    # ------------------------------------------------------------ declarations
    def _infer_declaration_undefined(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        name = self._identifier_name(value.get('identifier'))
        type_node = value.get('type')
        declared_type = self._annotation_type(type_node)
        self._bind(name or '', declared_type, True, self._annotation_weak(type_node))
        return declared_type

    def _infer_declaration_typed(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
            return SOME
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
        inferred_type = source_type if source_type else SOME
        self._bind(name or '', inferred_type, False, False)
        return inferred_type

    def _infer_destructure_declaration(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        pattern = value.get('pattern')
        if not isinstance(pattern, dict):
            return SOME
        pattern_value = pattern.get('value')
        if not isinstance(pattern_value, dict):
            pattern_value = pattern
        entries = pattern_value.get('entries')
        if not isinstance(entries, list):
            entries = []
        group_type_node = pattern_value.get('group_type')
        group_reference = bool(pattern_value.get('group_reference'))
        source_type = self._infer(value.get('expression'))

        array_element = _array_element_type(source_type) if _is_array_type(source_type) else SOME
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
                entry_type = object_props.get(name, SOME)
                explicit = False
            else:
                entry_type = array_element
                explicit = False
            if entry_type == MIXED:
                entry_type = SOME

            if explicit and not reference:
                source_entry_type = object_props.get(name, SOME) if object_props is not None else array_element
                if source_entry_type == MIXED:
                    source_entry_type = SOME
                if source_entry_type != SOME and entry_type != SOME and \
                        not self._assignable(entry_type, source_entry_type):
                    self._assign_error(f'destructuring: {name}', entry_type, source_entry_type)

            self._bind(name, entry_type, explicit or reference, False)
        return source_type

    def _infer_assignment(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
            if declared_type not in (SOME, NOVA, ERROR):
                if not self._assignable(declared_type, source_type):
                    self._assign_error('property assignment', declared_type, source_type)
        elif target_type == ParserTokenType.INDEX_EXPRESSION:
            declared_type = self._infer_index(target.get('value'))
            if declared_type not in (SOME, NOVA, ERROR, MIXED):
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
        if source_type == SOME:
            return source_type
        if self.return_allows_error and source_type == ERROR:
            return source_type
        if not self._assignable(self.return_type, source_type, self.return_weak):
            self._assign_error('function return', self.return_type, source_type)
        return source_type

    # -------------------------------------------------------------- statements
    def _infer_if(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        self._scope_push()
        try:
            self._infer(value.get('expression'))
            self._infer(value.get('block'))
        finally:
            self._scope_pop()
        else_block = value.get('else')
        if else_block is not None:
            self._infer(else_block)
        return SOME

    def _infer_match(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
                            if type_node is not None and subject_type != SOME:
                                if not self._assignable(bind_type, subject_type):
                                    self._assign_error('match pattern', bind_type, subject_type)
                            if bind_type == MIXED:
                                bind_type = SOME
                            self._bind(name or '', bind_type, type_node is not None, False)
                        elif kind == 'literal':
                            self._infer(pattern.get('value'))
                    guard = case.get('guard')
                    if guard is not None:
                        self._infer(guard)
                    self._infer(case.get('block'))
                finally:
                    self._scope_pop()
        return SOME

    def _infer_try(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
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
        return SOME

    def _infer_for(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        self._scope_push()
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
            self._scope_pop()
        return SOME

    def _infer_for_each(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        self._scope_push()
        try:
            iterable_node = value.get('expression')
            iterable_type = self._infer(iterable_node)
            iterator = value.get('iterator')
            element_type = _array_element_type(iterable_type) if _is_array_type(iterable_type) else SOME
            is_literal = isinstance(iterable_node, dict) and \
                iterable_node.get('type') == ParserTokenType.ARRAY_EXPRESSION

            if is_literal and isinstance(iterator, dict):
                self._check_for_each_elements(iterable_node, iterator)

            iterator_kind = iterator.get('type') if isinstance(iterator, dict) else None
            iterator_value = iterator.get('value') if isinstance(iterator, dict) else None
            if isinstance(iterator_value, dict):
                if iterator_kind == ParserTokenType.DECLARATION_UNDEFINED and iterator_value.get('inferred'):
                    ## Bare `for x >> values` takes the arr element type.
                    name = self._identifier_name(iterator_value.get('identifier'))
                    bind_type = element_type if element_type not in (SOME, MIXED) else SOME
                    self._bind(name or '', bind_type, False, False)
                else:
                    declared_type = self._annotation_type(iterator_value.get('type'))
                    if not is_literal and declared_type not in (SOME, NOVA) and element_type not in (SOME, MIXED):
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
            self._scope_pop()
        return SOME

    def _check_for_each_elements(self, array_node: dict, iterator: dict) -> None:
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
        if declared_type == SOME:
            return
        weak = self._annotation_weak(type_node)
        elements = array_node.get('elements')
        if not isinstance(elements, list):
            return
        for element in elements:
            element_type = self._infer(element)
            if element_type == SOME:
                continue
            if not self._assignable(declared_type, element_type, weak):
                self._assign_error('for each iterator', declared_type, element_type)
                return

    # ------------------------------------------------------------- user types
    def _infer_type_declaration(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        name = self._identifier_name(value.get('identifier'))
        if name is None:
            return SOME
        info = {'props': {}, 'methods': {}}
        self.object_types[name] = info

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
            if isinstance(methods, list):
                for entry in methods:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    _, method = entry
                    if not isinstance(method, dict):
                        continue
                    signature = self._make_signature(method)
                    if signature is not None and signature.name:
                        info['methods'].setdefault(signature.name, []).append(signature)
                    self._check_function(method, this_type=f'{OBJECT}:{name}', register=False)
        finally:
            self._scope_pop()
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
                parameter_types.append(SOME)
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
        )
        self.return_type = signature.return_type
        self.return_weak = signature.return_weak
        self.return_allows_error = signature.allows_error
        self.in_function = True
        self.this_type = this_type

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
            ) = previous

    # ----------------------------------------------------------------- extern
    def _infer_extern(self, value: Any) -> str:
        if not isinstance(value, dict):
            return SOME
        powang = value.get('powang')
        if isinstance(powang, dict):
            powang_type = powang.get('type')
            if powang_type == ParserTokenType.DECLARATION_FUN:
                self._check_function(powang, register=True)
            elif powang_type == ParserTokenType.TYPE_DECLARATION:
                self._infer_type_declaration(powang.get('value'))
        return SOME


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
    return type_check(program_ast, path)
