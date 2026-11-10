"""Declaration and construction semantics for the bytecode VM.

Type declarations, trait declarations, enum declarations, extern bindings,
destructuring and instantiation live here. They reuse the tree walker helpers
that define the exact language behavior: ``getUndefinedVariable``,
``assignWithChecks``, ``coerce_value_to_type_node``, ``explicitCast`` and the
error constructors. No new user visible text is introduced.
"""

from __future__ import annotations

from typing import Any, Optional

from ..powang_types import *
from ..lexer.token import ParserTokenType
from ..error import (
    powang_throw,
    powang_error_format,
    powang_error_identifier_not_found,
    powang_error_identifier_type,
    powang_error_invalid_cast,
    powang_error_type_match,
    powang_error_index_out_of_range,
)
from ..runtime import (
    CONSTRUCTOR_METHOD_NAME,
    NATI_TYPES,
    _ordered_named_constructor,
    _module_object_type,
    _construct_project,
    _private_access_allowed,
    assignWithChecks,
    areSameObjectType,
    coerce_value_to_type_node,
    copy_for_task,
    explicitCast,
    getFunctionCandidate,
    getUndefinedVariable,
    resolveNamedArguments,
    get_extern_module,
    _replace_type_parameters,
)
from ..state import get_state, TraitRuntimeInfo
from ..operator_traits import OPERATOR_TRAIT_NAMES
from ..scopestack import ScopeStack
from ..builtins.cast import explicitCastString
from .. import typespec as _typespec

from .dispatch import (
    _resolve_named,
    call_function_value,
    make_function,
)
from .values import SpreadValue, unwrap


def declare_type(vm, frame, type_index: int) -> PowangAny:
    info = vm.image.type_info(type_index)
    name = info.name
    if name in OPERATOR_TRAIT_NAMES:
        raise powang_throw(powang_error_format(
            'TYPE', 'type declaration',
            f"'{name}' is a built-in operator trait", [
                'reserved for operator overloading',
                'choose a different type name',
            ],
        ))
    if info.kind == "enum":
        return _declare_enum(frame, info)
    type_parameters = set(info.type_parameters or ())
    public_props: dict[str, PowangAny] = {}
    private_props: dict[str, PowangAny] = {}
    ScopeStack.push()
    try:
        for public, property_name, spec_index, _access in info.properties:
            declaration = vm.image.type_specs[spec_index]
            if isinstance(declaration, dict) and declaration.get("type") in {
                ParserTokenType.DECLARATION_UNDEFINED,
                ParserTokenType.DECLARATION_TYPED_VAR,
            }:
                from ..runtime import evaluateAstExpression
                evaluateAstExpression(declaration)
                value = ScopeStack.variables[-1].get(property_name)
                if value is None:
                    value = getUndefinedVariable("type declaration", {})
            else:
                type_inner = declaration.get("value") if isinstance(declaration, dict) else None
                if not isinstance(type_inner, dict):
                    type_inner = {"value": PowangAnyType.type, "weak": False, "const": False}
                value = getUndefinedVariable("type declaration", type_inner)
            if public:
                public_props[property_name] = value
            else:
                private_props[property_name] = value
    finally:
        ScopeStack.pop()
    public_meths: dict[str, list[PowangFunction]] = {}
    private_meths: dict[str, list[PowangFunction]] = {}
    public_static_meths: dict[str, list[PowangFunction]] = {}
    private_static_meths: dict[str, list[PowangFunction]] = {}
    trait_methods: dict[str, dict[str, list[PowangFunction]]] = {}
    for public, method_name, fn_index, qualifier, instance in info.methods:
        if fn_index < 0:
            continue
        function_info = vm.image.function_info(fn_index)
        function = make_function(function_info, vm.image)
        function.vm_module_scope = vm.current_module_scope()
        if isinstance(qualifier, str) and qualifier:
            trait_methods.setdefault(qualifier, {}).setdefault(method_name, []).append(function)
            continue
        is_instance = method_name == CONSTRUCTOR_METHOD_NAME or bool(instance)
        if is_instance:
            target = public_meths if public else private_meths
        else:
            target = public_static_meths if public else private_static_meths
        target.setdefault(method_name, []).append(function)
    new_type = PowangObjectType(
        public_props, private_props,
        public_meths, private_meths,
        public_static_meths, private_static_meths,
        trait_methods=trait_methods,
    )
    new_type.type_name = name
    ScopeStack.new_ObjectType(name, new_type)
    return new_type


