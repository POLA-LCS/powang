"""Call resolution and argument binding for the bytecode VM.

This module owns the call order and the error text that the tree walker
defines. It resolves identifiers, methods, statics, module members, natives,
builtins, traits, first class values, constructors, externs and tasks. The
interpreter calls into it, never the other way around.
"""

from __future__ import annotations

from typing import Any, Optional

from ..powang_types import *
from ..error import (
    powang_throw,
    powang_error_format,
    powang_error_identifier_not_found,
    powang_error_undefined_argument,
)
from ..runtime import (
    BUILTINS,
    NATIVE_METHOD_TYPES,
    areSameObjectType,
    assignWithChecks,
    callExternalFunction,
    callFunction,
    callModuleMember,
    call_native_method,
    copy_for_task,
    getFunctionCandidate,
    getModuleMember,
    getUndefinedVariable,
    moduleMemberValue,
    resolveNamedArguments,
    _capture_scopes,
    _bind_lambda_name,
    _find_default_trait_method,
    _private_access_allowed,
    _spread_values,
    _node_position,
)
from ..scopestack import ScopeStack
from ..state import get_state
from .. import typespec as _typespec
from ..operator_traits import OPERATOR_TRAITS


def flatten_arguments(site, raw_args: list[Any]) -> tuple[list[PowangAny], list[tuple[str, PowangAny]]]:
    """Expand spread wrappers and split positional from named arguments."""
    from .values import SpreadValue

    positional: list[PowangAny] = []
    named: list[tuple[str, PowangAny]] = []
    kinds = site.argument_kinds
    names = site.argument_names
    for index, raw in enumerate(raw_args):
        kind = kinds[index] if index < len(kinds) else "positional"
        name = names[index] if index < len(names) else ""
        if isinstance(raw, SpreadValue):
            positional.extend(_spread_values(raw.value))
            continue
        if kind == "named":
            named.append((name, raw))
            continue
        positional.append(raw)
    return positional, named


def make_function(info, image, *, is_lambda: bool = False,
                  lambda_name: Optional[str] = None,
                  mutable_capture: bool = False) -> PowangFunction:
    """Build the language function value for one function table entry."""
    body = info.flags.get("body") or []
    function = PowangFunction(list(info.args), list(body), info.return_node)
    function.min_argc = info.min_argc
    function.is_async = bool(info.flags.get("is_async"))
    function.is_lambda = bool(info.flags.get("is_lambda", is_lambda))
    function.mutable_capture = bool(info.flags.get("mutable_capture", mutable_capture))
    function.type_parameters = list(info.flags.get("type_parameters") or [])
    function.variadic = bool(info.flags.get("variadic"))
    function.variadic_index = info.flags.get("variadic_index")
    function.function_type = info.flags.get("function_type")
    function.instance_method = bool(info.flags.get("instance_method"))
    function.trait_qualifier = info.flags.get("trait_qualifier")
    function.lambda_name = info.flags.get("lambda_name", lambda_name)
    function.code = image.code(info.code_index) if image is not None else None
    function.vm_image = image
    function.vm_name = info.name
    function.vm_defaults = list(info.flags.get("defaults") or [])
    if function.is_lambda:
        function.captured_this = (
            ScopeStack.method_call_stack[-1]
            if ScopeStack.method_call_stack else None
        )
        captured = _capture_scopes(ScopeStack.save_scopes(), function.mutable_capture)
        if isinstance(function.lambda_name, str) and function.lambda_name:
            captured = _bind_lambda_name(captured, function.lambda_name, function)
        function.captured_scopes = captured
    return function


def _run_default(vm, code_index: int, where: str) -> PowangAny:
    image = vm.image
    code = image.code(code_index)
    return vm.run_code(code, [], is_function=True, default_frame=True)


