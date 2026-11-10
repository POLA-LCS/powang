"""Lazy and worker task helpers for the VM.

The interpreter creates tasks through this module. The lazy task body runs on
the current thread when ``AWAIT`` reaches it. A spawned task runs on the pool
worker. Both execute bytecode in a cloned interpreter state.
"""

from __future__ import annotations

from typing import Any, Optional

from ..powang_types import *
from ..error import powang_throw, powang_error_format
from ..state import get_state
from ..scopestack import ScopeStack
from ..builtins.tasks import get_task_pool, spawn_task
from ..runtime import copy_for_task

from .frames import LocalStore
from .modules import ModuleScope


def _copy_module_scope(scope: ModuleScope) -> ModuleScope:
    names = [
        name for name in scope.variables.keys()
        if scope.global_names is None
        or name in scope.global_names
        or name == 'project'
    ]
    variables = LocalStore(names)
    for name in names:
        try:
            variables[name] = copy_for_task(scope.variables[name])
        except Exception:
            variables[name] = scope.variables[name]
    functions: dict[str, list] = {}
    types = dict(scope.types)
    closure = {
        "variables": variables,
        "functions": functions,
        "ObjectTypes": types,
    }
    for name, overloads in scope.functions.items():
        copied_overloads = []
        for function in overloads:
            copied = _copy_vm_function(function)
            if getattr(function, 'closure', None) is not None:
                copied.closure = closure
            copied_overloads.append(copied)
        functions[name] = copied_overloads
    copied = ModuleScope(
        name=scope.name,
        path=scope.path,
        variables=variables,
        functions=functions,
        types=types,
        wildcards=dict(scope.wildcards),
    )
    return copied


def _task_module_scopes(parent_vm, state) -> dict[str, ModuleScope]:
    scopes: dict[str, ModuleScope] = {}
    for scope in parent_vm.module_scopes.values():
        scopes[scope.name] = _copy_module_scope(scope)
    loader = getattr(getattr(parent_vm, 'state', None), 'module_loader', None)
    cache = getattr(loader, 'cache', None)
    if isinstance(cache, dict):
        for module in cache.values():
            scope = getattr(module, 'vm_scope', None)
            if scope is not None and scope.name not in scopes:
                scopes[scope.name] = _copy_module_scope(scope)
    return scopes


def _task_vm(parent_vm, state):
    from .interpreter import VM, VMRunOptions
    vm = VM(state, parent_vm.image, VMRunOptions(trace=parent_vm.options.trace))
    vm.module_scopes = _task_module_scopes(parent_vm, state)
    return vm


def _copy_vm_function(function: PowangFunction) -> PowangFunction:
    """Copy a function for a task and keep its bytecode metadata.

    ``PowangCopyConstruct`` copies the language payload but not the VM
    attributes. The code object and its image are immutable, so the copy may
    share them safely. The module scope is replaced with the task's copy in the
    worker.
    """
    if getattr(function, 'external', None) is not None or getattr(function, 'data', None) is None:
        return function
    cloned = copy_for_task(function)
    for attribute in (
        "code", "vm_image", "vm_defaults", "vm_name", "is_async",
        "lambda_name", "type_parameters", "variadic", "variadic_index",
        "min_argc", "return_expr", "args", "data", "closure",
        "captured_scopes", "captured_this", "instance_method",
        "trait_qualifier", "vm_module_scope",
    ):
        if hasattr(function, attribute):
            setattr(cloned, attribute, getattr(function, attribute))
    return cloned


def _bind_task_closure(function: PowangFunction, scope) -> None:
    if scope is not None and getattr(function, 'closure', None) is not None:
        function.closure = {
            "variables": scope.variables,
            "functions": scope.functions,
            "ObjectTypes": scope.types,
        }


def _task_scope_for(function: PowangFunction, task_vm):
    original = getattr(function, 'vm_module_scope', None)
    if original is not None:
        copied = task_vm.module_scopes.get(original.name)
        if copied is not None:
            return copied
    return next(iter(task_vm.module_scopes.values()), None) or original