def _declare_enum(frame, info) -> PowangAny:
    name = info.name
    variants = list(info.variants)
    enum_type = PowangObjectType(
        {'name': PowangString(variants[0] if variants else '')},
        {},
        {},
        {},
    )
    enum_type.type_name = name
    enum_type.is_enum = True
    ScopeStack.new_ObjectType(name, enum_type)
    variants_map: dict[PowangAny, PowangAny] = {}
    for variant_name in variants:
        instance = PowangObjectType({'name': PowangString(variant_name)}, {}, {}, {})
        instance.type_name = name
        instance.is_enum = True
        instance.defined = True
        variants_map[PowangString(variant_name)] = instance
    enum_value = PowangMap(variants_map)
    if 'module_scope' in frame.__dict__ or hasattr(frame, 'module_scope'):
        store = frame.module_scope.variables
        if name not in store:
            store.add_slot(name)
    ScopeStack.new_variable(name, enum_value)
    return enum_value


def declare_trait(vm, frame, trait_index: int) -> PowangAny:
    info = vm.image.trait_info(trait_index)
    if info.name in OPERATOR_TRAIT_NAMES:
        raise powang_throw(powang_error_format(
            'TRAIT', 'trait declaration',
            f"'{info.name}' is a built-in operator trait", [
                'choose a different trait name',
            ],
        ))
    trait = TraitRuntimeInfo(info.name)
    for property_name in info.properties:
        trait.properties.add(property_name)
    for method_name, fn_index, signature_only in info.methods:
        trait.declared_methods.add(method_name)
        if signature_only or fn_index < 0:
            trait.required_methods.add(method_name)
            continue
        function_info = vm.image.function_info(fn_index)
        function = make_function(function_info, vm.image)
        function.vm_module_scope = vm.current_module_scope()
        function.instance_method = True
        trait.default_methods.setdefault(method_name, []).append(function)
    get_state().traits[info.name] = trait
    return PowangNova()


def declare_extern(vm, frame, descriptor: dict) -> None:
    powang_node = descriptor.get("powang")
    python_name = descriptor.get("python")
    attributes = str(python_name).split('.')
    module_name = attributes[0]
    if module_name not in get_state().allowed_extern_modules:
        raise powang_throw(powang_error_format(
            'MODULE', "extern", 'Module is not allowed in the extern enviroment', [
                f'module: {module_name}'
            ]))
    extern_module = get_extern_module(module_name)
    extern = extern_module
    for attribute in attributes[1:]:
        extern = getattr(extern, attribute)
    from ..runtime import evaluateAstExpression
    extern_signature = evaluateAstExpression(powang_node)
    if isinstance(powang_node, dict) and powang_node.get('type') == ParserTokenType.DECLARATION_FUN:
        if extern_signature.type != PowangFunction.type:
            raise powang_throw(powang_error_format(
                'DEVELOPMENT', 'extern function',
                "Somehow you get here without a function",
            ))
        setattr(extern_signature, 'external', extern)
        identifier = powang_node.get('value', {}).get('identifier', {})
        name = identifier.get('value')
        if isinstance(name, str):
            get_state().external_functions[name] = (extern_signature, extern)
        return
    raise powang_throw(powang_error_format(
        'EXTERN', 'extern type',
        "extern type declarations are not supported yet", [
            f"python type: {python_name}"
        ],
    ))


def destructure(vm, frame, descriptor: dict, source_value: PowangAny) -> PowangAny:
    source = unwrap(source_value)
    entries = descriptor.get("entries") or []
    group_type = descriptor.get("group_type")
    group_reference = bool(descriptor.get("group_reference"))
    if source.type == PowangArray.type:
        for index, entry in enumerate(entries):
            if index >= len(source.data):
                raise powang_throw(powang_error_index_out_of_range(index, len(source.data)))
            reference = bool(entry.get("reference")) or group_reference
            if reference:
                value: PowangAny = PowangElementReference(source, index)
            else:
                value = source.data[index]
                type_node = entry.get("type") or group_type
                type_name = _type_node_name(type_node)
                if type_name in NATI_TYPES:
                    casted = explicitCast(type_name, value)
                    if casted is not None:
                        value = casted
                value = PowangCopyConstruct(value)
            _store_binding(frame, entry, descriptor, value)
        return source
    if source.type == PowangObjectType.type:
        for entry in entries:
            name = entry['name']
            property_value = source.getProperty(name, False)
            if property_value is None:
                raise powang_throw(powang_error_identifier_not_found(
                    'destructure declaration', name,
                ))
            reference = bool(entry.get("reference")) or group_reference
            if reference:
                value = PowangPropertyReference(source, name)
            else:
                value = property_value
                type_node = entry.get("type") or group_type
                type_name = _type_node_name(type_node)
                if type_name in NATI_TYPES:
                    casted = explicitCast(type_name, value)
                    if casted is not None:
                        value = casted
                value = PowangCopyConstruct(value)
            _store_binding(frame, entry, descriptor, value)
        return source
    raise powang_throw(powang_error_type_match('destructure declaration', 'array or object', source.type))