def _resolve_named(function: PowangFunction, positional: list[PowangAny],
                   named: list[tuple[str, PowangAny]], where: str,
                   vm) -> list[PowangAny]:
    """Bind names and defaults before the callee frame exists.

    Defaults run in the caller scope, matching ``resolveNamedArguments`` in the
    tree walker. Each default has its own small code object.
    """
    arg_names = [
        arg['value']['identifier']['value']
        for arg in function.args
        if isinstance(arg, dict) and isinstance(arg.get('value'), dict)
        and isinstance(arg['value'].get('identifier'), dict)
    ]
    variadic = getattr(function, 'variadic', False)
    variadic_index = getattr(function, 'variadic_index', None)
    fixed_count = (
        variadic_index
        if variadic and isinstance(variadic_index, int)
        else len(arg_names)
    )
    fixed_names = arg_names[:fixed_count]
    resolved: list[PowangAny | None] = [None] * fixed_count
    extra: list[PowangAny] = []
    for index, value in enumerate(positional):
        if index < fixed_count:
            resolved[index] = value
        elif variadic:
            extra.append(value)
        else:
            raise powang_throw(powang_error_format('ARGUMENT', where, 'too many arguments'))
    for name, value in named:
        if name not in fixed_names:
            detail = (
                'named arguments cannot target a variadic parameter'
                if name in arg_names and name not in fixed_names
                else f"parameters: {', '.join(fixed_names)}"
            )
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, f"has no parameter named '{name}'", [detail],
            ))
        index = fixed_names.index(name)
        if resolved[index] is not None:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, f"received '{name}' more than once",
            ))
        resolved[index] = value
    defaults = getattr(function, 'vm_defaults', None) or []
    for index, value in enumerate(resolved):
        if value is not None:
            continue
        if index < function.min_argc:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where,
                f"Missing required argument '{fixed_names[index]}'", [
                    f"parameters: {', '.join(fixed_names)}",
                ],
            ))
        if index < len(defaults) and isinstance(defaults[index], int) and defaults[index] >= 0:
            resolved[index] = _run_default(vm, defaults[index], where)
            continue
        argument = function.args[index] if index < len(function.args) else None
        argument_value = argument.get('value') if isinstance(argument, dict) else None
        default_expression = argument_value.get('expression') if isinstance(argument_value, dict) else None
        if default_expression is not None:
            from ..runtime import evaluateAstExpression
            resolved[index] = evaluateAstExpression(default_expression)
            continue
        raise powang_throw(powang_error_format(
            'ARGUMENT', where,
            f"Missing required argument '{fixed_names[index]}'", [
                f"parameters: {', '.join(fixed_names)}",
            ],
        ))
    return [value for value in resolved if value is not None] + extra