def create_lazy_function_task(vm, function: PowangFunction,
                              arguments: list[PowangAny], where: str) -> PowangTask:
    parent_state = get_state()
    pool = get_task_pool(parent_state)
    task_state = parent_state.clone_for_task()
    try:
        cloned_function = _copy_vm_function(function)
        cloned_arguments = [copy_for_task(argument) for argument in arguments]
    except BaseException:
        task_state.close()
        raise

    def work() -> PowangAny:
        from .dispatch import call_function_value
        task_vm = _task_vm(vm, task_state)
        module_scope = _task_scope_for(cloned_function, task_vm)
        if module_scope is not None:
            cloned_function.vm_module_scope = module_scope
            _bind_task_closure(cloned_function, module_scope)
        return call_function_value(
            task_vm, None, cloned_function, cloned_arguments, [], where,
            force_sync=True,
        )

    task = PowangTask(pool.next_id())
    task.status = 'pending'
    task.lazy_work = work
    return pool.register_lazy(task, task_state)


def create_lazy_method_task(vm, receiver: PowangObjectType, method_name: str,
                            candidate: PowangFunction,
                            arguments: list[PowangAny], where: str) -> PowangTask:
    parent_state = get_state()
    pool = get_task_pool(parent_state)
    task_state = parent_state.clone_for_task()
    try:
        cloned_receiver = copy_for_task(receiver)
        cloned_candidate = _copy_vm_function(candidate)
        cloned_arguments = [copy_for_task(argument) for argument in arguments]
    except BaseException:
        task_state.close()
        raise

    def work() -> PowangAny:
        from .dispatch import call_function_value
        task_vm = _task_vm(vm, task_state)
        scope = _task_scope_for(cloned_candidate, task_vm)
        if scope is not None:
            cloned_candidate.vm_module_scope = scope
            _bind_task_closure(cloned_candidate, scope)
        return call_function_value(
            task_vm, None, cloned_candidate, cloned_arguments, [], where,
            receiver=cloned_receiver,
            frame_name=f"{cloned_receiver.type_name}.{method_name}",
        )

    task = PowangTask(pool.next_id())
    task.status = 'pending'
    task.lazy_work = work
    return pool.register_lazy(task, task_state)


def create_lazy_static_task(vm, user_type: PowangObjectType, method_name: str,
                            candidate: PowangFunction,
                            arguments: list[PowangAny],
                            named: list[tuple[str, PowangAny]],
                            where: str) -> PowangTask:
    parent_state = get_state()
    pool = get_task_pool(parent_state)
    task_state = parent_state.clone_for_task()
    try:
        cloned_candidate = _copy_vm_function(candidate)
        cloned_arguments = [copy_for_task(argument) for argument in arguments]
        cloned_named = [
            (name, copy_for_task(value)) for name, value in named
        ]
    except BaseException:
        task_state.close()
        raise

    def work() -> PowangAny:
        from .dispatch import call_function_value
        task_vm = _task_vm(vm, task_state)
        scope = _task_scope_for(cloned_candidate, task_vm)
        if scope is not None:
            cloned_candidate.vm_module_scope = scope
            _bind_task_closure(cloned_candidate, scope)
        return call_function_value(
            task_vm, None, cloned_candidate, cloned_arguments, cloned_named,
            where, receiver=user_type, is_static=True,
            frame_name=f"{user_type.type_name}.{method_name}",
        )

    task = PowangTask(pool.next_id())
    task.status = 'pending'
    task.lazy_work = work
    return pool.register_lazy(task, task_state)


