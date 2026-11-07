from .parser import *
from .error import *
from .builtins import *
from .scopestack import ScopeType, ScopeStack
from .state import fresh_state, get_state, set_state, reset_state, copy_for_task
from .builtins.tasks import check_cancellation, get_task_pool, spawn_task
from .lexer import *
from .typecheck import type_check
from .module_loader import get_module_loader
from . import typespec as _typespec

import math
import sys
import copy
import importlib
from contextvars import ContextVar

## Extern allowlist. This is installation configuration, not run state, so it
## stays a process-wide immutable set. The extern *bindings* declared by a
## program live on its InterpreterState.
_EXTERNAL_MODULES: set[str] = {
    "math",
}

## Standard library modules reachable from `extern ... >> "module.attr"`.
## Every import is optional: when a module is missing from an installation the
## interpreter still starts, and a module that tries to bind it gets the normal
## "module is not allowed" diagnostic instead of an import-time crash. The
## allowlist entry is only added when the module object is actually available,
## so the extern resolver can always find it in this module's globals.
try:
    from .stdlib import stdlib_strings
    _EXTERNAL_MODULES.add("stdlib_strings")
except ImportError:
    pass
try:
    from .stdlib import stdlib_json
    _EXTERNAL_MODULES.add("stdlib_json")
except ImportError:
    pass
try:
    from .stdlib import stdlib_url
    _EXTERNAL_MODULES.add("stdlib_url")
except ImportError:
    pass
try:
    from .stdlib import stdlib_env
    _EXTERNAL_MODULES.add("stdlib_env")
except ImportError:
    pass
try:
    from .stdlib import stdlib_time
    _EXTERNAL_MODULES.add("stdlib_time")
except ImportError:
    pass
try:
    from .stdlib import stdlib_crypto
    _EXTERNAL_MODULES.add("stdlib_crypto")
except ImportError:
    pass
try:
    from .stdlib import stdlib_http
    _EXTERNAL_MODULES.add("stdlib_http")
except ImportError:
    pass
try:
    from .stdlib import stdlib_http_server
    _EXTERNAL_MODULES.add("stdlib_http_server")
except ImportError:
    pass
try:
    from .stdlib import stdlib_http_router
    _EXTERNAL_MODULES.add("stdlib_http_router")
except ImportError:
    pass

try:
    from .stdlib import stdlib_log
    _EXTERNAL_MODULES.add("stdlib_log")
except ImportError:
    pass

EXTERNAL_MODULES: frozenset[str] = frozenset(_EXTERNAL_MODULES)
del _EXTERNAL_MODULES

def getPowangFromPython(python_data: Any) -> PowangAny:
    if python_data is None:
        return PowangNova()
    if isinstance(python_data, (list, tuple)):
        return PowangArray([getPowangFromPython(d) for d in python_data])
    if isinstance(python_data, dict):
        return PowangMap({getPowangFromPython(key): getPowangFromPython(value) for key, value in python_data.items()})
    ## check bool first: bool subclasses int, so the exact-type lookup below misses it
    if isinstance(python_data, bool):
        return PowangBoolean(python_data)
    powang_type: Optional[Callable[(...), PowangAny]] = {
        int   : PowangInteger,
        float : PowangNumber,
        str   : PowangString,
    }.get(type(python_data))
    if powang_type is None:
        try:
            from .state import get_state
            return PowangHandle(get_state().register_handle(python_data))
        except Exception:
            return PowangNova()
    return powang_type(python_data)

def getPythonFromPowang(powang_data: PowangAny):
    if powang_data.type == PowangHandle.type:
        from .state import get_state
        return get_state().resolve_handle(powang_data.data)
    if powang_data.type == PowangTask.type:
        ## Task handles name live threads and have no data representation.
        ## Rejecting them here keeps extern/JSON calls honest instead of
        ## silently serializing an internal id.
        raise powang_throw(powang_error_format(
            'TASK', 'extern conversion',
            'task values are not JSON-serializable', [
                f"task {powang_data.task_id} cannot cross the extern boundary",
            ]
        ))
    if powang_data.type == PowangReference.type:
        raise powang_throw(powang_error_format(
            'REFERENCE', 'extern boundary', "References cannot cross the extern boundary", [
                "references live only for the duration of a Powang call",
            ]))
    if powang_data.type == PowangFunction.type:
        ## A function value crossing into Python becomes a real callable. The
        ## HTTP server (and any other host callback) can then invoke Powang
        ## code from a foreign thread without sharing the caller's scopes.
        return _powang_function_to_python(powang_data, get_state())
    if powang_data.type == PowangArray.type:
        return [getPythonFromPowang(d) for d in powang_data.data]
    if powang_data.type == PowangMap.type:
        return {getPythonFromPowang(key): getPythonFromPowang(value) for key, value in powang_data.data.items()}
    return powang_data.data


class PowangCallbackError(RuntimeError):
    """Python-side failure of a Powang function called from host code.

    ``str(error)`` keeps the rendered Powang diagnostic so a host such as the
    HTTP server can log it without leaking a Python traceback to clients.
    """


def _powang_function_to_python(function: PowangFunction, state) -> Callable:
    """Adapt a Powang function value into a plain Python callable.

    Isolation matters here: the host may call the result from several threads
    at once. The captured state is snapshotted *once*, on the thread that
    performs the extern conversion, so later concurrent calls only clone an
    immutable template instead of reading a state the main thread may still be
    mutating.
    """
    template_state = state.clone_for_task()

    def python_callable(*arguments):
        call_state = template_state.clone_for_task()
        state_token = set_state(call_state)
        try:
            powang_arguments = [
                getPowangFromPython(argument) for argument in arguments
            ]
            ## An imported extern (for example `http_router.dispatch`) is a
            ## PowangFunction without a body; calling it through callFunction
            ## would iterate a None block. Dispatch it through the extern path.
            external = getattr(function, 'external', None)
            if external is not None:
                result = callExternalFunction(
                    'extern callback',
                    'function value',
                    function,
                    external,
                    powang_arguments,
                )
            else:
                result = callFunction(
                    'extern callback',
                    'function value',
                    function,
                    powang_arguments,
                )
            return getPythonFromPowang(result)
        except AssertionError as raw_error:
            ## PowangError subclasses AssertionError, and older call sites
            ## still raise a plain AssertionError wrapping one.
            converted = powang_error_from_exception(raw_error)
            if converted is None:
                raise
            raise PowangCallbackError(str(converted)) from None
        finally:
            reset_state(state_token)
            call_state.close()

    return python_callable

def getValidIdentifier(where: str, identifier: DictRepr) -> str:
    identifier_name = evaluateAstExpression(identifier, True)
    assert isinstance(identifier_name, str), powang_error_syntax_unexpected_token(
        where,
        identifier_name.type if isinstance(identifier_name, PowangTypeBase) else repr(identifier_name),
        TokenToString(LexerTokenType.IDENTIFIER))
    return identifier_name


def getCastTypeName(where: str, node: DictRepr) -> str:
    """Return the type name after `as`, accepting a type annotation node."""
    if isinstance(node, dict):
        if node.get('type') == LexerTokenType.IDENTIFIER:
            value = node.get('value')
            if isinstance(value, str):
                return value
        if node.get('type') == ParserTokenType.TYPE:
            inner = node.get('value')
            if isinstance(inner, dict):
                value = inner.get('value')
                if isinstance(value, str):
                    return value
        if node.get('type') == ParserTokenType.INDEX_EXPRESSION:
            value = node.get('value')
            if isinstance(value, dict):
                target = value.get('target')
                if isinstance(target, dict) and \
                        target.get('type') == LexerTokenType.IDENTIFIER and \
                        target.get('value') in (PowangArray.type, PowangTuple.type, PowangMap.type):
                    return target.get('value')
    raise powang_throw(powang_error_syntax('cast expression', 'Expected a type name after `as`', [
        'write a primitive type, a user type or arr[element]'
    ]))


def _evaluateDestructureDeclaration(where: str, expr_value: DictRepr) -> PowangAny:
    pattern = expr_value.get('pattern')
    pattern_value = pattern.get('value') if isinstance(pattern, dict) else pattern
    if not isinstance(pattern_value, dict):
        pattern_value = {}
    entries = pattern_value.get('entries')
    if not isinstance(entries, list):
        entries = []
    group_reference = bool(pattern_value.get('group_reference'))

    def entryTypeName(entry: dict) -> Optional[str]:
        type_node = entry.get('type') or pattern_value.get('group_type')
        if isinstance(type_node, dict):
            inner = type_node.get('value')
            if isinstance(inner, dict):
                name = inner.get('value')
                if isinstance(name, str):
                    return name
        return None

    source = evaluateAstExpression(expr_value.get('expression'))
    if source.type == PowangAnyType.type:
        source = PowangUnwrapAny(source)

    if source.type == PowangArray.type:
        for index, entry in enumerate(entries):
            if index >= len(source.data):
                raise powang_throw(powang_error_index_out_of_range(index, len(source.data)))
            reference = bool(entry.get('reference')) or group_reference
            if reference:
                value = PowangElementReference(source, index)
            else:
                value = source.data[index]
                type_name = entryTypeName(entry)
                if type_name in NATI_TYPES:
                    casted = explicitCast(type_name, value)
                    if casted is not None:
                        value = casted
                value = PowangCopyConstruct(value)
            ScopeStack.new_variable(entry['identifier']['value'], value)
        return source

    if source.type == PowangObjectType.type:
        for entry in entries:
            name = entry['identifier']['value']
            property_value = source.getProperty(name, False)
            if property_value is None:
                raise powang_throw(powang_error_identifier_not_found(where, name))
            reference = bool(entry.get('reference')) or group_reference
            if reference:
                value = PowangPropertyReference(source, name)
            else:
                value = property_value
                type_name = entryTypeName(entry)
                if type_name in NATI_TYPES:
                    casted = explicitCast(type_name, value)
                    if casted is not None:
                        value = casted
                value = PowangCopyConstruct(value)
            ScopeStack.new_variable(name, value)
        return source

    raise powang_throw(powang_error_type_match(where, 'array or object', source.type))


def getUndefinedVariable(where: str, type_expression: DictRepr):
    type_alias = get_state().type_alias
    if type_expression['value'] in type_alias:
        type_expression = type_alias[type_expression['value']]
    alternatives = type_expression.get('alternatives')
    if isinstance(alternatives, list) and alternatives:
        ## A union has no single runtime class. The gradual `any` holder keeps
        ## the concrete payload while the annotation decides assignability.
        undefined_right_value: PowangAny = PowangAnyType()
        undefined_right_value.any = type_node_inner(alternatives[0]).get('value', PowangAnyType.type)
        undefined_right_value.declared_spec = _typespec.from_ast_node({
            'type': ParserTokenType.TYPE,
            'value': type_expression,
        })
    elif type_expression.get('auto'):
        undefined_right_value = PowangAnyType()
        undefined_right_value.any = PowangAnyType.type
    elif type_expression['value'] in NATI_TYPES:
        undefined_right_value = PowangTypeMap(type_expression['value'])()
    else:
        user_type = ScopeStack.get_ObjectType(type_expression['value'])
        if user_type is None:
            raise powang_throw(powang_error_identifier_type(
                where, type_expression['value']
            ))
        undefined_right_value = PowangCopyConstruct(user_type)
    undefined_right_value.defined = False
    undefined_weak = PowangTypeBase.PropertyWeak(type_expression['weak'], False)
    undefined_const = PowangTypeBase.PropertyConst(type_expression['const'], True)
    undefined_right_value.weak   = undefined_weak
    undefined_right_value.const  = undefined_const
    undefined_right_value.structure_locked = bool(type_expression.get('const'))
    elements_locked = False
    element_node = type_expression.get('element_type')
    if isinstance(element_node, dict) and bool(element_node.get('value', {}).get('const')):
        elements_locked = True
    generics = type_expression.get('generics')
    if isinstance(generics, list):
        if type_expression.get('value') == PowangMap.type and len(generics) >= 2:
            if bool(generics[1].get('value', {}).get('const')):
                elements_locked = True
        elif type_expression.get('value') == PowangSet.type and generics:
            if bool(generics[0].get('value', {}).get('const')):
                elements_locked = True
    undefined_right_value.elements_locked = elements_locked
    return undefined_right_value

def checkObjectTypes(where: str, target_value: PowangObjectType, right_value: PowangAny) -> PowangObjectType:
    if checkReturnsNova(where, target_value, right_value):
        return target_value

    user_type = ScopeStack.get_existingObjectType(target_value.type_name)

    if right_value.type == PowangTuple.type:
        right_value = PowangArray(list(right_value.data))
    elif right_value.type != PowangArray.type:
        right_value = PowangArray([right_value])

    casted_value = castToObjectType(where, user_type, target_value, right_value)
    return casted_value

def castToObjectType(where: str, user_type: PowangObjectType, target_value: PowangObjectType, right_value: PowangArray) -> PowangObjectType:
    constructor_methods = user_type.getConstructors()
    constructor_return: Optional[PowangAny] = None
    constructor_candidate = getFunctionCandidate(constructor_methods, right_value.data)
    constructor_return = callMethod(where, user_type, CONSTRUCTOR_METHOD_NAME, constructor_candidate, right_value.data)
    assert constructor_return.type == PowangObjectType.type and constructor_return.type_name == user_type.type_name, powang_error_type_match(where, target_value.type_name, constructor_return.type_name)
    return constructor_return