def bind_parameters(vm, frame, function: PowangFunction,
                    call_parameters: list[PowangAny], where: str) -> None:
    """Type check and store the bound arguments in the callee frame."""
    parameter_names = frame.code.parameter_names
    variadic = getattr(function, 'variadic', False)
    variadic_index = getattr(function, 'variadic_index', None)
    for index, argument in enumerate(function.args):
        argument_value = argument.get('value') if isinstance(argument, dict) else None
        if not isinstance(argument_value, dict):
            continue
        identifier = argument_value.get('identifier', {})
        parameter_name = identifier.get('value')
        type_node = argument_value.get('type')
        type_inner = type_node.get('value') if isinstance(type_node, dict) else None
        param_type = type_inner.get('value') if isinstance(type_inner, dict) else None
        is_reference = isinstance(type_inner, dict) and bool(type_inner.get('reference'))

        if variadic and variadic_index == index:
            items = call_parameters[index:]
            type_parameters = set(getattr(function, 'type_parameters', []) or [])
            element_name = param_type if isinstance(param_type, str) else None
            if element_name not in type_parameters and isinstance(type_inner, dict):
                for item in items:
                    element_target = getUndefinedVariable(where, type_inner)
                    assignWithChecks(
                        'function call', element_target, item,
                        areSameObjectType(element_target, item),
                    )
            frame.locals[parameter_name] = PowangArray(
                [copy_for_task(item) for item in items]
            )
            break

        if is_reference:
            if index >= len(call_parameters):
                continue
            argument_value_ref = call_parameters[index]
            if argument_value_ref.type != PowangReference.type:
                raise powang_throw(powang_error_format(
                    'REFERENCE', 'function call', "Expected a reference argument", [
                        f"parameter '{parameter_name}' is declared as &{param_type}",
                        "pass it as &variable",
                        f"but {argument_value_ref.type} was encountered",
                    ]))
            expected = param_type
            if argument_value_ref.target_type not in {expected, PowangAnyType.type}:
                raise powang_throw(powang_error_format(
                    'REFERENCE', 'function call', "Reference type does not match", [
                        f"expected &{expected}",
                        f"but &{argument_value_ref.target_type} was encountered",
                    ]))
            frame.locals[parameter_name] = argument_value_ref
            continue

        if index < len(call_parameters):
            if not isinstance(type_inner, dict):
                frame.locals[parameter_name] = copy_for_task(call_parameters[index])
                continue
            target = getUndefinedVariable(where, type_inner)
            value = copy_for_task(call_parameters[index])
            assignWithChecks(
                'function call', target, value,
                areSameObjectType(target, value),
            )
            frame.locals[parameter_name] = target

    if not variadic and len(call_parameters) > len(function.args):
        raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'too many arguments'))
    if len(call_parameters) < function.min_argc:
        raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'not enought arguments'))
    for index, call_arg in enumerate(call_parameters):
        if not call_arg.defined:
            raise powang_throw(powang_error_undefined_argument(where, index + 1, call_arg.type))


def call_function_value(vm, frame, function: PowangFunction,
                        positional: list[PowangAny],
                        named: list[tuple[str, PowangAny]],
                        where: str, *, receiver: Optional[PowangObjectType] = None,
                        is_static: bool = False,
                        frame_name: Optional[str] = None,
                        force_sync: bool = False) -> PowangAny:
    """Call a first class function, dispatching to the VM when it has code."""
    if receiver is None:
        captured_this = getattr(function, 'captured_this', None)
        if captured_this is not None:
            receiver = captured_this
    external = getattr(function, 'external', None)
    if external is not None:
        ordered = _resolve_named(function, positional, named, where, vm)
        return callExternalFunction(where, getattr(function, 'vm_name', None) or getattr(function, 'lambda_name', None) or '<extern>', function, external, ordered)
    if getattr(function, 'is_async', False) and receiver is None and not force_sync:
        from .tasks import create_lazy_function_task
        ordered = _resolve_named(function, positional, named, where, vm)
        return create_lazy_function_task(vm, function, ordered, where)
    ordered = _resolve_named(function, positional, named, where, vm)
    code = getattr(function, 'code', None)
    if code is None:
        ## A tree walker function value. Named and defaults are already
        ## resolved, so the shared call path only has to bind and run.
        return callFunction(where, getattr(function, 'vm_name', None) or getattr(function, 'lambda_name', None) or '<function>', function, ordered)
    state = get_state()
    function_image = getattr(function, 'vm_image', None)
    runner = vm
    if function_image is not None and function_image is not vm.image:
        runner = vm.sibling(function_image)
    state.type_parameter_stack.append(set(getattr(function, 'type_parameters', []) or []))
    try:
        if receiver is not None and not is_static:
            ScopeStack.method_call_stack.append(receiver)
        if is_static and receiver is not None:
            ScopeStack.static_method_stack.append(receiver.type_name)
        try:
            return runner.run_code(
                code,
                ordered,
                receiver=None if is_static else receiver,
                closure=getattr(function, 'captured_scopes', None)
                or getattr(function, 'closure', None),
                is_function=True,
                frame_name=frame_name or getattr(function, 'vm_name', None) or getattr(function, 'lambda_name', None),
                module_scope=getattr(function, 'vm_module_scope', None) or runner.current_module_scope(),
                type_check_function=function,
            )
        finally:
            if is_static and receiver is not None:
                ScopeStack.static_method_stack.pop()
            if receiver is not None and not is_static:
                ScopeStack.method_call_stack.pop()
    finally:
        state.type_parameter_stack.pop()