def create_lazy_site_task(vm, frame, site, raw_args: list[Any],
                          target: Optional[PowangAny] = None) -> PowangTask:
    from . import dispatch
    positional, named = dispatch.flatten_arguments(site, raw_args)
    if site.dispatch == "method" and target is not None:
        receiver = unwrap_for_task(target)
        if receiver.type == PowangModule.type:
            member = dispatch.getModuleMember(
                f"async module: {receiver.name}", receiver, site.name,
            )
            candidate = (
                dispatch.getFunctionCandidate(member, positional)
                if isinstance(member, list) else member
            )
            return create_lazy_function_task(
                vm, candidate, positional, f"async module: {receiver.name}",
            )
        if receiver.type in dispatch.NATIVE_METHOD_TYPES:
            return dispatch.call_native(vm, frame, site, raw_args)
        methods = dispatch._resolve_instance_method(
            receiver, site.name, site.trait_name, positional,
            f"async method: {site.name}",
        )
        candidate = dispatch.getFunctionCandidate(methods, positional)
        return create_lazy_method_task(
            vm, receiver, site.name, candidate, positional,
            f"async method: {site.name}",
        )
    if site.dispatch == "trait":
        if not positional:
            raise powang_throw(powang_error_format(
                'ARGUMENT', 'async trait call', 'missing receiver',
            ))
        receiver = unwrap_for_task(positional[0])
        arguments = positional[1:]
        trait_name = site.trait_name or ''
        trait = get_state().traits.get(trait_name)
        if trait is None:
            raise powang_throw(powang_error_format(
                'IMPLEMENTATION', 'async trait call', f"unknown trait '{trait_name}'",
            ))
        methods = receiver.getTraitMethods(trait_name, site.name)
        if methods is None:
            methods = receiver.getMethods(site.name, False)
        if methods is None:
            methods = trait.default_methods.get(site.name)
        if methods is None:
            raise powang_throw(powang_error_format(
                'IMPLEMENTATION', 'async trait call',
                f"trait '{trait_name}' has no implementation for method '{site.name}'",
            ))
        candidate = dispatch.getFunctionCandidate(methods, arguments)
        return create_lazy_method_task(
            vm, receiver, site.name, candidate, arguments,
            f"async trait call: {trait_name}.{site.name}",
        )
    if site.dispatch == "static":
        user_type = ScopeStack.get_ObjectType(site.type_name or "")
        if user_type is None:
            raise powang_throw(powang_error_identifier_not_found(
                f"async method: {site.name}", site.name,
            ))
        methods = user_type.getStaticMethods(site.name, False)
        if methods is None:
            raise powang_throw(powang_error_identifier_not_found(
                f"async method: {site.name}", site.name,
            ))
        candidate = dispatch.getFunctionCandidate(methods, positional + [value for _, value in named])
        return create_lazy_static_task(
            vm, user_type, site.name, candidate, positional, named,
            f"async method: {site.name}",
        )
    if site.dispatch == "module":
        if target is not None and target.type == PowangModule.type:
            member = dispatch.getModuleMember(
                f"async module: {target.name}", target, site.name,
            )
            candidate = (
                dispatch.getFunctionCandidate(member, positional)
                if isinstance(member, list) else member
            )
            return create_lazy_function_task(
                vm, candidate, positional, f"async module: {target.name}",
            )
    if site.dispatch == "value":
        callee = target
        if callee is not None and getattr(callee, 'type', None) == PowangFunction.type:
            return create_lazy_function_task(vm, callee, positional, "async call")
    functions = ScopeStack.get_functions(site.name)
    if functions is not None:
        candidate = dispatch.getFunctionCandidate(functions, positional)
        return create_lazy_function_task(vm, candidate, positional, f"async call: {site.name}")
    variable = ScopeStack.get_variable(site.name)
    if variable is not None and variable.type == PowangFunction.type:
        return create_lazy_function_task(vm, variable, positional, f"async call: {site.name}")
    if site.name in dispatch.BUILTINS:
        raise powang_throw(powang_error_format(
            'TASK', 'async call', 'builtins cannot be async', [
                f"call: {site.name}",
            ],
        ))
    raise powang_throw(powang_error_identifier_not_found(
        f"async call: {site.name}", site.name,
    ))


def unwrap_for_task(value: PowangAny) -> PowangAny:
    from ..runtime import unwrap_any_value
    return unwrap_any_value(value)


def _peek_target(site, raw_args: list[Any], frame) -> Optional[PowangAny]:
    ## The caller already popped the arguments but left the target below them.
    ## It passes the target through the receiver slot for module and value
    ## dispatch. This helper only exists for defensive fallbacks.
    return None