def checkReturnsNova(where: str, target_value: PowangAny, right_value: PowangAny) -> bool:
    if not target_value.weak.it_is and target_value.type != PowangNova.type:
        assert right_value.weak.has_value, powang_error_strong_nova_assign(where, target_value.type)

    elif not right_value.weak.has_value:
        return True
    return False

def checkTypes(where: str, target_value: PowangAny, right_value: PowangAny) -> PowangAny:
    if checkReturnsNova(where, target_value, right_value):
        return target_value

    if right_value.type == PowangAnyType.type:
        right_value = unwrap_any_value(right_value)

    if target_value.type != right_value.type and target_value.type != PowangAnyType.type:
        casted_right_value = PowangTypeCast(target_value.type, right_value)
        if casted_right_value is None:
            raise powang_throw(powang_error_type_match(
                where,
                target_value.type,
                right_value.type,
            ))
        return PowangCopyConstruct(casted_right_value)
    return PowangCopyConstruct(right_value)

def assignWithChecks(where: str, target_value: PowangAny, right_value: PowangAny, force_object_assign: bool):
    if right_value.type == PowangAnyType.type:
        right_value = PowangUnwrapAny(right_value)

    if target_value.const:
        assert not target_value.defined or target_value.const.can_change, powang_error_format(
            "CONST", where, "Trying to assign to a strong const", [
                f"{right_value.type} -> {target_value.type}!"])
        target_value.const.can_change = False


    if right_value.type == PowangReference.type:
        raise powang_throw(powang_error_format(
            'REFERENCE', where, "References cannot be stored", [
                "a reference only lives for the duration of one call",
                "use &variable directly as a &parameter argument",
            ]))

    if target_value.type == PowangAnyType.type:
        declared_spec = getattr(target_value, 'declared_spec', None)
        if declared_spec is not None and declared_spec.kind is _typespec.Kind.UNION:
            concrete = unwrap_any_value(right_value)
            if not _typespec.assignable(declared_spec, value_type_spec(concrete)):
                raise powang_throw(powang_error_type_match(
                    where,
                    _typespec.render(declared_spec),
                    concrete.type if concrete.type != PowangObjectType.type else concrete.type_name,
                ))
        # PowangCopyConstruct handles types whose constructor signature is not
        # (data,) - e.g. PowangFunction(args, data, return_expr).
        target_value.data = PowangCopyConstruct(right_value).data
        target_value.any = (
            right_value.type_name
            if right_value.type == PowangObjectType.type
            else right_value.type
        )
        target_value.concrete_value = PowangCopyConstruct(right_value)

    elif target_value.type == PowangErrorValue.type and right_value.type == PowangErrorValue.type:
        ## Error values carry a structured payload beside `data`; copy both.
        target_value.data = right_value.data
        target_value.error = right_value.error

    elif target_value.type == PowangObjectType.type:
        copy_constructor_result: Optional[PowangAny] = None
        if areSameObjectType(target_value, right_value) and right_value.type == PowangObjectType.type:
            if not force_object_assign:
                target_value.defined = True
                target_value.weak.has_value = right_value.weak.has_value
                for const in target_value.getConstructors():
                    if len(const.args) == 1 and const.args[0]['value']['type']['value']['value'] == target_value.type_name:
                        copy_constructor_result = callMethod(where, target_value, CONSTRUCTOR_METHOD_NAME, const, [right_value])
                        break
            check_result = copy_constructor_result \
            if copy_constructor_result is not None and copy_constructor_result.type == PowangObjectType.type \
            else PowangCopyConstructObjectType(right_value)
        else:
            check_result = checkObjectTypes(where, target_value, right_value)
        target_value.data = PowangCopyConstructObjectType(check_result).data if check_result.type == PowangObjectType.type else check_result.data
        target_value.private_props = check_result.private_props
    else:
        check_result = checkTypes(where, target_value, right_value)
        target_value.data = check_result.data # type: ignore

    target_value.defined = True
    target_value.weak.has_value = right_value.weak.has_value
    return target_value

def performOperation(operator: str, left: PowangAny, right: PowangAny, typed: bool) -> PowangAny:
    if left.type == PowangAnyType.type:
        left = unwrap_any_value(left)
    if right.type == PowangAnyType.type:
        right = unwrap_any_value(right)
    if operator in {'+', '-', '*', '/', '%'}:
        assert left.type != PowangNova.type and left.weak.has_value, powang_error_unsupported_operation(
            'operation', f'nova weak {left.type}', operator, right.type)
        assert right.type != PowangNova.type and right.weak.has_value, powang_error_unsupported_operation(
            'operation', left.type, operator, f'nova weak {right.type}')
    result: PowangAny | None = None
    match operator:
        case '+' : result = left + right
        case '-' : result = left - right
        case '*' : result = left * right
        case '/' : result = left / right
        case '%' : result = left % right
        case _:
            result = PowangBoolean(False)
            if not left.weak.has_value or not right.weak.has_value:
                assert operator in {'==', '!='}, powang_error_format("VALUE", 'comparisson', "Invalid weak comparisson", [
                    "trying to compare greatness or lessness with non strong values"
                ])
                if operator == '==':
                    return PowangBoolean(left.weak.has_value == right.weak.has_value)
                return PowangBoolean(left.weak.has_value != right.weak.has_value)
            if left.type != right.type:
                if typed:
                    return result
                casted = PowangTypeCast(left.type, right)
                assert casted is not None, powang_error_unsupported_operation('comparisson', left.type, operator, right.type)
                return performOperation(operator, left, casted, False)
            match operator:
                case '==':
                    result.data = left == right
                case '!=':
                    result.data = left != right
                case '<=':
                    result.data = left < right or left == right
                case '>=':
                    result.data = left > right or left == right
                case '<':
                    result.data = left < right
                case '>':
                    result.data = left > right
            return result
    if result is None:
        if typed:
            casted = PowangTypeCast(right.type, left)
            assert casted is not None, powang_error_unsupported_operation('implicit typed operation', left.type, operator, right.type)
            return performOperation(operator, casted, right, False)
        else:
            casted = PowangTypeCast(left.type, right)
            assert casted is not None, powang_error_unsupported_operation('implicit operation', left.type, operator, right.type)
        return performOperation(operator, left, casted, typed)
    return result

def getIndexedValue(where: str, expression: DictRepr, subscript_check: bool):
    target_value = evaluateAstExpression(expression['target'])
    assert target_value.defined, powang_error_undefined_reference(
        TokenToString(ParserTokenType.ASSIGNMENT),
        expression['target']['value'])
    if target_value.type == PowangAnyType.type:
        target_value = unwrap_any_value(target_value)
    index = evaluateAstExpression(expression['index'])
    if subscript_check:
        assert target_value.type != PowangString.type, powang_error_format("ASSIGN", where, "str type is not subscriptable for now.")
    return target_value.index(index)

def getErrorProperty(where: str, error_value: PowangErrorValue, property_identifier: str) -> PowangAny:
    error = error_value.error
    if error is None:
        return PowangNova()
    match property_identifier:
        case 'kind':
            return PowangString(error.kind)
        case 'message':
            return PowangString(error.message)
        case 'details':
            return PowangArray([PowangString(detail) for detail in error.details])
        case 'where':
            return PowangString(error.where) if error.where is not None else PowangNova()
        case 'line':
            return PowangInteger(error.line) if error.line is not None else PowangNova()
        case 'column':
            return PowangInteger(error.column) if error.column is not None else PowangNova()
        case 'cause':
            return PowangErrorValue.from_error(error.cause) if error.cause is not None else PowangNova()
        case 'frames':
            return PowangArray([PowangString(frame) for frame in error.frames])
    raise powang_throw(powang_error_identifier_not_found(where, property_identifier, [
        "error values expose: kind, message, details, where, line, column, cause",
    ]))


def _score_parameter(type_node: DictRepr, param: PowangAny) -> int:
    spec = _typespec.from_ast_node(type_node)
    concrete = unwrap_any_value(param)
    source = value_type_spec(concrete)
    if spec.name == 'any' or source.name == 'any':
        return 1
    if spec.kind is _typespec.Kind.UNION:
        if not spec.args:
            return 1
        return max(_score_parameter_spec(branch, concrete, source) for branch in spec.args)
    return _score_parameter_spec(spec, concrete, source)


def _score_parameter_spec(spec: _typespec.TypeSpec, concrete: PowangAny, source: _typespec.TypeSpec) -> int:
    if spec.name == 'any' or source.name == 'any':
        return 1
    if spec == source:
        return 3
    if spec.name == concrete.type_name or spec.name == concrete.type:
        return 3
    if _typespec.assignable(spec, source):
        return 2
    try:
        casted = explicitCast(spec, concrete)
    except PowangError:
        casted = None
    return 1 if casted is not None else -1


def getFunctionCandidate(match_functions: list[PowangFunction], call_parameters: list[PowangAny]):
    candidates: list[int] = [0] * len(match_functions)
    max_score: int | None = None
    max_indices: list[int] = []
    for func_index, match_func in enumerate(match_functions):
        if len(call_parameters) == len(match_func.args):
            candidates[func_index] += 3
        elif len(call_parameters) == match_func.min_argc:
            candidates[func_index] += 2
        for match_arg, param in zip(match_func.args, call_parameters):
            candidates[func_index] += _score_parameter(
                match_arg['value']['type'], param
            )
            if match_arg['value']['type']['value']['weak']:
                if param.weak:
                    candidates[func_index] += 1
                if not param.weak.has_value:
                    candidates[func_index] += 2
            elif not param.weak.it_is:
                candidates[func_index] += 1
        if max_score is None or candidates[func_index] > max_score:
            max_score = candidates[func_index]
            max_indices = [func_index]
        elif candidates[func_index] == max_score:
            max_indices.append(func_index)

    if len(max_indices) != 1:
        raise powang_throw(powang_error_format('OVERLOAD', 'function overload resolution',
            'Ambiguous call, multiple overloads match equally well', [
                *[f"candidate {i}: {match_functions[i]}" for i in max_indices]
            ]))

    return match_functions[max_indices[0]]

def areSameObjectType(left: PowangAny, right: PowangAny):
    return (
        left.type == PowangObjectType.type and \
        left.type_name == right.type_name
    )

def checkFunctionArguments(where: str, callee: str, candidate: PowangFunction, call_parameters: list[PowangAny]):
    for i, call_arg in enumerate(candidate.args):
        argument_value = call_arg.get('value') if isinstance(call_arg, dict) else None
        param_type_node = argument_value.get('type') if isinstance(argument_value, dict) else None
        param_type = param_type_node.get('value') if isinstance(param_type_node, dict) else None
        is_reference = isinstance(param_type, dict) and bool(param_type.get('reference'))

        if is_reference:
            if i >= len(call_parameters):
                continue
            parameter_name = argument_value.get('identifier', {}).get('value')
            argument = call_parameters[i]
            if argument.type != PowangReference.type:
                raise powang_throw(powang_error_format(
                    'REFERENCE', 'function call', "Expected a reference argument", [
                        f"parameter '{parameter_name}' is declared as &{param_type.get('value')}",
                        "pass it as &variable",
                        f"but {argument.type} was encountered",
                    ]))
            expected = param_type.get('value')
            if argument.target_type not in {expected, PowangAnyType.type}:
                raise powang_throw(powang_error_format(
                    'REFERENCE', 'function call', "Reference type does not match", [
                        f"expected &{expected}",
                        f"but &{argument.target_type} was encountered",
                    ]))
            ScopeStack.new_variable(parameter_name, argument)
            continue

        call_argument = evaluateAstExpression(call_arg)

        if i < len(call_parameters):
            argument_value = copy_for_task(call_parameters[i])
            assignWithChecks('function call', call_argument, argument_value,
               areSameObjectType(call_argument, argument_value)
                # force object assign condition
            )

    if len(call_parameters) > len(candidate.args):
        raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'too many arguments'))
    if len(call_parameters) < candidate.min_argc:
        raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'not enought arguments'))

    for i, call_arg in enumerate(call_parameters):
        if not call_arg.defined:
            raise powang_throw(powang_error_undefined_argument(callee, i + 1, call_arg.type))
    return None

def callFunction(where: str, callee: str, candidate: PowangFunction, call_parameters: list[PowangAny]):
    call_parameters = resolveNamedArguments(where, candidate, call_parameters, [])
    ## Error-union functions (`: type?`) may return an error VALUE in place of
    ## the declared type. Raised errors (`error(...)`) still propagate as
    ## exceptions: annotations are erasable and never change raising behavior.
    allows_error_union = bool(
        isinstance(candidate.return_expr, dict)
        and candidate.return_expr.get('error_union')
    )

    closure = getattr(candidate, 'closure', None)
    saved_scopes = None
    if closure is not None:
        ## Module functions keep lexical access to their defining module
        ## scope even after that scope has been popped from the live stack.
        ## The caller's scopes are hidden so the call is lexically isolated.
        saved_scopes = ScopeStack.save_scopes()
        ScopeStack.reset_scopes()
        ScopeStack.push_captured(
            closure['variables'],
            closure['functions'],
            closure['ObjectTypes'],
        )
    ScopeStack.push(ScopeType.FUNCTION)
    return_value: PowangAny = PowangNova()
    try:
        try:
            checkFunctionArguments(where, callee, candidate, call_parameters)

            for call_statement in candidate.data:
                check_cancellation()
                evaluateAstExpression(call_statement)
                if ScopeStack.return_value is not None:
                    return_value = PowangCopyConstruct(ScopeStack.return_value)
                    ScopeStack.return_value = None
                    break
        finally:
            # The function scope must unwind even when a Powang error
            # propagates out, otherwise the REPL leaks one frame per call.
            ScopeStack.pop()

        if allows_error_union and return_value.type == PowangErrorValue.type:
            return PowangCopyConstruct(return_value)

        return_expression_value = getUndefinedVariable(where, candidate.return_expr)
        assignWithChecks(f'function return: {callee}', return_expression_value, return_value,
            areSameObjectType(return_expression_value, return_value)
        )

        return return_expression_value
    finally:
        if saved_scopes is not None:
            ScopeStack.restore_scopes(saved_scopes)