def call_identifier(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    name = site.name
    where = f"call: {name}"
    functions = ScopeStack.get_functions(name)
    if functions is not None:
        if site.type_argument_count:
            functions = [
                candidate for candidate in functions
                if len(getattr(candidate, 'type_parameters', []) or []) == site.type_argument_count
            ]
            if not functions:
                raise powang_throw(powang_error_format(
                    'ARGUMENT', where,
                    f"No generic overload of '{name}' accepts {site.type_argument_count} type arguments",
                ))
        if named:
            if len(functions) != 1:
                raise powang_throw(powang_error_format(
                    'ARGUMENT', where, f"Named arguments for '{name}' require a single overload", [
                        f"found {len(functions)} overloads",
                    ],
                ))
            candidate = functions[0]
        else:
            candidate = getFunctionCandidate(functions, positional)
        external = getattr(candidate, 'external', None)
        if external is not None:
            if named:
                raise powang_throw(powang_error_format(
                    'ARGUMENT', where, 'Named arguments are not supported for external functions',
                ))
            return callExternalFunction(where, name, candidate, external, positional)
        return call_function_value(
            vm, frame, candidate, positional, named, where,
            frame_name=name,
        )

    if name in get_state().external_functions:
        if named:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, 'Named arguments are not supported for external functions',
            ))
        function, external = get_state().external_functions[name]
        return callExternalFunction(where, name, function, external, positional)

    if name in BUILTINS:
        call_min_argc, call_max_argc, call_func = BUILTINS[name]
        if call_max_argc != -1 and len(positional) > call_max_argc:
            raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'too many arguments'))
        if len(positional) < call_min_argc:
            raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'not enought arguments'))
        return call_func(*positional)

    variable = ScopeStack.get_variable(name)
    if variable is not None and variable.type == PowangFunction.type:
        return call_function_value(
            vm, frame, variable, positional, named, where,
            frame_name=name,
        )
    raise powang_throw(powang_error_identifier_not_found(where, name))


def _resolve_instance_method(receiver: PowangObjectType, method_name: str,
                             resolved_trait: Optional[str],
                             arguments: list[PowangAny], where: str):
    methods = receiver.getMethods(method_name, _private_access_allowed(receiver))
    if methods is None and isinstance(resolved_trait, str):
        methods = receiver.getTraitMethods(resolved_trait, method_name)
        if methods is None:
            trait = get_state().traits.get(resolved_trait)
            if trait is not None:
                methods = trait.default_methods.get(method_name)
    if methods is None:
        qualified_methods = receiver.getAllTraitMethods(method_name)
        if len(qualified_methods) > 1:
            raise powang_throw(powang_error_format(
                'IMPLEMENTATION', where,
                f"call to {method_name} is ambiguous between trait methods",
                ['use Trait.method to select one'],
            ))
        if qualified_methods:
            methods = qualified_methods
        else:
            methods = _find_default_trait_method(receiver, method_name)
    if methods is None:
        raise powang_throw(powang_error_identifier_not_found(
            where, f"method: {method_name}", [
                "perhaps is a private method?"
            ]))
    return methods


def call_method(vm, frame, site, raw_args: list[Any],
                receiver: PowangAny) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    receiver = PowangUnwrapAny(receiver)
    method_name = site.name
    where = f"method call: {method_name}"
    if receiver.type == PowangModule.type:
        if named:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, 'Named arguments are not supported for module members',
            ))
        return callModuleMember(where, receiver, method_name, positional)
    if receiver.type in NATIVE_METHOD_TYPES:
        return call_native_method(
            where, receiver.type, method_name, [receiver] + positional,
        )
    if receiver.type != PowangObjectType.type:
        raise powang_throw(powang_error_format(
            'IMPLEMENTATION', where,
            "Currently only user types can perform a method call.", [
                f"but trying to call from a {receiver.type}"
            ]))
    methods = _resolve_instance_method(receiver, method_name, site.trait_name, positional, where)
    candidate = getFunctionCandidate(methods, positional)
    if getattr(candidate, 'is_async', False):
        from .tasks import create_lazy_method_task
        return create_lazy_method_task(vm, receiver, method_name, candidate, positional, where)
    ## The tree walker drops named arguments on instance method calls. Keep
    ## the same behavior so a program cannot observe a difference.
    return call_function_value(
        vm, frame, candidate, positional, [], where,
        receiver=receiver, frame_name=f"{receiver.type_name}.{method_name}",
    )