def create_worker_site_task(vm, frame, site, raw_args: list[Any],
                            receiver: Optional[PowangAny] = None) -> PowangTask:
    from . import dispatch
    positional, named = dispatch.flatten_arguments(site, raw_args)
    parent_state = get_state()
    pool = get_task_pool(parent_state)
    task_state = parent_state.clone_for_task()

    if site.dispatch == "spawn_static" and site.type_name:
        user_type = ScopeStack.get_ObjectType(site.type_name)
        if user_type is None:
            raise powang_throw(powang_error_identifier_not_found(
                f"spawn: {site.type_name}.{site.name}", site.name,
            ))
        static_methods = user_type.getStaticMethods(site.name, False)
        if static_methods is None:
            raise powang_throw(powang_error_identifier_not_found(
                f"spawn: {site.type_name}.{site.name}", site.name,
            ))
        candidate = dispatch.getFunctionCandidate(static_methods, positional)
        cloned_candidate = _copy_vm_function(candidate)
        work_args = [copy_for_task(argument) for argument in positional]

        def work() -> PowangAny:
            task_vm = _task_vm(vm, task_state)
            scope = _task_scope_for(cloned_candidate, task_vm)
            if scope is not None:
                cloned_candidate.vm_module_scope = scope
                _bind_task_closure(cloned_candidate, scope)
            return dispatch.call_function_value(
                task_vm, None, cloned_candidate, work_args, [],
                f"spawn: {site.type_name}.{site.name}",
                receiver=user_type, is_static=True, force_sync=True,
                frame_name=f"{site.type_name}.{site.name}",
            )

        return spawn_task(task_state, work, pool)

    if receiver is not None:
        receiver = unwrap_for_task(receiver)
        if receiver.type == PowangModule.type:
            member = dispatch.getModuleMember(
                f"spawn: {receiver.name}", receiver, site.name,
            )
            candidate = (
                dispatch.getFunctionCandidate(member, positional)
                if isinstance(member, list) else member
            )
            work_args = [copy_for_task(argument) for argument in positional]
            cloned_candidate = _copy_vm_function(candidate)

            def work() -> PowangAny:
                task_vm = _task_vm(vm, task_state)
                scope = _task_scope_for(cloned_candidate, task_vm)
                if scope is not None:
                    cloned_candidate.vm_module_scope = scope
                    _bind_task_closure(cloned_candidate, scope)
                return dispatch.call_function_value(
                    task_vm, None, cloned_candidate, work_args, [],
                    f"spawn: {receiver.name}", force_sync=True,
                )

            return spawn_task(task_state, work, pool)
        methods = dispatch._resolve_instance_method(
            receiver, site.name, None, positional, f"spawn method: {site.name}",
        )
        candidate = dispatch.getFunctionCandidate(methods, positional)
        cloned_receiver = copy_for_task(receiver)
        cloned_candidate = _copy_vm_function(candidate)
        work_args = [copy_for_task(argument) for argument in positional]

        def work() -> PowangAny:
            task_vm = _task_vm(vm, task_state)
            scope = _task_scope_for(cloned_candidate, task_vm)
            if scope is not None:
                cloned_candidate.vm_module_scope = scope
                _bind_task_closure(cloned_candidate, scope)
            return dispatch.call_function_value(
                task_vm, None, cloned_candidate, work_args, [],
                f"spawn method: {site.name}", receiver=cloned_receiver,
                frame_name=f"{cloned_receiver.type_name}.{site.name}",
            )

        return spawn_task(task_state, work, pool)

    functions = ScopeStack.get_functions(site.name)
    candidate = None
    if functions is not None:
        candidate = dispatch.getFunctionCandidate(functions, positional)
    elif site.name in get_state().external_functions:
        candidate = None
    elif (variable := ScopeStack.get_variable(site.name)) is not None \
            and variable.type == PowangFunction.type:
        candidate = variable
    if candidate is not None:
        cloned_candidate = _copy_vm_function(candidate)
        work_args = [copy_for_task(argument) for argument in positional]

        def work() -> PowangAny:
            task_vm = _task_vm(vm, task_state)
            scope = _task_scope_for(cloned_candidate, task_vm)
            if scope is not None:
                cloned_candidate.vm_module_scope = scope
                _bind_task_closure(cloned_candidate, scope)
            return dispatch.call_function_value(
                task_vm, None, cloned_candidate, work_args, [],
                f"spawn: {site.name}", force_sync=True,
            )

        return spawn_task(task_state, work, pool)

    if site.name in dispatch.BUILTINS:
        call_min_argc, call_max_argc, call_func = dispatch.BUILTINS[site.name]
        work_args = [copy_for_task(argument) for argument in positional]

        def work() -> PowangAny:
            return call_func(*work_args)

        return spawn_task(task_state, work, pool)

    raise powang_throw(powang_error_identifier_not_found(
        f"spawn: {site.name}", site.name,
    ))