def callMethod(where: str, owner: PowangObjectType, method_name: str, method: PowangFunction, arguments: list[PowangAny]):
    ScopeStack.method_call_stack.append(owner)
    return_value = callFunction(where, method_name, method, arguments)
    ScopeStack.method_call_stack.pop()
    return return_value


def callExternalFunction(
    where: str,
    callee: str,
    function: PowangFunction,
    external: Callable,
    call_parameters: list[PowangAny],
) -> PowangAny:
    ## extern signatures have no body scope of their own, evaluate their
    ## argument declarations in a throwaway scope
    call_parameters = resolveNamedArguments(where, function, call_parameters, [])
    ScopeStack.push()
    try:
        checkFunctionArguments(where, callee, function, call_parameters)
    finally:
        ScopeStack.pop()

    try:
        if len(call_parameters) > 0:
            powang_data: list = [getPythonFromPowang(param) for param in call_parameters]
            external_return: Any = external(*powang_data)
        else:
            external_return: Any = external()
    except Exception as python_error:
        raise powang_throw(powang_error_format('EXTERN', f'extern function: {callee}',
            'The extern function raised an exception', [
                f"{type(python_error).__name__}: {python_error}"
            ]))

    return getPowangFromPython(external_return)


def callFunctionValue(
    where: str,
    callee: str,
    value: Any,
    call_parameters: list[PowangAny],
) -> PowangAny:
    """Call a first-class function value or an exported overload set."""
    if isinstance(value, list):
        if not value:
            raise powang_throw(powang_error_identifier_not_found(where, callee))
        candidate = getFunctionCandidate(value, call_parameters)
    else:
        candidate = value

    if getattr(candidate, 'type', None) != PowangFunction.type:
        raise powang_throw(powang_error_format(
            'MODULE', where, f"'{callee}' is not callable", [
                f"it is a {getattr(candidate, 'type', type(candidate).__name__)} value",
            ]
        ))

    external = getattr(candidate, 'external', None)
    if external is not None:
        return callExternalFunction(where, callee, candidate, external, call_parameters)
    return callFunction(where, callee, candidate, call_parameters)


def resolveNamedArguments(
    where: str,
    candidate: PowangFunction,
    positional: list[PowangAny],
    named: list[tuple[str, PowangAny]],
) -> list[PowangAny]:
    arg_names = [
        arg['value']['identifier']['value']
        for arg in candidate.args
        if isinstance(arg, dict) and isinstance(arg.get('value'), dict)
    ]
    resolved: list[PowangAny | None] = [None] * len(arg_names)
    for index, value in enumerate(positional):
        if index >= len(resolved):
            raise powang_throw(powang_error_format('ARGUMENT', where, 'too many arguments'))
        resolved[index] = value
    for name, value in named:
        if name not in arg_names:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, f"Unknown named argument '{name}'", [
                    f"parameters: {', '.join(arg_names)}",
                ],
            ))
        index = arg_names.index(name)
        if resolved[index] is not None:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, f"Duplicate argument '{name}'",
            ))
        resolved[index] = value
    for index, value in enumerate(resolved):
        if value is not None:
            continue
        if index < candidate.min_argc:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where,
                f"Missing required argument '{arg_names[index]}'", [
                    f"parameters: {', '.join(arg_names)}",
                ],
            ))
        argument_value = candidate.args[index].get('value') if isinstance(candidate.args[index], dict) else None
        default_expression = argument_value.get('expression') if isinstance(argument_value, dict) else None
        if default_expression is None:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where,
                f"Missing required argument '{arg_names[index]}'", [
                    f"parameters: {', '.join(arg_names)}",
                ],
            ))
        resolved[index] = evaluateAstExpression(default_expression)
    return [value for value in resolved if value is not None]


def _executeCallNode(where: str, callee_node: DictRepr, call_parameters: list[PowangAny], named_arguments: list[tuple[str, PowangAny]] | None = None) -> PowangAny:
    """Perform a call whose arguments have already been evaluated.

    Shared by normal ``CALL_EXPRESSION`` evaluation and by task workers, which
    receive parent-evaluated arguments instead of re-evaluating them.
    """
    if named_arguments is None:
        named_arguments = []
    ## Generalized call targets: a callee does not have to be a bare
    ## identifier. Namespace members, indexed callables and other
    ## expression-shaped targets are resolved to a function value.
    if callee_node.get('type') != LexerTokenType.IDENTIFIER:
        if callee_node.get('type') == ParserTokenType.ACCESS_EXPRESSION:
            access_value = callee_node['value']
            access_target = evaluateAstExpression(access_value['target'])
            member_name = getValidIdentifier(where, access_value['property'])
            if access_target.type == PowangModule.type:
                if named_arguments:
                    raise powang_throw(powang_error_format(
                        'ARGUMENT', where, 'Named arguments are not supported for module members',
                    ))
                return callModuleMember(where, access_target, member_name, call_parameters)
        if named_arguments:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, 'Named arguments are not supported for this callee',
            ))
        callee_value = evaluateAstExpression(callee_node)
        return callFunctionValue(where, '<expression>', callee_value, call_parameters)

    call_callee = getValidIdentifier(where, callee_node)

    ## Local definitions win over imported extern bindings. A module may import
    ## a module whose extern is named like one of its own helpers (for example
    ## `json.parse` versus a local `parse`), and the local definition must keep
    ## resolving. Wildcard-imported externs still carry an `external` attribute,
    ## so they are dispatched through the extern path.
    if (match_functions := ScopeStack.get_functions(call_callee)) is not None:
        if named_arguments:
            if len(match_functions) != 1:
                raise powang_throw(powang_error_format(
                    'ARGUMENT', where, f"Named arguments for '{call_callee}' require a single overload", [
                        f"found {len(match_functions)} overloads",
                    ],
                ))
            candidate = match_functions[0]
            call_parameters = resolveNamedArguments(where, candidate, call_parameters, named_arguments)
        else:
            candidate = getFunctionCandidate(match_functions, call_parameters)
        external = getattr(candidate, 'external', None)
        if external is not None:
            if named_arguments:
                raise powang_throw(powang_error_format(
                    'ARGUMENT', where, 'Named arguments are not supported for external functions',
                ))
            return callExternalFunction(where, call_callee, candidate, external, call_parameters)
        return callFunction(where, call_callee, candidate, call_parameters)

    if call_callee in get_state().external_functions:
        if named_arguments:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, 'Named arguments are not supported for external functions',
            ))
        function, external = get_state().external_functions[call_callee]
        return callExternalFunction(where, call_callee, function, external, call_parameters)

    if call_callee in BUILTINS:
        call_min_argc, call_max_argc, call_func = BUILTINS[call_callee]
        if call_max_argc != -1:
            assert len(call_parameters) <= call_max_argc, powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
        assert len(call_parameters) >= call_min_argc, powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')
        return call_func(*call_parameters)

    # First-class function values: a variable may hold a PowangFunction.
    if (call_variable := ScopeStack.get_variable(call_callee)) is not None \
            and call_variable.type == PowangFunction.type:
        return callFunction(where, call_callee, call_variable, call_parameters)
    raise powang_throw(powang_error_identifier_not_found(where, call_callee))


def _prepareTaskCall(where: str, callee_node: DictRepr, call_parameters: list[PowangAny]) -> Callable[[], PowangAny]:
    """Resolve a call in the parent and return a zero-argument task body.

    Resolution happens before the task starts so local functions and
    first-class values keep working, and so overload selection sees exactly
    the arguments the parent evaluated. The returned callable runs in the
    worker with the cloned state installed.
    """
    if callee_node.get('type') != LexerTokenType.IDENTIFIER:
        if callee_node.get('type') == ParserTokenType.ACCESS_EXPRESSION:
            access_value = callee_node['value']
            access_target = evaluateAstExpression(access_value['target'])
            member_name = getValidIdentifier(where, access_value['property'])
            if access_target.type == PowangModule.type:
                return lambda: callModuleMember(
                    where, access_target, member_name, call_parameters
                )
        callee_value = evaluateAstExpression(callee_node)
        return lambda: callFunctionValue(
            where, '<expression>', callee_value, call_parameters
        )

    call_callee = getValidIdentifier(where, callee_node)

    ## Local definitions win over imported extern bindings (see _executeCallNode).
    if (match_functions := ScopeStack.get_functions(call_callee)) is not None:
        candidate = getFunctionCandidate(match_functions, call_parameters)
        external = getattr(candidate, 'external', None)
        if external is not None:
            return lambda: callExternalFunction(where, call_callee, candidate, external, call_parameters)
        return lambda: callFunction(where, call_callee, candidate, call_parameters)

    if call_callee in get_state().external_functions:
        function, external = get_state().external_functions[call_callee]
        return lambda: callExternalFunction(
            where, call_callee, function, external, call_parameters
        )

    if call_callee in BUILTINS:
        call_min_argc, call_max_argc, call_func = BUILTINS[call_callee]
        if call_max_argc != -1:
            assert len(call_parameters) <= call_max_argc, powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
        assert len(call_parameters) >= call_min_argc, powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')
        return lambda: call_func(*call_parameters)

    if (call_variable := ScopeStack.get_variable(call_callee)) is not None \
            and call_variable.type == PowangFunction.type:
        return lambda: callFunction(where, call_callee, call_variable, call_parameters)
    raise powang_throw(powang_error_identifier_not_found(where, call_callee))


def getModuleMember(where: str, module: PowangModule, member_name: str):
    member = module.getMember(member_name)
    if member is None:
        raise powang_throw(powang_error_identifier_not_found(where, member_name, [
            f"module '{module.name}' has no exported member '{member_name}'",
        ]))
    return member


def moduleMemberValue(where: str, module: PowangModule, member_name: str) -> PowangAny:
    member = getModuleMember(where, module, member_name)
    if isinstance(member, list):
        ## Exported functions are stored as overload sets. A single overload
        ## behaves like a normal function value; multiple overloads stay
        ## callable through the module, but as a value they form an array.
        if len(member) == 1:
            return member[0]
        return PowangArray(list(member))
    return member


def callModuleMember(
    where: str,
    module: PowangModule,
    member_name: str,
    call_parameters: list[PowangAny],
) -> PowangAny:
    member = getModuleMember(where, module, member_name)
    if isinstance(member, list):
        candidate = getFunctionCandidate(member, call_parameters)
        return callFunctionValue(where, member_name, candidate, call_parameters)
    return callFunctionValue(where, member_name, member, call_parameters)


def bindWildcardImport(where: str, module: PowangModule) -> None:
    for name, member in module.data.items():
        collision_kind: str | None = None
        collision_source: str | None = None

        if ScopeStack.get_functions(name) is not None:
            collision_kind = 'function'
            collision_source = ScopeStack.get_wildcard_source(name)
        elif ScopeStack.get_variable(name) is not None:
            collision_kind = 'variable'
            collision_source = ScopeStack.get_wildcard_source(name)
        elif ScopeStack.get_ObjectType(name) is not None:
            collision_kind = 'type'
            collision_source = ScopeStack.get_wildcard_source(name)

        if collision_kind is not None:
            other_source = (
                f"module '{collision_source}'"
                if collision_source is not None
                else f"an existing {collision_kind} declaration"
            )
            raise powang_throw(powang_error_format(
                'MODULE', where, f"Import collision for '{name}'", [
                    f"imported from module '{module.name}'",
                    f"already provided by {other_source}",
                ]
            ))

        if isinstance(member, list):
            for overload in member:
                ScopeStack.new_function(name, overload)
            ScopeStack.new_wildcard_source(name, module.name)
        elif getattr(member, 'type', None) == PowangObjectType.type:
            ScopeStack.new_ObjectType(name, member)
            ScopeStack.new_wildcard_source(name, module.name)
        else:
            ScopeStack.new_variable(name, member)
            ScopeStack.new_wildcard_source(name, module.name)

def get_extern_module(name: str) -> Any:
    state = get_state()
    if name in state.extern_module_cache:
        return state.extern_module_cache[name]
    import_name = name
    if name == "stdlib_host":
        import_name = "src.stdlib.stdlib_host"
    elif name.startswith("stdlib_"):
        import_name = "src.stdlib." + name
    for path in state.module_search_paths:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    try:
        module = importlib.import_module(import_name)
    except ImportError as error:
        raise powang_throw(powang_error_format('MODULE', "extern", 'Module is not allowed in the extern enviroment', [
            f'module: {name}',
            str(error),
        ]))
    state.extern_module_cache[name] = module
    return module