def call_static(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    type_name = site.type_name
    method_name = site.name
    where = f"method call: {type_name}.{method_name}"
    user_type = ScopeStack.get_ObjectType(type_name)
    if user_type is None:
        raise powang_throw(powang_error_identifier_not_found(where, f"method: {method_name}"))
    private_allowed = _private_access_allowed(user_type)
    static_methods = user_type.getStaticMethods(method_name, private_allowed)
    if static_methods is None:
        raise powang_throw(powang_error_identifier_not_found(
            where, f"method: {method_name}", ["perhaps is a private static method?"],
        ))
    if named and len(static_methods) != 1:
        raise powang_throw(powang_error_format(
            'ARGUMENT', where,
            f"Named arguments for '{method_name}' require a single overload", [
                f"found {len(static_methods)} overloads",
            ],
        ))
    candidate = getFunctionCandidate(static_methods, positional + [value for _, value in named])
    if getattr(candidate, 'is_async', False):
        from .tasks import create_lazy_static_task
        return create_lazy_static_task(
            vm, user_type, method_name, candidate, positional, named, where,
        )
    return call_function_value(
        vm, frame, candidate, positional, named, where,
        receiver=user_type, is_static=True,
        frame_name=f"{type_name}.{method_name}",
    )


def call_module(vm, frame, site, raw_args: list[Any], target: PowangAny) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    target = PowangUnwrapAny(target)
    if target.type == PowangModule.type:
        if named:
            raise powang_throw(powang_error_format(
                'ARGUMENT', f"module: {target.name}",
                'Named arguments are not supported for module members',
            ))
        return callModuleMember(f"module: {target.name}", target, site.name, positional)
    if named:
        raise powang_throw(powang_error_format(
            'ARGUMENT', 'call expression',
            'Named arguments are not supported for this callee',
        ))
    return call_value(vm, frame, target, positional, [], 'call expression')


def call_value(vm, frame, callee: PowangAny,
               positional: list[PowangAny],
               named: list[tuple[str, PowangAny]], where: str) -> PowangAny:
    if isinstance(callee, list):
        if not callee:
            raise powang_throw(powang_error_identifier_not_found(where, '<expression>'))
        candidate = getFunctionCandidate(callee, positional)
    else:
        candidate = callee
    if getattr(candidate, 'type', None) != PowangFunction.type:
        raise powang_throw(powang_error_format(
            'MODULE', where, f"'<expression>' is not callable", [
                f"it is a {getattr(candidate, 'type', type(candidate).__name__)} value",
            ]
        ))
    return call_function_value(vm, frame, candidate, positional, named, where)


def call_native(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    if named:
        raise powang_throw(powang_error_format(
            'ARGUMENT', f"native method: {site.native_type}.{site.name}",
            'Named arguments are not supported for native methods',
        ))
    return call_native_method(
        f"native method: {site.native_type}.{site.name}",
        site.native_type or '',
        site.name,
        positional,
    )


def call_trait(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    if named:
        raise powang_throw(powang_error_format(
            'ARGUMENT', 'trait call',
            'Named arguments are not supported in trait-qualified calls',
        ))
    if not positional:
        raise powang_throw(powang_error_format(
            'ARGUMENT', 'trait call',
            f"trait-qualified call '{site.trait_name}.{site.name}' needs a receiver",
        ))
    receiver = PowangUnwrapAny(positional[0])
    arguments = positional[1:]
    trait_name = site.trait_name or ''
    where = f"trait call: {trait_name}.{site.name}"
    if receiver.type != PowangObjectType.type:
        raise powang_throw(powang_error_format(
            'IMPLEMENTATION', where,
            "Trait methods require an object receiver", [
                f"but {receiver.type} was encountered",
            ],
        ))
    trait = get_state().traits.get(trait_name)
    if trait is None:
        raise powang_throw(powang_error_format(
            'IMPLEMENTATION', where, f"unknown trait '{trait_name}'",
        ))
    methods = receiver.getTraitMethods(trait_name, site.name)
    if methods is None:
        methods = receiver.getMethods(site.name, _private_access_allowed(receiver))
    if methods is None:
        methods = trait.default_methods.get(site.name)
    if methods is None:
        raise powang_throw(powang_error_format(
            'IMPLEMENTATION', where,
            f"trait '{trait_name}' has no implementation for method '{site.name}'",
        ))
    candidate = getFunctionCandidate(methods, arguments)
    if getattr(candidate, 'is_async', False):
        from .tasks import create_lazy_method_task
        return create_lazy_method_task(
            vm, receiver, site.name, candidate, arguments, where,
        )
    return call_function_value(
        vm, frame, candidate, arguments, [], where,
        receiver=receiver, frame_name=f"{receiver.type_name}.{site.name}",
    )


def call_builtin(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    if named:
        raise powang_throw(powang_error_format(
            'ARGUMENT', 'Function call', 'Named arguments are not supported for builtins',
        ))
    if site.name not in BUILTINS:
        raise powang_throw(powang_error_identifier_not_found('builtin', site.name))
    call_min_argc, call_max_argc, call_func = BUILTINS[site.name]
    if call_max_argc != -1 and len(positional) > call_max_argc:
        raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'too many arguments'))
    if len(positional) < call_min_argc:
        raise powang_throw(powang_error_format("ARGUMENT", 'Function call', 'not enought arguments'))
    return call_func(*positional)


def call_extern(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    positional, named = flatten_arguments(site, raw_args)
    if named:
        raise powang_throw(powang_error_format(
            'ARGUMENT', 'extern call', 'Named arguments are not supported for external functions',
        ))
    binding = get_state().external_functions.get(site.name)
    if binding is None:
        callee = site.callee_ast
        if isinstance(callee, dict) and callee.get("value") in get_state().external_functions:
            binding = get_state().external_functions[callee.get("value")]
    if binding is None:
        raise powang_throw(powang_error_identifier_not_found('extern', site.name))
    function, external = binding
    return callExternalFunction('extern function: ' + site.name, site.name, function, external, positional)


def construct(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    """Instantiate a native, built in or user type with evaluated arguments."""
    from .declarations import instantiate
    return instantiate(vm, frame, site, raw_args)


def call_function_bridge(function: PowangFunction,
                         call_parameters: list[PowangAny],
                         where: str,
                         position=None,
                         frame_name=None) -> PowangAny:
    """Entry used by ``src.runtime.callFunction`` for VM compiled functions."""
    from .interpreter import VM
    from ..state import get_state
    from ..scopestack import ScopeStack
    state = get_state()
    vm = getattr(state, 'vm_instance', None)
    image = getattr(function, 'vm_image', None)
    if vm is None or getattr(vm, 'image', None) is not image:
        if image is None:
            raise powang_throw(powang_error_format(
                'DEVELOPMENT', where, 'VM function has no image',
            ))
        from .interpreter import VMRunOptions
        vm = VM(state, image, VMRunOptions())
        state.vm_instance = vm
    receiver = ScopeStack.method_call_stack[-1] if ScopeStack.method_call_stack else None
    is_static = bool(ScopeStack.static_method_stack) and receiver is None
    return vm.call_function(
        function, call_parameters, where=where, frame_name=frame_name,
        receiver=receiver, is_static=is_static,
    )