def _type_node_name(type_node: Any) -> Optional[str]:
    if not isinstance(type_node, dict):
        return None
    inner = type_node.get("value")
    if isinstance(inner, dict):
        name = inner.get("value")
        return name if isinstance(name, str) else None
    return None


def _store_binding(frame, entry: dict, descriptor: dict, value: PowangAny) -> None:
    slot = entry.get("slot", -1)
    if isinstance(slot, int) and slot >= 0:
        frame.locals.set_at(slot, value)
        return
    name = entry.get("name")
    if isinstance(name, str):
        frame.locals[name] = value


def _argument_groups(site, raw_args: list[Any]) -> tuple[list[PowangAny], list[tuple[str, PowangAny]], list[tuple[PowangAny, PowangAny]]]:
    positional: list[PowangAny] = []
    named: list[tuple[str, PowangAny]] = []
    pairs: list[tuple[PowangAny, PowangAny]] = []
    kinds = site.argument_kinds
    names = site.argument_names
    argument_index = 0
    stack_index = 0
    while argument_index < len(kinds) and stack_index < len(raw_args):
        kind = kinds[argument_index]
        name = names[argument_index] if argument_index < len(names) else ""
        raw = raw_args[stack_index]
        if isinstance(raw, SpreadValue):
            from ..runtime import _spread_values
            positional.extend(_spread_values(raw.value))
            stack_index += 1
            argument_index += 1
            continue
        if kind == "pair":
            if stack_index + 1 >= len(raw_args):
                raise CompileErrorLike("Instantiation pair is missing its value")
            pairs.append((raw, raw_args[stack_index + 1]))
            stack_index += 2
            argument_index += 1
            continue
        if kind == "named":
            named.append((name, raw))
        else:
            positional.append(raw)
        stack_index += 1
        argument_index += 1
    while stack_index < len(raw_args):
        positional.append(raw_args[stack_index])
        stack_index += 1
    return positional, named, pairs


class CompileErrorLike(RuntimeError):
    pass


def instantiate(vm, frame, site, raw_args: list[Any]) -> PowangAny:
    type_ref = site.callee_ast if isinstance(site.callee_ast, dict) else {}
    type_name = type_ref.get('name')
    if not isinstance(type_name, str):
        raise powang_throw(powang_error_format('TYPE', 'instantiation', 'Invalid instantiation node'))
    type_parameters = [
        parameter for parameter in type_ref.get('type_parameters', [])
        if isinstance(parameter, dict)
    ]
    variadic = bool(type_ref.get('variadic'))
    where = 'instantiation'
    positional, named, pairs = _argument_groups(site, raw_args)
    named_form = any(kind == "named" for kind in site.argument_kinds)

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

    if type_name == PowangProject.type:
        return _construct_project(where, positional, named, named_form)

    if type_name in NATI_TYPES:
        if named_form:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, "Named arguments are only supported for user type constructors",
            ))
        if type_name == PowangMap.type:
            result = PowangMap()
            for pair in pairs:
                result.data[pair[0]] = pair[1]
            for argument in positional:
                raise powang_throw(powang_error_format(
                    'TYPE', where, "map construction requires key >> value entries",
                ))
            return result
        if pairs:
            raise powang_throw(powang_error_format(
                'TYPE', where, "map construction requires key >> value entries",
            ))
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
                                'TYPE', where, "tuple construction arity does not match its type", [
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
                                'TYPE', where, "tuple construction arity does not match its type", [
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
    instance_type = None
    if user_type is None and '.' in type_name:
        user_type, _qualified = _module_object_type(type_name)
        if user_type is not None:
            instance_type = PowangCopyConstructObjectType(user_type)
    if user_type is None:
        raise powang_throw(powang_error_identifier_type(where, type_name))
    if instance_type is None:
        instance_type = ScopeStack.get_existingObjectType(type_name)
    constructors = instance_type.getConstructors()
    if named_form:
        if positional:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, "Named and positional arguments cannot be mixed",
            ))
        candidate, arguments = _ordered_named_constructor_vm(vm, constructors, named, where)
    else:
        if not constructors:
            raise powang_throw(powang_error_format(
                'ARGUMENT', where, f"Type '{type_name}' has no constructor",
            ))
        candidate = getFunctionCandidate(constructors, positional)
        arguments = positional
    return call_function_value(
        vm, frame, candidate, arguments, [], where,
        receiver=instance_type,
        frame_name=f"{instance_type.type_name}.{CONSTRUCTOR_METHOD_NAME}",
    )