def type_node_alternatives(type_node: Any) -> list[DictRepr]:
    """Return every alternative of a TYPE node, or the node itself."""
    if not isinstance(type_node, dict):
        return []
    inner = type_node.get('value')
    if isinstance(inner, dict):
        alternatives = inner.get('alternatives')
        if isinstance(alternatives, list) and alternatives:
            return [alternative for alternative in alternatives if isinstance(alternative, dict)]
    return [type_node]


def type_node_inner(type_node: Any) -> dict:
    if not isinstance(type_node, dict):
        return {}
    inner = type_node.get('value')
    return inner if isinstance(inner, dict) else {}


def type_node_is_union(type_node: Any) -> bool:
    inner = type_node_inner(type_node)
    alternatives = inner.get('alternatives')
    return isinstance(alternatives, list) and len(alternatives) > 1


def unwrap_any_value(value: PowangAny) -> PowangAny:
    """Return the concrete payload of a gradual or union `any` value."""
    return PowangUnwrapAny(value)


def value_type_spec(value: PowangAny) -> _typespec.TypeSpec:
    concrete = unwrap_any_value(value)
    if concrete.type == PowangObjectType.type:
        return _typespec.TypeSpec(name=concrete.type_name or PowangObjectType.type)
    if concrete.type == PowangArray.type:
        element_specs = [value_type_spec(item) for item in concrete.data]
        element = _typespec.union(element_specs) if element_specs else _typespec.TypeSpec(name='any')
        return _typespec.TypeSpec(name=PowangArray.type, args=(element,))
    if concrete.type == PowangTuple.type:
        return _typespec.TypeSpec(
            name=PowangTuple.type,
            args=tuple(value_type_spec(item) for item in concrete.data),
        )
    if concrete.type == PowangMap.type:
        key_specs = [value_type_spec(key) for key in concrete.data.keys()]
        value_specs = [value_type_spec(item) for item in concrete.data.values()]
        key_spec = _typespec.union(key_specs) if key_specs else _typespec.TypeSpec(name='any')
        mapped_spec = _typespec.union(value_specs) if value_specs else _typespec.TypeSpec(name='any')
        return _typespec.TypeSpec(name=PowangMap.type, args=(key_spec, mapped_spec))
    if concrete.type == PowangSet.type:
        element_specs = [value_type_spec(item) for item in concrete.data.keys()]
        element = _typespec.union(element_specs) if element_specs else _typespec.TypeSpec(name='any')
        return _typespec.TypeSpec(name=PowangSet.type, args=(element,))
    if concrete.type == PowangAnyType.type:
        return _typespec.TypeSpec(name=concrete.any or PowangAnyType.type)
    return _typespec.TypeSpec(name=concrete.type)


def coerce_value_to_type_node(where: str, value: PowangAny, type_node: Any) -> PowangAny:
    """Apply the implicit construction conversion rules for one value."""
    inner = type_node_inner(type_node)
    if inner.get('auto') or inner.get('value') == 'auto':
        return PowangCopyConstruct(value)
    target = _typespec.from_ast_node(type_node)
    concrete = unwrap_any_value(value)
    source = value_type_spec(concrete)

    if target.name == 'any':
        return PowangCopyConstruct(concrete)

    if target.kind is _typespec.Kind.UNION:
        if not _typespec.assignable(target, source):
            raise powang_throw(powang_error_type_match(
                where,
                _typespec.render(target),
                concrete.type if concrete.type != PowangObjectType.type else concrete.type_name,
            ))
        return PowangCopyConstruct(concrete)

    if target.name == source.name:
        return PowangCopyConstruct(concrete)

    head = _typespec.HEADS.get(target.name)
    if head is not None and head.shape is _typespec.Shape.SCALAR:
        casted = PowangTypeCast(target.name, concrete)
        if casted is not None:
            return PowangCopyConstruct(casted)
        raise powang_throw(powang_error_type_match(
            where,
            _typespec.render(target),
            concrete.type if concrete.type != PowangObjectType.type else concrete.type_name,
        ))

    if head is not None and head.shape in (_typespec.Shape.SEQUENCE, _typespec.Shape.MAPPING):
        casted = explicitCast(target, concrete)
        if casted is not None:
            return PowangCopyConstruct(casted)

    raise powang_throw(powang_error_type_match(
        where,
        _typespec.render(target),
        concrete.type if concrete.type != PowangObjectType.type else concrete.type_name,
    ))


def runtime_type_matches(value: PowangAny, type_node: Any) -> bool:
    """`::` check for a TYPE node, including union alternatives and qualifiers."""
    concrete = unwrap_any_value(value)
    inner = type_node_inner(type_node)
    if inner.get('weak') and (concrete.type == PowangNova.type or not concrete.weak.has_value):
        return True
    outer_const = bool(inner.get('const'))
    for alternative in type_node_alternatives(type_node):
        alt_inner = type_node_inner(alternative)
        name = alt_inner.get('value')
        if not isinstance(name, str):
            continue
        if alt_inner.get('weak'):
            if concrete.type == PowangNova.type or not concrete.weak.has_value:
                return True
        if name == 'auto':
            return True
        if concrete.type == PowangObjectType.type:
            matched = concrete.type_name == name
        elif concrete.type == PowangAnyType.type:
            matched = concrete.any == name
        else:
            matched = concrete.type == name
        if matched and (outer_const or alt_inner.get('const')) and not concrete.const.it_is:
            matched = False
        if matched:
            return True
    return False


def cast_to_union_type(where: str, spec: _typespec.TypeSpec, value: PowangAny) -> PowangAny:
    """Try each union branch in order, including user type constructors."""
    for branch in spec.args:
        head = _typespec.HEADS.get(branch.name)
        if head is None and not branch.nominal:
            if value.type == PowangObjectType.type and value.type_name == branch.name:
                return PowangCopyConstruct(value)
            user_type = ScopeStack.get_ObjectType(branch.name)
            if user_type is not None:
                try:
                    return PowangCopyConstruct(checkObjectTypes(where, user_type, value))
                except PowangError:
                    continue
        try:
            casted = explicitCast(branch, value)
        except PowangError:
            casted = None
        if casted is not None:
            return PowangCopyConstruct(casted)
    raise powang_throw(powang_error_invalid_cast(
        where,
        _typespec.render(spec),
        value.type,
        True,
    ))


def _evaluate_instantiation_arguments(value: DictRepr) -> tuple[list[PowangAny], list[tuple[str, PowangAny]], bool]:
    positional: list[PowangAny] = []
    named: list[tuple[str, PowangAny]] = []
    for argument in value.get('arguments', []):
        if not isinstance(argument, dict):
            continue
        name = argument.get('name')
        argument_value = argument.get('value')
        if isinstance(name, str):
            named.append((name, evaluateAstExpression(argument_value)))
        elif isinstance(argument_value, dict) and argument_value.get('type') == ParserTokenType.KEY_VALUE_PAIR:
            positional.append(argument_value)
        else:
            positional.append(evaluateAstExpression(argument_value))
    return positional, named, bool(value.get('named'))


def _ordered_named_constructor(
    where: str,
    constructors: list[PowangFunction],
    named: list[tuple[str, PowangAny]],
) -> tuple[PowangFunction, list[PowangAny]]:
    if not constructors:
        raise powang_throw(powang_error_format(
            'ARGUMENT', where, "Type has no constructor",
        ))
    provided = {name for name, _ in named}

    def parameter_names(candidate: PowangFunction) -> list[str]:
        return [
            argument['value']['identifier']['value']
            for argument in candidate.args
            if isinstance(argument, dict) and isinstance(argument.get('value'), dict)
        ]

    compatible: list[PowangFunction] = []
    for candidate in constructors:
        names = parameter_names(candidate)
        if not provided.issubset(names):
            continue
        if any(names[index] not in provided for index in range(candidate.min_argc)):
            continue
        compatible.append(candidate)

    if not compatible:
        ## Reuse the shared resolver for the closest signature so the user gets
        ## a precise unknown, duplicate or missing diagnostic.
        closest = max(constructors, key=lambda candidate: len(
            provided.intersection(parameter_names(candidate))
        ))
        resolveNamedArguments(where, closest, [], named)
        raise powang_throw(powang_error_format('ARGUMENT', where, 'Invalid named constructor call'))

    resolved_by_candidate: list[list[PowangAny]] = []
    for candidate in compatible:
        try:
            resolved_by_candidate.append(resolveNamedArguments(where, candidate, [], named))
        except PowangError:
            continue
    if not resolved_by_candidate:
        raise powang_throw(powang_error_format(
            'ARGUMENT', where, 'Invalid named constructor call',
        ))
    candidate = compatible[0]
    resolved = resolved_by_candidate[0]
    if len(compatible) > 1:
        candidate = getFunctionCandidate(compatible, resolved)
        resolved = resolveNamedArguments(where, candidate, [], named)
    return candidate, resolved



def _construct_project(where: str, positional: list[PowangAny], named: list[tuple[str, PowangAny]], named_form: bool) -> PowangAny:
    fields = ["modules", "paths", "logLevel", "allowSystem"]
    values: dict[str, PowangAny | None] = {field: None for field in fields}
    if named_form:
        for name, value in named:
            if name not in values:
                raise powang_throw(powang_error_format(
                    'ARGUMENT', where, f"Project has no field named '{name}'",
                    [f"fields: {', '.join(fields)}"],
                ))
            if values[name] is not None:
                raise powang_throw(powang_error_format(
                    'ARGUMENT', where, f"Duplicate field '{name}'",
                ))
            values[name] = value
    else:
        if len(positional) > len(fields):
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, "Too many Project fields",
                [f"expected at most {len(fields)}"],
            ))
        for index, value in enumerate(positional):
            values[fields[index]] = value

    modules_value = values["modules"]
    paths_value = values["paths"]
    log_level_value = values["logLevel"]
    allow_system_value = values["allowSystem"]

    modules: list[str] = []
    if modules_value is not None:
        concrete = unwrap_any_value(modules_value)
        if concrete.type != PowangArray.type:
            raise powang_throw(powang_error_type_match(where, 'arr[str]', concrete.type))
        for item in concrete.data:
            item = unwrap_any_value(item)
            if item.type != PowangString.type:
                raise powang_throw(powang_error_type_match(where, 'str', item.type))
            modules.append(item.data)

    paths_list: list[str] = []
    if paths_value is not None:
        concrete = unwrap_any_value(paths_value)
        if concrete.type != PowangArray.type:
            raise powang_throw(powang_error_type_match(where, 'arr[str]', concrete.type))
        for item in concrete.data:
            item = unwrap_any_value(item)
            if item.type != PowangString.type:
                raise powang_throw(powang_error_type_match(where, 'str', item.type))
            paths_list.append(item.data)

    log_level = "info"
    if log_level_value is not None:
        concrete = unwrap_any_value(log_level_value)
        if concrete.type != PowangString.type:
            raise powang_throw(powang_error_type_match(where, 'str', concrete.type))
        log_level = concrete.data

    allow_system = False
    if allow_system_value is not None:
        concrete = unwrap_any_value(allow_system_value)
        if concrete.type != PowangBoolean.type:
            raise powang_throw(powang_error_type_match(where, 'bool', concrete.type))
        allow_system = concrete.data

    return PowangProject(modules, paths_list, log_level, allow_system)


def evaluate_instantiation(where: str, value: DictRepr) -> PowangAny:
    type_reference = value.get('type_ref')
    if not isinstance(type_reference, dict):
        raise powang_throw(powang_error_syntax(where, "Invalid instantiation node"))
    type_name = type_reference.get('name')
    if not isinstance(type_name, str):
        raise powang_throw(powang_error_syntax(where, "Instantiation requires a type name"))
    type_parameters = [
        parameter for parameter in type_reference.get('type_parameters', [])
        if isinstance(parameter, dict)
    ]
    variadic = bool(type_reference.get('variadic'))

    positional, named, named_form = _evaluate_instantiation_arguments(value)

    type_alias = get_state().type_alias
    if type_name in type_alias:
        alias = type_alias[type_name]
        if isinstance(alias, dict) and alias.get('alternatives'):
            raise powang_throw(powang_error_format(
                'TYPE', where, f"Cannot construct union alias '{type_name}'",
            ))
        if isinstance(alias, dict):
            alias_element = alias.get('element_type')
            alias_generics = alias.get('generics') or []
            if not type_parameters and alias.get('value') == PowangArray.type and alias_element is not None:
                type_parameters = [alias_element]
            elif not type_parameters and alias_generics:
                type_parameters = list(alias_generics)
                variadic = bool(alias.get('variadic'))
            type_name = alias.get('value', type_name)
        else:
            type_name = alias

    if type_name == 'Project':
        return _construct_project(where, positional, named, named_form)

    if type_name in NATI_TYPES:
        if named_form:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, "Named arguments are only supported for user type constructors",
            ))
        if type_name == PowangMap.type:
            result = PowangMap()
            for argument in positional:
                if not isinstance(argument, dict) or argument.get('type') != ParserTokenType.KEY_VALUE_PAIR:
                    raise powang_throw(powang_error_format(
                        'TYPE', where, "map construction requires key >> value entries",
                    ))
                pair = argument['value']
                key_value = evaluateAstExpression(pair['key'])
                entry_value = evaluateAstExpression(pair['value'])
                result.data[key_value] = entry_value
            return result

        if type_name in {PowangArray.type, PowangTuple.type, PowangSet.type}:
            if type_name == PowangSet.type:
                if type_parameters:
                    if len(type_parameters) != 1:
                        raise powang_throw(powang_error_format(
                            'TYPE', where, "set construction expects exactly one element type",
                        ))
                    positional = [
                        coerce_value_to_type_node(where, item, type_parameters[0])
                        for item in positional
                    ]
                return PowangSet(positional)
            if type_parameters:
                if type_name == PowangArray.type:
                    if len(type_parameters) != 1:
                        raise powang_throw(powang_error_format(
                            'TYPE', where, "arr construction expects exactly one element type",
                        ))
                    element_specs = [type_parameters[0]] * len(positional)
                else:
                    if variadic:
                        if len(positional) < len(type_parameters):
                            raise powang_throw(powang_error_format(
                                'TYPE', where, "tuple construction arity does not match its type",
                                [
                                    f"type declares at least {len(type_parameters)} elements",
                                    f"but {len(positional)} were given",
                                ],
                            ))
                        if type_parameters:
                            element_specs = (
                                type_parameters[:-1]
                                + [type_parameters[-1]] * (len(positional) - len(type_parameters) + 1)
                            )
                        else:
                            element_specs = [None] * len(positional)
                    else:
                        if len(type_parameters) != len(positional):
                            raise powang_throw(powang_error_format(
                                'TYPE', where, "tuple construction arity does not match its type",
                                [
                                    f"type declares {len(type_parameters)} elements",
                                    f"but {len(positional)} were given",
                                ],
                            ))
                        element_specs = type_parameters
                positional = [
                    coerce_value_to_type_node(where, item, spec) if spec is not None else PowangCopyConstruct(item)
                    for item, spec in zip(positional, element_specs)
                ]
            if type_name == PowangArray.type:
                return PowangArray(positional)
            return PowangTuple(positional)

        if type_name == PowangNova.type:
            if positional:
                raise powang_throw(powang_error_format(
                    'TYPE', where, "nova construction takes no arguments",
                ))
            return PowangNova()

        if len(positional) != 1:
            raise powang_throw(powang_error_format(
                'TYPE', where, f"{type_name} construction takes exactly one argument",
                [f"but {len(positional)} were given"],
            ))
        casted = explicitCast(type_name, positional[0])
        if casted is None:
            raise powang_throw(powang_error_invalid_cast(
                where, type_name, positional[0].type, True,
            ))
        return casted

    user_type = ScopeStack.get_ObjectType(type_name)
    if user_type is None:
        raise powang_throw(powang_error_identifier_type(where, type_name))
    instance_type = ScopeStack.get_existingObjectType(type_name)
    constructors = instance_type.getConstructors()
    if named_form:
        if positional:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, "Named and positional arguments cannot be mixed",
            ))
        candidate, arguments = _ordered_named_constructor(where, constructors, named)
    else:
        if not constructors:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, f"Type '{type_name}' has no constructor",
            ))
        candidate = getFunctionCandidate(constructors, positional)
        arguments = positional
    return callMethod(where, instance_type, CONSTRUCTOR_METHOD_NAME, candidate, arguments)


## Evaluation depth guard. Recursive Powang calls would otherwise surface as a
## raw Python RecursionError. The counter is per execution context (thread) and
## reset per run (and therefore per REPL line, since each line is a run). It
## always unwinds through `finally`.
MAX_EVALUATION_DEPTH: int = 900
_evaluation_depth: ContextVar[int] = ContextVar("powang_evaluation_depth", default=0)


def reset_evaluation_depth():
    _evaluation_depth.set(0)


def evaluateAstExpression(expression: DictRepr, is_identifier: bool = False) -> PowangAny:
    depth_token = _evaluation_depth.set(_evaluation_depth.get() + 1)
    try:
        current_depth = _evaluation_depth.get()
        if current_depth > MAX_EVALUATION_DEPTH:
            raise PowangError('RECURSION', 'Maximum evaluation depth exceeded', [
                f"depth limit: {MAX_EVALUATION_DEPTH}",
                "check for unbounded or deeply nested recursion",
            ])
        return _evaluateAstExpression(expression, is_identifier)
    except RecursionError as e:
        import traceback
        traceback.print_exc()
        raise PowangError('RECURSION', 'Python recursion limit reached', [
            f"depth: {_evaluation_depth.get()}",
            "check for unbounded or deeply nested recursion",
        ]) from None
    finally:
        _evaluation_depth.reset(depth_token)