def _parameter_names(candidate: PowangFunction) -> list[str]:
    return [
        argument['value']['identifier']['value']
        for argument in candidate.args
        if isinstance(argument, dict) and isinstance(argument.get('value'), dict)
        and isinstance(argument['value'].get('identifier'), dict)
    ]


def _ordered_named_constructor_vm(vm, constructors: list[PowangFunction],
                                  named: list[tuple[str, PowangAny]],
                                  where: str) -> tuple[PowangFunction, list[PowangAny]]:
    if not constructors:
        raise powang_throw(powang_error_format('ARGUMENT', where, "Type has no constructor"))
    provided = {name for name, _ in named}
    compatible: list[PowangFunction] = []
    for candidate in constructors:
        names = _parameter_names(candidate)
        if not provided.issubset(names):
            continue
        if any(names[index] not in provided for index in range(candidate.min_argc)):
            continue
        compatible.append(candidate)
    if not compatible:
        closest = max(constructors, key=lambda candidate: len(
            provided.intersection(_parameter_names(candidate))
        ))
        _resolve_named(closest, [], named, where, vm)
        raise powang_throw(powang_error_format('ARGUMENT', where, 'Invalid named constructor call'))
    resolved_by_candidate: list[list[PowangAny]] = []
    first_error = None
    for candidate in compatible:
        try:
            resolved_by_candidate.append(_resolve_named(candidate, [], named, where, vm))
        except PowangError as error:
            if first_error is None:
                first_error = error
            continue
    if not resolved_by_candidate:
        if first_error is not None:
            raise first_error
        raise powang_throw(powang_error_format('ARGUMENT', where, 'Invalid named constructor call'))
    candidate = compatible[0]
    resolved = resolved_by_candidate[0]
    if len(compatible) > 1:
        candidate = getFunctionCandidate(compatible, resolved)
        resolved = _resolve_named(candidate, [], named, where, vm)
    return candidate, resolved


def make_error(descriptor: dict, arguments: list[PowangAny]) -> PowangAny:
    mode = descriptor.get("mode", "raise")
    has_kind = bool(descriptor.get("has_kind"))
    where = descriptor.get("where", "builtin: error")
    required = 2 if has_kind else 1
    if len(arguments) < required:
        raise powang_throw(powang_error_format(
            'ARGUMENT', where, 'not enought arguments',
        ))
    if has_kind:
        kind_value = arguments[0]
        message_value = arguments[1]
        details = arguments[2:]
        if kind_value.type != PowangString.type:
            raise powang_throw(powang_error_type_match(
                'builtin: fail, kind', PowangString.type, kind_value.type,
            ))
        error_kind = kind_value.data
    else:
        message_value = arguments[0]
        details = arguments[1:]
        error_kind = "USER"
    if message_value.type != PowangString.type:
        raise powang_throw(powang_error_type_match(
            'builtin: error, message' if not has_kind else 'builtin: fail, message',
            PowangString.type, message_value.type,
        ))
    for index, detail in enumerate(details):
        if detail.type != PowangString.type:
            raise powang_throw(powang_error_type_match(
                'builtin: error, argument' if not has_kind else 'builtin: fail, argument',
                PowangString.type, detail.type,
            ))
    created = powang_error_format(
        error_kind, where, message_value.data,
        [detail.data for detail in details],
    )
    if mode == "value":
        return PowangErrorValue.from_error(created)
    raise powang_throw(created)