def _evaluateAstExpression(expression: DictRepr, is_identifier: bool = False) -> PowangAny:
    if expression == {}:
        return PowangNova()

    where = TokenToString(expression['type'])
    expr_value = expression['value']
    match expression['type']:
        case LexerTokenType.IDENTIFIER:
            if expr_value == 'nova':
                return PowangNova()
            if expr_value in {'true', 'false'}:
                return PowangBoolean(expr_value == 'true')
            if expr_value == str('this'):
                if len(ScopeStack.method_call_stack) > 0:
                    this = ScopeStack.method_call_stack[-1]
                    return this
            if is_identifier:
                return expr_value
            if (identifier_value := ScopeStack.get_variable(expr_value)) is not None:
                ## Reading a reference parameter yields the live target value.
                if identifier_value.type == PowangReference.type:
                    return identifier_value.get()
                return identifier_value
            ## functions live on their own stack, fall back to them so
            ## function values can be referenced and inferred with :=
            if (identifier_functions := ScopeStack.get_functions(expr_value)) is not None:
                return identifier_functions[-1]
            assert False, powang_error_identifier_not_found(None, expr_value)
            return PowangNova()

        case LexerTokenType.INTEGER_LITERAL:
            return PowangInteger(int(expr_value))

        case LexerTokenType.FLOATING_LITERAL:
            return PowangNumber(float(expr_value))

        case LexerTokenType.STRING_LITERAL:
            return PowangString(expr_value)

        case ParserTokenType.INTERPOLATED_STRING:
            pieces: list[str] = []
            parts = expr_value.get('parts', []) if isinstance(expr_value, dict) else []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if part.get('kind') == 'text':
                    pieces.append(str(part.get('value', '')))
                    continue
                part_value = evaluateAstExpression(part.get('value'))
                casted = explicitCastString(part_value)
                if casted is None and part_value.type == PowangObjectType.type:
                    casted = PowangString(f"<type: {part_value.type_name}>")
                if casted is not None:
                    pieces.append(casted.data)
            return PowangString(''.join(pieces))

        case ParserTokenType.REFERENCE_EXPRESSION:
            target_node = expr_value['target']
            target_name = getValidIdentifier(where, target_node)
            slot = ScopeStack.find_variable_slot(target_name)
            if slot is None:
                raise powang_throw(powang_error_identifier_not_found(where, target_name))
            owner_scope, bound_value = slot
            if bound_value.type == PowangReference.type:
                raise powang_throw(powang_error_format(
                    'REFERENCE', where, "Cannot take a reference to a reference", [
                        f"'{target_name}' already holds a reference",
                    ]))
            if bool(bound_value.const):
                raise powang_throw(powang_error_format(
                    'REFERENCE', where, "Cannot take a reference to a constant", [
                        f"'{target_name}' is constant",
                        "references mutate the target, so the target must be assignable",
                    ]))
            return PowangReference(owner_scope, target_name, bound_value.type)

        case ParserTokenType.UNARY_EXPRESSION:
            unary_operator = expr_value['operator']['value']
            unary_right = evaluateAstExpression(expr_value['right'])

            match unary_operator:
                case '!':
                    return PowangBoolean(not PowangBoolean.cast(unary_right).data)
                case '[-]':
                    if unary_right.type == PowangInteger.type:
                        return explicitCastInteger(PowangString(explicitCastString(unary_right).data[::-1])) # type: ignore
                    if unary_right.type == PowangNumber.type:
                        return explicitCastNumber(PowangString(explicitCastString(unary_right).data[::-1])) # type: ignore
                    if unary_right.type == PowangString.type:
                        return PowangString(unary_right.data[::-1])
                    if unary_right.type == PowangArray.type:
                        return PowangArray(unary_right.data[::-1])
                case '-':
                    if unary_right.type == PowangInteger.type:
                        return PowangInteger(-unary_right.data)
                    if unary_right.type == PowangNumber.type:
                        return PowangNumber(-unary_right.data)
                    else:
                        powang_throw(powang_error_invalid_type_for_prefix_operator(None, unary_operator, unary_right.type))

        case ParserTokenType.BINARY_EXPRESSION:
            binary_operator = expr_value['operator']['value']
            binary_left = evaluateAstExpression(expr_value['left'])
            if binary_operator in {'::', '!:'}:
                type_condition: bool = True
                right_node = expr_value['right']
                right_node_type = right_node.get('type') if isinstance(right_node, dict) else None
                if right_node_type == ParserTokenType.TYPE:
                    type_condition = runtime_type_matches(binary_left, right_node)
                elif right_node_type == LexerTokenType.IDENTIFIER:
                    type_condition = right_node['value'] == (
                        binary_left.type_name if binary_left.type != PowangAnyType.type else binary_left.any
                    )
                else:
                    binary_right = evaluateAstExpression(right_node)
                    if binary_right.weak:
                        type_condition = type_condition and binary_left.weak.it_is
                    if binary_right.const:
                        type_condition = type_condition and binary_left.const.it_is

                if binary_operator == '::':
                    return PowangBoolean(type_condition)
                return PowangBoolean(not type_condition)

            if binary_operator == 'as':
                from . import typespec as _ts
                target_spec = _ts.from_ast_expr(expr_value['right'])
                binary_right = getCastTypeName(where, expr_value['right'])
                if binary_left.type == PowangAnyType.type:
                    binary_left = PowangUnwrapAny(binary_left)

                if target_spec.kind is _ts.Kind.UNION:
                    union_casted = cast_to_union_type(where, target_spec, binary_left)
                    return PowangCopyConstruct(union_casted)

                if binary_right in get_state().type_alias:
                    binary_right = get_state().type_alias[binary_right]['value']
                if binary_right not in NATI_TYPES and not target_spec.nominal:
                    user_type = ScopeStack.get_ObjectType(binary_right)
                    if user_type is None:
                        raise powang_throw(powang_error_identifier_type(where, binary_right))
                    check_result = checkObjectTypes(where, user_type, binary_left)
                    return check_result

                # EXPLICIT CASTING
                binary_casted = explicitCast(target_spec, binary_left)
                if binary_casted is None:
                    raise powang_throw(powang_error_invalid_cast(
                        None,
                        binary_right,
                        binary_left.type,
                        True,
                    ))
                binary_value = PowangCopyConstruct(binary_casted)
                return binary_value

            if binary_operator == ':>':
                right_node = expr_value['right']
                if isinstance(right_node, dict) and right_node.get('type') == ParserTokenType.CALL_EXPRESSION:
                    call_value = right_node['value']
                    pipeline_parameters = [binary_left] + [
                        evaluateAstExpression(argument)
                        for argument in call_value.get('arguments', [])
                    ]
                    return _executeCallNode(where, call_value['callee'], pipeline_parameters)
                if isinstance(right_node, dict) and right_node.get('type') == ParserTokenType.METHOD_CALL:
                    method_value = right_node['value']
                    owner_node = method_value.get('owner')
                    if isinstance(owner_node, dict) and \
                            owner_node.get('type') == LexerTokenType.IDENTIFIER and \
                            owner_node.get('value') in NATIVE_METHOD_TYPES:
                        pipeline_parameters = [binary_left] + [
                            evaluateAstExpression(argument)
                            for argument in method_value.get('arguments', [])
                        ]
                        return call_native_method(
                            where,
                            owner_node['value'],
                            method_value['method']['value'],
                            pipeline_parameters,
                        )
                    owner_value = evaluateAstExpression(method_value['owner'])
                    pipeline_parameters = [binary_left] + [
                        evaluateAstExpression(argument)
                        for argument in method_value.get('arguments', [])
                    ]
                    if owner_value.type == PowangModule.type:
                        return callModuleMember(where, owner_value, method_value['method']['value'], pipeline_parameters)
                    assert owner_value.type == PowangObjectType.type, powang_error_format('IMPLEMENTATION', where,
                        "Currently only user types can perform a method call.", [
                            f"but trying to call from a {owner_value.type}"
                        ])
                    match_methods = owner_value.getMethods(method_value['method']['value'], len(ScopeStack.method_call_stack) > 0)
                    if match_methods is None:
                        raise powang_throw(powang_error_identifier_not_found(
                            where, f"method: {method_value['method']['value']}", [
                                "perhaps is a private method?"
                            ]))
                    method_candidate = getFunctionCandidate(match_methods, pipeline_parameters)
                    return callMethod(
                        where,
                        owner_value,
                        method_value['method']['value'],
                        method_candidate,
                        pipeline_parameters,
                    )
                if isinstance(right_node, dict) and right_node.get('type') == ParserTokenType.ACCESS_EXPRESSION:
                    access_value = right_node.get('value')
                    access_target = access_value.get('target') if isinstance(access_value, dict) else None
                    if isinstance(access_target, dict) and \
                            access_target.get('type') == LexerTokenType.IDENTIFIER and \
                            access_target.get('value') in NATIVE_METHOD_TYPES:
                        member = access_value.get('property')
                        method_name = member.get('value') if isinstance(member, dict) else None
                        if isinstance(method_name, str):
                            return call_native_method(
                                where,
                                access_target['value'],
                                method_name,
                                [binary_left],
                            )
                pipeline_callable = evaluateAstExpression(right_node)
                return callFunctionValue(where, '<pipeline>', pipeline_callable, [binary_left])

            binary_right = evaluateAstExpression(expr_value['right'])
            if binary_operator == '??':
                if binary_left.type == PowangNova.type or not binary_left.weak.has_value:
                    return binary_right
                return binary_left
            if binary_operator in {'&&', '||'}:
                if binary_operator == '&&':
                    if not PowangBoolean.cast(binary_left).data:
                        return PowangBoolean(False)
                    return PowangBoolean.cast(binary_right)
                if PowangBoolean.cast(binary_left).data:
                    return PowangBoolean(True)
                return PowangBoolean.cast(binary_right)

            return performOperation(binary_operator, binary_left, binary_right, expr_value['typed'])

        case ParserTokenType.DECLARATION_UNDEFINED:
            undefined_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert undefined_identifier not in ScopeStack.variables[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {undefined_identifier}"
            ])
            undefined_variable = getUndefinedVariable(where, expr_value['type']['value'])
            ScopeStack.new_variable(expr_value['identifier']['value'], undefined_variable)
            return undefined_variable

        case ParserTokenType.DECLARATION_TYPED_VAR:
            typed_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert typed_identifier not in ScopeStack.variables[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {typed_identifier}"
            ])
            undefined_value = getUndefinedVariable(where, expr_value['type']['value'])
            right_value = evaluateAstExpression(expr_value['expression'])
            typed_variable = assignWithChecks(where, undefined_value, right_value, False)
            ScopeStack.new_variable(expr_value['identifier']['value'], typed_variable)
            return typed_variable

        case ParserTokenType.DESTRUCTURE_DECLARATION:
            return _evaluateDestructureDeclaration(where, expr_value)

        case ParserTokenType.DECLARATION_INTERPRET:
            typed_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert typed_identifier not in ScopeStack.variables[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {typed_identifier}"
            ])
            right_value = evaluateAstExpression(expr_value['expression'])
            if right_value.type in {
                PowangFunction.type,
                PowangFileStream.type,
                PowangModule.type,
                PowangTask.type,
            }:
                ## function, file, module and task values can't be default
                ## constructed nor copied, bind them directly, the same way
                ## identifiers resolve to them
                interpret_variable = right_value
            elif right_value.type == PowangObjectType.type \
                    and ScopeStack.get_ObjectType(right_value.type_name) is None:
                ## The value came from another module: its type template is not
                ## visible here, but the instance itself carries enough state
                ## to be copied safely.
                interpret_variable = PowangCopyConstruct(right_value)
            else:
                interpret_variable = getUndefinedVariable(where, {
                    "weak" : right_value.weak.it_is,
                    "const": right_value.const.it_is,
                    "value" : {
                        PowangAnyType.type: right_value.any,
                        PowangObjectType.type: right_value.type_name
                    }.get(right_value.type, right_value.type),
                })

                assignWithChecks(where, interpret_variable, right_value, False)
            ScopeStack.new_variable(expr_value['identifier']['value'], interpret_variable)
            return interpret_variable

        case ParserTokenType.ASSIGNMENT:
            ## NOTE: compound assignments (`+=`, `-=`...) are parsed as `target = target op value`
            ## sharing the same AST node for both occurrences, so the target expression is
            ## evaluated twice. Avoiding that requires an lvalue/reference redesign.
            assign_target = expr_value['target']

            if assign_target['type'] == ParserTokenType.ACCESS_EXPRESSION:
                access_owner = evaluateAstExpression(assign_target['value']['target'])
                access_owner = unwrap_any_value(access_owner)
                if access_owner.type == PowangModule.type:
                    member_name = getValidIdentifier(where, assign_target['value']['property'])
                    raise powang_throw(powang_error_format(
                        'MODULE', where, "Modules are immutable", [
                            f"cannot assign to '{access_owner.name}.{member_name}'",
                        ]
                    ))
                if getattr(access_owner, 'structure_locked', False):
                    raise powang_throw(powang_error_format(
                        'CONST', where, "object fields are locked",
                        ["the type annotation ends with '!'"],
                    ))
                assign_target_value = evaluateAstExpression(assign_target)
            elif assign_target['type'] == ParserTokenType.INDEX_EXPRESSION:
                index_expression = assign_target['value']
                container = unwrap_any_value(evaluateAstExpression(index_expression['target']))
                index = evaluateAstExpression(index_expression['index'])
                if container.type == PowangMap.type:
                    assign_value = evaluateAstExpression(expr_value['expression'])
                    if index in container.data:
                        if getattr(container, 'elements_locked', False):
                            raise powang_throw(powang_error_format(
                                'CONST', where, "map values are locked",
                                ["the value type ends with '!'"],
                            ))
                    elif getattr(container, 'structure_locked', False):
                        raise powang_throw(powang_error_format(
                            'CONST', where, "map structure is locked",
                            ["the map type ends with '!'"],
                        ))
                    container.data[index] = copy_for_task(assign_value)
                    return assign_value
                if container.type == PowangArray.type:
                    if getattr(container, 'elements_locked', False):
                        raise powang_throw(powang_error_format(
                            'CONST', where, "array elements are locked",
                            ["the element type ends with '!'"],
                        ))
                    assign_target_value = container.index(index)
                    assign_value = evaluateAstExpression(expr_value['expression'])
                    return assignWithChecks(where, assign_target_value, assign_value, False)
                if container.type == PowangTuple.type:
                    raise powang_throw(powang_error_format(
                        'CONST', where, "tuples are immutable",
                    ))
                assign_target_value = getIndexedValue(where, index_expression, True)
            else:
                assign_target = getValidIdentifier(where, assign_target)
                assign_target_value = ScopeStack.get_variable(assign_target)
                if assign_target_value is None:
                    raise powang_throw(powang_error_identifier_not_found(
                        where,
                        assign_target,
                    ))

            assign_value = evaluateAstExpression(expr_value['expression'])
            ## Assignment through a reference parameter writes to the caller's
            ## variable instead of rebinding the local parameter name.
            if isinstance(assign_target, str) and assign_target_value.type == PowangReference.type:
                referenced_value = assign_target_value.get()
                assigned = assignWithChecks(where, referenced_value, assign_value, False)
                assign_target_value.set(assigned)
                return assigned
            return assignWithChecks(where, assign_target_value, assign_value, False)

        case ParserTokenType.INSTANTIATION:
            return evaluate_instantiation(where, expr_value)

        case ParserTokenType.ARRAY_EXPRESSION:
            array_expr_elements = expr_value['elements']
            if expr_value['type'] == PowangMap.type:
                return PowangMap({
                    evaluateAstExpression(key_value['value']['key']):
                    evaluateAstExpression(key_value['value']['value'])
                    for key_value in array_expr_elements
                })
            array_elements: list = [evaluateAstExpression(array_item) for array_item in array_expr_elements]
            return PowangArray(array_elements)

        case ParserTokenType.TUPLE_EXPRESSION:
            tuple_elements: list = [evaluateAstExpression(item) for item in expr_value['elements']]
            return PowangTuple(tuple_elements)

        case ParserTokenType.INDEX_EXPRESSION:
            index_expression_value = getIndexedValue(where, expression['value'], False)
            assert index_expression_value is not None, powang_error_format(
                'IMPLEMENTATION', where, "Index to that type is not implemented yet."
            )
            return index_expression_value

        case ParserTokenType.POSTFIX_UNWRAP:
            ## `expr?` propagates an error value by returning it from the
            ## current function. The enclosing block sees `return_value` set
            ## and unwinds exactly like a `return` statement.
            current_scope_type = ScopeStack.current_scope_type()
            assert current_scope_type == ScopeType.FUNCTION, powang_error_format(
                'LOGIC', where,
                "Trying to use the '?' operator outside a function scope", [
                    f"the scope you are trying to unwrap from it's {ScopeType.toStr(current_scope_type)}"
                ]
            )
            unwrap_value = evaluateAstExpression(expr_value['expression'])
            if unwrap_value.type == PowangAnyType.type:
                unwrap_value = PowangUnwrapAny(unwrap_value)
            if unwrap_value.type == PowangErrorValue.type:
                ScopeStack.return_value = PowangCopyConstruct(unwrap_value)
                return ScopeStack.return_value
            return unwrap_value

        case ParserTokenType.CALL_EXPRESSION:
            call_callee_node = expr_value['callee']
            call_parameters: list[PowangAny] = []
            named_arguments: list[tuple[str, PowangAny]] = []
            for call_arg in expr_value['arguments']:
                if isinstance(call_arg, dict) and call_arg.get('type') == ParserTokenType.NAMED_ARGUMENT:
                    named_value = call_arg.get('value')
                    if isinstance(named_value, dict):
                        name_node = named_value.get('name')
                        name = name_node.get('value') if isinstance(name_node, dict) else None
                        if isinstance(name, str):
                            named_arguments.append((name, evaluateAstExpression(named_value.get('value'))))
                    continue
                call_parameters.append(evaluateAstExpression(call_arg))
            return _executeCallNode(where, call_callee_node, call_parameters, named_arguments)

        case ParserTokenType.SPAWN_EXPRESSION:
            ## Arguments are evaluated on the parent thread, then copied so
            ## the task cannot share mutable storage with the parent. The
            ## callable is resolved here as well; only its execution moves to
            ## the worker.
            spawn_call = expr_value['call']['value']
            parent_parameters = [
                evaluateAstExpression(spawn_arg)
                for spawn_arg in spawn_call['arguments']
            ]
            task_parameters = [copy_for_task(parameter) for parameter in parent_parameters]
            task_work = _prepareTaskCall(where, spawn_call['callee'], task_parameters)

            parent_state = get_state()
            ## Create the pool before cloning so the clone shares it and an
            ## outer run can join tasks spawned from inside tasks.
            pool = get_task_pool(parent_state)
            task_state = parent_state.clone_for_task()
            try:
                return spawn_task(task_state, task_work, pool)
            except BaseException:
                task_state.close()
                raise

        case ParserTokenType.MATCH_STATEMENT:
            match_subject = unwrap_any_value(evaluateAstExpression(expr_value['subject']))
            for match_case in expr_value.get('cases', []):
                if not isinstance(match_case, dict):
                    continue
                ScopeStack.push()
                try:
                    pattern = match_case.get('pattern')
                    if not isinstance(pattern, dict):
                        pattern = {}
                    kind = pattern.get('kind')
                    matched = False
                    if kind == 'wildcard':
                        matched = True
                    elif kind == 'literal':
                        pattern_value = evaluateAstExpression(pattern.get('value'))
                        matched = match_subject.type == pattern_value.type and match_subject == pattern_value
                    elif kind == 'binding':
                        name = pattern['value']['value']
                        ScopeStack.new_variable(name, PowangCopyConstruct(match_subject))
                        matched = True
                    guard = match_case.get('guard')
                    if matched and guard is not None:
                        matched = PowangBoolean.cast(evaluateAstExpression(guard)).data
                    if matched:
                        for match_statement in match_case['block']['value']:
                            check_cancellation()
                            evaluateAstExpression(match_statement)
                            if ScopeStack.return_value is not None:
                                break
                        break
                finally:
                    ScopeStack.pop()

        case ParserTokenType.MATCH_EXPRESSION:
            match_subject = unwrap_any_value(evaluateAstExpression(expr_value['subject']))
            match_result: PowangAny = PowangNova()
            for match_case in expr_value.get('cases', []):
                if not isinstance(match_case, dict):
                    continue
                ScopeStack.push()
                try:
                    pattern = match_case.get('pattern')
                    if not isinstance(pattern, dict):
                        pattern = {}
                    kind = pattern.get('kind')
                    matched = False
                    if kind == 'wildcard':
                        matched = True
                    elif kind == 'literal':
                        pattern_value = evaluateAstExpression(pattern.get('value'))
                        matched = match_subject.type == pattern_value.type and match_subject == pattern_value
                    elif kind == 'binding':
                        name = pattern['value']['value']
                        ScopeStack.new_variable(name, PowangCopyConstruct(match_subject))
                        matched = True
                    guard = match_case.get('guard')
                    if matched and guard is not None:
                        matched = PowangBoolean.cast(evaluateAstExpression(guard)).data
                    if matched:
                        if match_case.get('is_expression'):
                            match_result = evaluateAstExpression(match_case.get('value'))
                        else:
                            block = match_case.get('block')
                            if isinstance(block, dict) and block.get('value') is not None:
                                for match_statement in block['value']:
                                    check_cancellation()
                                    evaluateAstExpression(match_statement)
                                    if ScopeStack.return_value is not None:
                                        match_result = ScopeStack.return_value
                                        ScopeStack.return_value = None
                                        break
                        break
                finally:
                    ScopeStack.pop()
            return match_result

        case ParserTokenType.IF_STATEMENT:
            if_expr = expr_value['expression']
            if_block = expr_value['block']
            if_else_block = expr_value['else']

            condition_true = False
            ScopeStack.push()
            try:
                condition_true = PowangBoolean.cast(evaluateAstExpression(if_expr)).data
                if condition_true:
                    for if_statement in if_block['value']:
                        check_cancellation()
                        evaluateAstExpression(if_statement)
                        if ScopeStack.return_value is not None:
                            break
            finally:
                ScopeStack.pop()

            if not condition_true and if_else_block is not None:
                ScopeStack.push()
                try:
                    for if_statement in if_else_block['value']:
                        check_cancellation()
                        evaluateAstExpression(if_statement)
                        if ScopeStack.return_value is not None:
                            break
                finally:
                    ScopeStack.pop()

        case ParserTokenType.TRY_STATEMENT:
            try_block = expr_value['block']
            try_catches = expr_value['catches']
            try_finally = expr_value['finally_block']

            def run_try_block(block):
                ScopeStack.push()
                try:
                    for try_statement in block['value']:
                        check_cancellation()
                        evaluateAstExpression(try_statement)
                        if ScopeStack.return_value is not None:
                            break
                finally:
                    ScopeStack.pop()

            pending_error: PowangError | None = None
            finally_took_return: bool = False
            try:
                run_try_block(try_block)
            except AssertionError as raw_error:
                ## Only language errors are catchable. A bare Python
                ## AssertionError is an internal invariant and must propagate.
                converted_error = powang_error_from_exception(raw_error)
                if converted_error is None:
                    raise
                pending_error = converted_error
                for try_catch in try_catches:
                    ScopeStack.push()
                    try:
                        if try_catch['name'] is not None:
                            ScopeStack.new_variable(
                                try_catch['name']['value'],
                                PowangErrorValue.from_error(pending_error),
                            )
                        for catch_statement in try_catch['block']['value']:
                            check_cancellation()
                            evaluateAstExpression(catch_statement)
                            if ScopeStack.return_value is not None:
                                break
                    finally:
                        ScopeStack.pop()
                    pending_error = None
                    break
            finally:
                if try_finally is not None:
                    ## The finally block always runs, including when a return
                    ## is already pending. A return inside finally overrides
                    ## the earlier one; an exception inside finally discards
                    ## the pending return.
                    pending_return = ScopeStack.return_value
                    ScopeStack.return_value = None
                    try:
                        ScopeStack.push()
                        try:
                            for finally_statement in try_finally['value']:
                                check_cancellation()
                                evaluateAstExpression(finally_statement)
                                if ScopeStack.return_value is not None:
                                    break
                        finally:
                            ScopeStack.pop()
                    except BaseException:
                        ScopeStack.return_value = None
                        raise
                    else:
                        if ScopeStack.return_value is not None:
                            ## A return inside finally wins over a pending
                            ## return and, as in Python and JavaScript,
                            ## suppresses a pending error as well.
                            finally_took_return = True
                        else:
                            ScopeStack.return_value = pending_return
            if pending_error is not None and not finally_took_return:
                raise pending_error

        case ParserTokenType.FOR_STATEMENT:
            for_start_expression = expr_value['start_expression']
            for_middle_expression = expr_value['middle_expression']
            for_last_expression = expr_value['last_expression']
            for_block = expr_value['block']

            if for_middle_expression is None:
                for_middle_expression = for_start_expression
                for_start_expression = None

            ScopeStack.push() # init statement scope, lives for the whole loop
            try:
                if for_start_expression is not None:
                    evaluateAstExpression(for_start_expression)

                running: bool = True
                while PowangBoolean.cast(evaluateAstExpression(for_middle_expression)).data:
                    check_cancellation()
                    ScopeStack.push()
                    try:
                        for statement in for_block['value']:
                            check_cancellation()
                            evaluateAstExpression(statement)
                            if ScopeStack.return_value is not None:
                                running = False
                                break
                    finally:
                        ScopeStack.pop()

                    if not running:
                        break
                    if for_last_expression is not None:
                        evaluateAstExpression(for_last_expression)
            finally:
                ScopeStack.pop()

        case ParserTokenType.FOR_EACH_STATEMENT:
            for_each_iterable_expression = expr_value['expression']

            ScopeStack.push()
            try:
                for_each_iterable = unwrap_any_value(evaluateAstExpression(for_each_iterable_expression))
                assert for_each_iterable.type in {PowangArray.type, PowangString.type, PowangMap.type, PowangSet.type}, powang_error_format("VALUE", where, "Expression is not an iterable value", [
                    f"Expression is of type {for_each_iterable.type}"
                ])

                for_each_iterator_expression = expr_value['iterator']

                for_each_block = expr_value['block']

                running: bool = True
                for current_item in for_each_iterable.iterate().data:
                    if not running:
                        break
                    check_cancellation()

                    # One scope per iteration holding BOTH the iterator
                    # binding and the body, otherwise the body cannot see
                    # the iterator variable.
                    ScopeStack.push()
                    try:
                        iterator = evaluateAstExpression(for_each_iterator_expression)
                        assignWithChecks('for each', iterator, current_item, False)
                        if expr_value['if_expression'] is not None and \
                                not evaluateAstExpression(expr_value['if_expression']).data:
                            continue

                        for for_each_statement in for_each_block['value']:
                            check_cancellation()
                            evaluateAstExpression(for_each_statement)
                            if ScopeStack.return_value is not None:
                                running = False
                                break
                    finally:
                        ScopeStack.pop()
            finally:
                ScopeStack.pop()

        case ParserTokenType.DECLARATION_FUN:
            fun_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert fun_identifier not in NATI_TYPES, powang_error_identifier_names_type(where, fun_identifier)
            functions: list[PowangFunction] | None = ScopeStack.get_functions(fun_identifier)
            if functions is not None:
                for func in functions:
                    if len(func.args) != len(expr_value['args']):
                        continue

                    is_different: bool = False
                    for found_arg, new_arg in zip(func.args, expr_value['args']):
                        if found_arg['value']['type']['value']['value'] != new_arg['value']['type']['value']['value']:
                            is_different = True
                            break

                        if found_arg['value']['type']['value']['weak'] != new_arg['value']['type']['value']['weak']:
                            is_different = True
                            break

                    assert is_different, powang_error_redefined(where, fun_identifier, [
                        f"remember, type qualifiers such as const does not determine function signatures, same with return types"
                    ])

            ## Synthesize the default return type locally; never write back
            ## into the AST node (the interpreter must not mutate the tree).
            return_type = expr_value['return']
            if return_type is None:
                return_type = doToken(ParserTokenType.TYPE, {
                    'value': PowangNova.type,
                    'const': False,
                    'weak': False,
                    'reference': None,
                }).toDict()

            new_function = PowangFunction(
                expr_value['args'],
                expr_value['block']['value'],
                return_type['value']
            )
            new_function.min_argc = expr_value['min_argc']
            return ScopeStack.new_function(fun_identifier, new_function)

        case ParserTokenType.RETURN_EXPRESSION:
            current_scope_type = ScopeStack.current_scope_type()
            assert current_scope_type == ScopeType.FUNCTION, powang_error_format('LOGIC', None, "Trying to return with a non function scope", [
                f"the scope you are trying to return from it's {ScopeType.toStr(current_scope_type)}"
            ])

            return_expr_value = evaluateAstExpression(expr_value)
            if return_expr_value.type == PowangAnyType.type:
                return_expr_value = PowangUnwrapAny(return_expr_value)
            ScopeStack.return_value = PowangCopyConstruct(return_expr_value)

        case ParserTokenType.MODULE_DECLARATION:
            return PowangNova()

        case ParserTokenType.TYPE_DECLARATION:
            identifier = getValidIdentifier(where, expr_value['identifier'])
            
            ## Enum declaration: a finite set of named constant instances.
            if expr_value.get('is_enum'):
                get_state().user_types.add(identifier)
                variant_names: list[str] = expr_value.get('variants') or []
                # Build the enum type with a `name` property (string).
                enum_type = PowangObjectType(
                    {'name': PowangString(variant_names[0] if variant_names else '')},
                    {},
                    {},
                    {},
                )
                enum_type.type_name = identifier
                enum_type.is_enum = True
                ScopeStack.new_ObjectType(identifier, enum_type)
                
                # Create variant instances and store them in a map.
                variants_map: dict[PowangAny, PowangAny] = {}
                for variant_name in variant_names:
                    instance = PowangObjectType(
                        {'name': PowangString(variant_name)},
                        {},
                        {},
                        {},
                    )
                    instance.type_name = identifier
                    instance.is_enum = True
                    instance.defined = True
                    variants_map[PowangString(variant_name)] = instance
                enum_value = PowangMap(variants_map)
                ScopeStack.new_variable(identifier, enum_value)
                get_state().user_types.discard(identifier)
                return enum_value
            
            get_state().user_types.add(identifier)
            type_parameters = set(expr_value.get('type_parameters') or [])
            ScopeStack.push()
            try:
                public_props: dict[str, PowangAny] = {}
                private_props: dict[str, PowangAny] = {}
                for public, prop in expr_value['properties']:
                    prop_identifier: str = prop['value']['identifier']['value']
                    concrete_prop = _replace_type_parameters(prop, type_parameters)
                    evaluateAstExpression(concrete_prop)
                    if public:
                        public_props[prop_identifier] = ScopeStack.variables[-1][prop_identifier]
                    else:
                        private_props[prop_identifier] = ScopeStack.variables[-1][prop_identifier]

                public_meths: dict[str, list[PowangFunction]] = {}
                private_meths: dict[str, list[PowangFunction]] = {}
                public_static_meths: dict[str, list[PowangFunction]] = {}
                private_static_meths: dict[str, list[PowangFunction]] = {}
                for public, method in expr_value['methods']:
                    method_identifier: str = method['value']['identifier']['value']
                    concrete_method = _replace_type_parameters(method, type_parameters)
                    evaluateAstExpression(concrete_method)
                    loaded = ScopeStack.functions[-1][method_identifier][-1]
                    is_instance = (
                        method_identifier == CONSTRUCTOR_METHOD_NAME
                        or bool(method['value'].get('instance_method'))
                    )
                    if is_instance:
                        target = public_meths if public else private_meths
                    else:
                        target = public_static_meths if public else private_static_meths
                    target.setdefault(method_identifier, []).append(loaded)
            finally:
                # Unwind even on error so the REPL does not leak scope frames.
                ScopeStack.pop()
            get_state().user_types.remove(identifier)
            new_user_type = PowangObjectType(
                public_props, private_props,
                public_meths, private_meths,
                public_static_meths, private_static_meths,
            )
            new_user_type.type_name = identifier
            return ScopeStack.new_ObjectType(identifier, new_user_type)

        case ParserTokenType.SAFE_ACCESS_EXPRESSION:
            safe_target = evaluateAstExpression(expr_value['target'])
            safe_target = unwrap_any_value(safe_target)
            if safe_target.type == PowangNova.type or not safe_target.weak.has_value:
                return PowangNova()
            if safe_target.type == PowangErrorValue.type:
                property_identifier = getValidIdentifier(where, expr_value['property'])
                return getErrorProperty(where, safe_target, property_identifier)
            if safe_target.type == PowangModule.type:
                property_identifier = getValidIdentifier(where, expr_value['property'])
                return moduleMemberValue(where, safe_target, property_identifier)
            assert safe_target.type == PowangObjectType.type, powang_error_syntax(where, "Invalid safe access", [
                f"{safe_target.type} cannot be accessed in any way or has no properties"
            ])
            property_identifier = getValidIdentifier(where, expr_value['property'])
            assert safe_target.defined, powang_error_undefined_reference(where, expr_value['target']['value'])
            is_private: bool = len(ScopeStack.method_call_stack) > 0
            property_value = safe_target.getProperty(property_identifier, is_private)
            assert property_value is not None, powang_error_identifier_not_found(where, property_identifier, [
                "perhaps it is a private property?"
            ] if not is_private else [])
            return property_value

        case ParserTokenType.ACCESS_EXPRESSION:
            target = evaluateAstExpression(expr_value['target'])
            target = unwrap_any_value(target)
            if target.type == PowangErrorValue.type:
                property_identifier = getValidIdentifier(where, expr_value['property'])
                return getErrorProperty(where, target, property_identifier)
            if target.type == PowangModule.type:
                property_identifier = getValidIdentifier(where, expr_value['property'])
                return moduleMemberValue(where, target, property_identifier)
            if target.type == PowangMap.type:
                property_identifier = getValidIdentifier(where, expr_value['property'])
                key = PowangString(property_identifier)
                if key in target.data:
                    return target.data[key]
                raise powang_throw(powang_error_identifier_not_found(where, property_identifier, [
                    "perhaps it is a private variant?"
                ]))
            assert target.type == PowangObjectType.type, powang_error_syntax(where, "Invalid access", [
                f"{target.type} cannot be accessed in any way or has no properties"
            ])
            property_identifier = getValidIdentifier(where, expr_value['property'])
            assert target.defined, powang_error_undefined_reference(where, expr_value['target']['value'])
            assert target.weak.has_value, powang_error_format("VALUE", where, f"Invalid access", [
                f"Trying to access property {property_identifier} from a nova weak {target.type_name}"
            ])

            is_private: bool = len(ScopeStack.method_call_stack) > 0
            property_value = target.getProperty(property_identifier, is_private)
            assert property_value is not None, powang_error_identifier_not_found(where, property_identifier, [
                "perhaps it is a private property?"
            ] if not is_private else [])
            return property_value

        case ParserTokenType.METHOD_CALL:
            owner_node = expr_value['owner']
            if isinstance(owner_node, dict) and \
                    owner_node.get('type') == LexerTokenType.IDENTIFIER and \
                    owner_node.get('value') in NATIVE_METHOD_TYPES:
                native_arguments = [
                    evaluateAstExpression(call_arg)
                    for call_arg in expr_value['arguments']
                ]
                return call_native_method(
                    where,
                    owner_node['value'],
                    expr_value['method']['value'],
                    native_arguments,
                )
            if isinstance(owner_node, dict) and owner_node.get('type') == LexerTokenType.IDENTIFIER:
                user_type = ScopeStack.get_ObjectType(owner_node.get('value'))
                if user_type is not None:
                    static_methods = user_type.getStaticMethods(expr_value['method']['value'], False)
                    if static_methods is None:
                        raise powang_throw(powang_error_identifier_not_found(
                            where, f"method: {expr_value['method']['value']}", [
                                "perhaps is a private static method?"
                            ]))
                    static_arguments = [
                        evaluateAstExpression(call_arg)
                        for call_arg in expr_value['arguments']
                    ]
                    candidate = getFunctionCandidate(static_methods, static_arguments)
                    return callFunction(
                        where,
                        f"{owner_node['value']}.{expr_value['method']['value']}",
                        candidate,
                        static_arguments,
                    )
            owner_value = evaluateAstExpression(expr_value['owner'])
            owner_value = unwrap_any_value(owner_value)
            call_parameters = [evaluateAstExpression(call_arg) for call_arg in expr_value['arguments']]
            if owner_value.type in NATIVE_METHOD_TYPES:
                return call_native_method(
                    where,
                    owner_value.type,
                    expr_value['method']['value'],
                    [owner_value] + call_parameters,
                )
            if owner_value.type == PowangModule.type:
                return callModuleMember(
                    where,
                    owner_value,
                    expr_value['method']['value'],
                    call_parameters,
                )
            assert owner_value.type == PowangObjectType.type, powang_error_format('IMPLEMENTATION', where,
                "Currently only user types can perform a method call.", [
                    f"but trying to call from a {owner_value.type}"
            ])


            match_methods = owner_value.getMethods(expr_value['method']['value'], len(ScopeStack.method_call_stack) > 0)
            if match_methods is None:
                raise powang_throw(powang_error_identifier_not_found(
                    where, f"method: {expr_value['method']['value']}", [
                        "perhaps is a private method?"
                    ]))

            method_candidate = getFunctionCandidate(match_methods, call_parameters)
            return callMethod(
                where,
                owner_value,
                expr_value['method']['value'],
                method_candidate,
                call_parameters,
            )

        case ParserTokenType.USE_EXPRESSION:
            use_value = expr_value
            loader = get_module_loader()
            module = loader.load(use_value)

            if use_value.get('wildcard'):
                bindWildcardImport(where, module)
            else:
                binding_name = use_value.get('alias') or module.name
                if ScopeStack.get_variable(binding_name) is not None \
                        or ScopeStack.get_functions(binding_name) is not None \
                        or ScopeStack.get_ObjectType(binding_name) is not None:
                    existing_module = ScopeStack.get_variable(binding_name)
                    if existing_module is module:
                        return PowangNova()
                    raise powang_throw(powang_error_format(
                        'MODULE', where, f"Import collision for '{binding_name}'", [
                            f"module '{module.name}' cannot be bound",
                            f"'{binding_name}' is already declared in this scope",
                        ]
                    ))
                ScopeStack.new_variable(binding_name, module)
                ## Legacy modules (no export declarations) historically spliced
                ## their top-level names into the importer. Keep that path alive
                ## when the program uses the old alias-less form.
                if module.legacy and use_value.get('alias') is None:
                    bindWildcardImport(where, module)

        case ParserTokenType.EXTERN_REFERENCE:
            powang = expr_value['powang']
            python = expr_value['python']

            attributes = python.split('.')

            module_name = attributes[0]
            if module_name not in get_state().allowed_extern_modules:
                raise powang_throw(powang_error_format('MODULE', "extern", 'Module is not allowed in the extern enviroment', [
                    f'module: {module_name}'
                ]))

            extern_module = get_extern_module(module_name)
            extern = extern_module
            for attribute in attributes[1:]:
                extern = getattr(extern, attribute)

            extern_signature = evaluateAstExpression(powang)

            if powang['type'] == ParserTokenType.DECLARATION_FUN:
                assert extern_signature.type == PowangFunction.type, powang_error_format('DEVELOPMENT', 'extern function', "Somehow you get here without a function")
                ## The callable rides on the signature so module-qualified
                ## calls (`math.sqrt`) can find it without relying on a global
                ## name that another module could shadow.
                setattr(extern_signature, 'external', extern)
                get_state().external_functions[powang['value']['identifier']['value']] = (extern_signature, extern)
            else:
                raise powang_throw(powang_error_format('EXTERN', 'extern type',
                    "extern type declarations are not supported yet", [
                        f"python type: {python}"
                    ]))
    return PowangNova()

def _replace_type_parameters(node: Any, parameters: set[str]) -> Any:
    if isinstance(node, list):
        return [_replace_type_parameters(item, parameters) for item in node]
    if not isinstance(node, dict):
        return node
    if node.get('type') == ParserTokenType.TYPE:
        inner = node.get('value')
        if isinstance(inner, dict) and inner.get('value') in parameters:
            return doToken(ParserTokenType.TYPE, {
                'value': PowangAnyType.type,
                'weak': False,
                'const': bool(inner.get('const')),
                'error_union': bool(inner.get('error_union')),
                'reference': False,
                'element_type': None,
                'generics': [],
                'variadic': False,
                'alternatives': [],
                'auto': False,
            }).toDict()
    return {
        key: _replace_type_parameters(value, parameters)
        for key, value in node.items()
    }


def get_file_content(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        if not content.endswith('\n'):
            content = content + '\n'
        return content


def _exported_declaration_name(statement: DictRepr) -> str | None:
    statement_type = statement.get('type')
    value = statement.get('value')
    if statement_type == ParserTokenType.EXTERN_REFERENCE and isinstance(value, dict):
        inner = value.get('powang')
        if isinstance(inner, dict):
            statement_type = inner.get('type')
            value = inner.get('value')
    if statement_type not in {
        ParserTokenType.DECLARATION_FUN,
        ParserTokenType.DECLARATION_UNDEFINED,
        ParserTokenType.DECLARATION_TYPED_VAR,
        ParserTokenType.DECLARATION_INTERPRET,
        ParserTokenType.TYPE_DECLARATION,
    } or not isinstance(value, dict):
        return None
    identifier = value.get('identifier')
    if not isinstance(identifier, dict):
        return None
    name = identifier.get('value')
    return name if isinstance(name, str) else None


def _attach_module_closure(scope_variables, scope_functions, scope_types) -> None:
    closure = {
        'variables': scope_variables,
        'functions': scope_functions,
        'ObjectTypes': scope_types,
    }

    def attach(function: Any) -> None:
        if getattr(function, 'type', None) == PowangFunction.type:
            ## Never steal a function that already belongs to another module;
            ## wildcard imports put foreign functions in this scope.
            if not hasattr(function, 'closure'):
                setattr(function, 'closure', closure)

    for overloads in scope_functions.values():
        for function in overloads:
            attach(function)
    for value in scope_variables.values():
        attach(value)
    for object_type in scope_types.values():
        for overloads in object_type.public_meths.values():
            for method in overloads:
                attach(method)
        for overloads in object_type.private_meths.values():
            for method in overloads:
                attach(method)


def evaluate_module_ast(
    program_ast: list[DictRepr],
    module_name: str,
    module_path: Any,
    loader: Any,
) -> PowangModule:
    exported: list[tuple[str, str]] = []
    has_exports: bool = False
    for statement in program_ast:
        if not statement.get('exported'):
            continue
        has_exports = True
        name = _exported_declaration_name(statement)
        if name is None:
            continue
        statement_type = statement.get('type')
        kind = 'function' if statement_type in {
            ParserTokenType.DECLARATION_FUN,
            ParserTokenType.EXTERN_REFERENCE,
        } else 'type' if statement_type == ParserTokenType.TYPE_DECLARATION else 'variable'
        exported.append((name, kind))

    saved_scopes = ScopeStack.save_scopes()
    ScopeStack.reset_scopes()
    ScopeStack.push(ScopeType.GLOBAL)
    try:
        for statement in program_ast:
            evaluateAstExpression(statement)

        scope_variables = ScopeStack.variables[-1]
        scope_functions = ScopeStack.functions[-1]
        scope_types = ScopeStack.ObjectTypes[-1]

        _attach_module_closure(scope_variables, scope_functions, scope_types)

        members: dict[str, Any] = {}
        if has_exports:
            seen: dict[str, str] = {}
            for name, kind in exported:
                previous = seen.get(name)
                if previous is not None and not (previous == kind == 'function'):
                    raise powang_throw(powang_error_format(
                        'MODULE', f'module: {module_path}',
                        f"Duplicate export: {name}", [
                            f"already exported as {previous}",
                            f"then exported again as {kind}",
                        ]
                    ))
                seen[name] = kind

                if name in scope_functions:
                    members[name] = list(scope_functions[name])
                elif name in scope_types:
                    members[name] = scope_types[name]
                elif name in scope_variables:
                    members[name] = scope_variables[name]
                else:
                    raise powang_throw(powang_error_format(
                        'MODULE', f'module: {module_path}',
                        f"Exported name was not declared: {name}",
                    ))
        else:
            key = str(module_path.resolve()) if hasattr(module_path, 'resolve') else str(module_path)
            if key not in loader.warned:
                loader.warned.add(key)
                print(
                    f"[MODULE WARNING] module '{module_name}' declares no exports; "
                    "exporting all top-level names",
                    file=sys.stderr,
                )
            for name, value in scope_variables.items():
                members[name] = value
            for name, overloads in scope_functions.items():
                members[name] = list(overloads)
            for name, object_type in scope_types.items():
                members[name] = object_type

        module = PowangModule(module_name, members)
        module.legacy = not has_exports
        return module
    finally:
        ScopeStack.pop()
        ScopeStack.restore_scopes(saved_scopes)

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


import json

_interpret_depth: ContextVar[int] = ContextVar("powang_interpret_depth", default=0)

def interpret_program(content: str, ast_output: str | None, check: bool = False, *, state=None):
    ## Only the outermost call is a "run" (REPL lines call this directly, the
    ## same way a file run does). Nested `use` interpretation must not reset
    ## the depth guard of the caller. The counter is per execution context so
    ## two threads running programs cannot make each other look nested.
    is_outermost = _interpret_depth.get() == 0
    state_token = None
    if is_outermost:
        reset_evaluation_depth()
        ## Every file run gets a fresh state, so two sequential runs in one
        ## process cannot see each other's scopes, modules, externs, type
        ## aliases or open files. The REPL passes its own long-lived state so
        ## variables persist between lines. Nested runs keep the importer's
        ## state because they never reach this branch.
        if state is not None:
            active_state = state
        else:
            active_state = fresh_state()
            ## Paths and script arguments are caller configuration rather than
            ## runtime data. Copy the active context's values so callers that
            ## still configure PATHS/set_argv before a run keep working. The
            ## copy is per state, never a shared object.
            previous_state = get_state()
            active_state.paths.update(previous_state.paths)
            active_state.script_argv.extend(previous_state.script_argv)
        state_token = set_state(active_state)
    depth_token = _interpret_depth.set(_interpret_depth.get() + 1)
    ## Building the parser can already tokenize and raise, so it belongs inside
    ## the guarded region: otherwise a bad first character would leave the run
    ## depth and the fresh state installed for the next run in this context.
    program_parser: Parser | None = None
    try:
        program_parser = Parser(content, source_path=PATHS.get('RELATIVE'))
        program_raw_ast = program_parser.parse()
        if check:
            relative_path = PATHS.get('RELATIVE')
            type_errors = type_check(
                program_raw_ast,
                str(relative_path) if relative_path is not None else None,
            )
            if type_errors:
                ## Abort before execution with the first static diagnostic.
                ## The AST carries no line information, so mark it to keep
                ## the end-of-file line out of the rendered message.
                setattr(type_errors[0], '_from_type_check', True)
                raise type_errors[0]
        if getattr(get_state(), 'project_value', None) is not None and not _has_project_declaration(program_raw_ast):
            ScopeStack.new_variable('project', get_state().project_value)
        result = PowangNova()
        if ast_output:
            def make_json_serializable(raw_ast):
                if isinstance(raw_ast, dict):
                    return {
                        key: make_json_serializable(value)
                        for key, value in raw_ast.items()
                    }
                elif isinstance(raw_ast, (LexerTokenType, ParserTokenType)):
                    return TokenToString(raw_ast).upper()
                elif isinstance(raw_ast, (list, tuple)):
                    return [make_json_serializable(item) for item in raw_ast]
                else:
                    return raw_ast

            ast_dict = make_json_serializable(program_raw_ast)

            with open(ast_output, 'w', encoding='utf-8') as json_ast:
                json_ast.write(json.dumps(ast_dict, indent=4, ensure_ascii=False))
        for statement in program_raw_ast:
            check_cancellation()
            result = evaluateAstExpression(statement)
        return result
    except PowangError as ass:
        if getattr(ass, '_from_type_check', False):
            raise ass from None
        error_line = program_parser.tokenizer.row + 1 if program_parser is not None else None
        raise ass.with_line(error_line) from None
    except AssertionError as ass:
        converted_error = powang_error_from_exception(ass)
        if converted_error is None:
            ## Not a language error: keep the Python assertion visible.
            raise
        error_line = program_parser.tokenizer.row + 1 if program_parser is not None else None
        raise converted_error.with_line(error_line) from None
    finally:
        _interpret_depth.reset(depth_token)
        if state_token is not None:
            ## Restore whatever state (usually none) was active before this
            ## run. Scopes never leak past the outermost interpret_program.
            active_state.emit_warnings()
            reset_state(state_token)
