"""The bytecode execution loop.

The VM owns the frame stack, the operand stacks, the module stores, the type
and trait registries and the error unwinder. Opcode handlers delegate value
level semantics to the shared tree walker helpers so the two engines cannot
drift.

The interpreter never parses or checks source. It consumes a ``ProgramImage``
that the compiler produced and assumes the verifier accepted it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..powang_types import *
from ..error import (
    PowangError,
    powang_throw,
    powang_error_format,
    powang_error_identifier_not_found,
    powang_error_syntax,
    powang_error_type_match,
    powang_error_invalid_cast,
    powang_error_undefined_reference,
    powang_error_index_out_of_range,
    powang_error_unsupported_operation,
    powang_error_type_match as _type_match,
    powang_error_invalid_type_for_prefix_operator,
)
from ..runtime import (
    BreakSignal,
    ContinueSignal,
    CONSTRUCTOR_METHOD_NAME,
    NATI_TYPES,
    _attach_frames,
    _call_comparison_operator,
    _call_operator_method,
    _private_access_allowed,
    _find_default_trait_method,
    _object_satisfies_trait,
    _runtime_reference_type,
    assignWithChecks,
    areSameObjectType,
    builtin_size,
    cast_to_union_type,
    checkObjectTypes,
    coerce_value_to_type_node,
    copy_for_task,
    evaluateAstExpression,
    explicitCast,
    getErrorProperty,
    getUndefinedVariable,
    get_module_loader,
    getCastTypeName,
    moduleMemberValue,
    performOperation,
    runtime_type_matches,
    slice_value,
    unwrap_any_value,
    value_type_spec,
    _spread_values,
)
from ..scopestack import ScopeStack, ScopeType
from ..state import Frame, get_state
from ..operator_traits import (
    BINARY_OPERATOR_TRAITS,
    COMPARISON_OPERATOR_TRAIT,
    COMPARISON_OPERATORS,
    OPERATOR_TRAITS,
    UNARY_OPERATOR_TRAITS,
    trait_method,
)
from .. import typespec as _typespec
from ..builtins import BUILTINS
from ..builtins.cast import explicitCastInteger, explicitCastNumber, explicitCastString
from ..builtins.native_methods import NATIVE_METHOD_TYPES, call_native_method
from ..builtins.tasks import (
    builtin_wait,
    check_cancellation,
    run_lazy_task,
)
from ..lexer.token import LexerTokenType, ParserTokenType, TokenToString, DictRepr

from .frames import (
    HandlerEntry,
    LocalStore,
    VMFrame,
    publish_local,
    sync_local,
)
from .image import CodeObject, ExceptionEntry, ProgramImage
from .values import (
    SpreadValue,
    constant_to_value,
    copy_value,
    is_defined,
    is_nova,
    is_weak,
    spread_values,
    tag_of,
    truthy,
    unwrap,
)
from .opcodes import BY_OPCODE, OpcodeSpec
from .trace import TextTraceSink, TraceEvent, TraceSink
from . import dispatch


class VMError(RuntimeError):
    """Internal VM failure that is not a language error."""


@dataclass
class VMRunOptions:
    trace: bool = False
    trace_sink: Any = None
    verify: bool = True
    trusted: bool = False
    instruction_budget: int = 0
    max_frames: int = 900
    cache_dir: Optional[str] = None


@dataclass
class _Decoded:
    offset: int
    spec: OpcodeSpec
    operands: dict[str, Any]
    next_offset: int
    index: int
    span_index: int


class _Skip:
    """Internal marker for an interpolated part with no string form."""

    __slots__ = ()


_SKIP = _Skip()


class VMIterator:
    """Internal iterator state for ITER_NEW and ITER_NEXT."""

    __slots__ = ("values", "index")

    def __init__(self, values: list[PowangAny]):
        self.values = values
        self.index = 0


_PROPERTY_NAMES = (
    "kind", "message", "details", "where", "line", "column", "cause", "frames",
)


class VM:
    """One execution session for a program image."""

    def __init__(self, state, image: ProgramImage,
                 options: Optional[VMRunOptions] = None):
        self.state = state
        self.image = image
        self.options = options or VMRunOptions()
        self.frames: list[VMFrame] = []
        self.module_scopes: dict[int, Any] = {}
        self._module_stack: list[Any] = []
        self._siblings: dict[int, "VM"] = {id(image): self}
        self._decoded: dict[int, dict[int, _Decoded]] = {}
        self._decoded_sizes: dict[int, int] = {}
        self.instruction_count = 0
        self._budget = [0]
        self._trace_sink: Optional[TraceSink] = None
        if self.options.trace:
            self._trace_sink = self.options.trace_sink or TextTraceSink()

    # ------------------------------------------------------------- decoding
    def decode(self, code: CodeObject) -> dict[int, _Decoded]:
        key = id(code)
        cached = self._decoded.get(key)
        if cached is not None:
            return cached
        from .opcodes import decode_instruction
        table: dict[int, _Decoded] = {}
        offset = 0
        index = 0
        data = code.bytecode
        span_table = code.span_table
        while offset < len(data):
            spec, operands, next_offset = decode_instruction(data, offset)
            span_index = span_table[index] if index < len(span_table) else 0
            table[offset] = _Decoded(offset, spec, operands, next_offset, index, span_index)
            offset = next_offset
            index += 1
        self._decoded[key] = table
        self._decoded_sizes[key] = index
        return table

    def instruction_size(self, code: CodeObject) -> int:
        self.decode(code)
        return self._decoded_sizes.get(id(code), 0)

    # ------------------------------------------------------------- execution
    def sibling(self, image: ProgramImage) -> "VM":
        """Return a VM for another program image that shares this state.

        Imported modules are compiled into their own image. A function from
        that image must execute with the tables of its own image, so calls
        switch to a sibling VM. The state and the options are shared.
        """
        if image is self.image:
            return self
        key = id(image)
        existing = self._siblings.get(key)
        if existing is None:
            existing = VM(self.state, image, self.options)
            existing._siblings = self._siblings
            existing._budget = self._budget
            self._siblings[key] = existing
        return existing

    def current_module_scope(self):
        if self._module_stack:
            return self._module_stack[-1]
        return None

    def run(self) -> PowangAny:
        module = self.image.module_info(self.image.entry_module)
        code = self.image.code(module.code_index)
        scope = self.module_scopes.get(self.image.entry_module)
        if scope is None:
            from .modules import ModuleScope
            scope = ModuleScope(
                name=module.name,
                path=module.path,
                variables=LocalStore(code.local_names),
                functions={},
                types={},
                wildcards={},
            )
            self.module_scopes[self.image.entry_module] = scope
        return self.run_module_code(code, scope)

    def run_module_code(self, code: CodeObject, scope) -> PowangAny:
        """Run a module body with the scope stacks already prepared."""
        saved = ScopeStack.save_scopes()
        ScopeStack.reset_scopes()
        ScopeStack.push(ScopeType.GLOBAL)
        ScopeStack.variables[-1] = scope.variables
        ScopeStack.functions[-1] = scope.functions
        ScopeStack.ObjectTypes[-1] = scope.types
        ScopeStack.wildcard_sources[-1] = scope.wildcards
        self._module_stack.append(scope)
        state_token = None
        try:
            frame = VMFrame(
                code, scope.variables, scope.functions, scope.types,
                scope.wildcards, scope, receiver=None, closure=None,
                task=None, is_function=False,
            )
            return self._run_frame(frame, base_pushed=True)
        finally:
            self._module_stack.pop()
            ScopeStack.restore_scopes(saved)

    def run_code(self, code: CodeObject, arguments: list[PowangAny],
                 *, receiver: Optional[PowangObjectType] = None,
                 closure: Any = None, task: Optional[PowangTask] = None,
                 is_function: bool = True, frame_name: Optional[str] = None,
                 module_scope: Any = None, default_frame: bool = False,
                 type_check_function: Optional[PowangFunction] = None,
                 functions: Optional[dict] = None,
                 types: Optional[dict] = None,
                 wildcards: Optional[dict] = None) -> PowangAny:
        if len(self.frames) >= self.options.max_frames:
            raise powang_throw(powang_error_format(
                'RECURSION', 'function call', 'Maximum frame depth exceeded', [
                    f"depth limit: {self.options.max_frames}",
                ],
            ))
        scope = module_scope or self.current_module_scope()
        if scope is None:
            from .modules import ModuleScope
            scope = ModuleScope(
                name=code.name, path="", variables=LocalStore(code.local_names),
                functions={}, types={}, wildcards={},
            )
        locals_store = LocalStore(code.local_names)
        frame = VMFrame(
            code, locals_store,
            functions if functions is not None else {},
            types if types is not None else {},
            wildcards if wildcards is not None else {},
            scope,
            receiver=receiver, closure=closure, task=task,
            is_function=is_function,
        )
        frame.name = frame_name or code.name
        return self._run_frame(
            frame, base_pushed=False,
            bind_function=type_check_function,
            bind_arguments=arguments,
            bind_name=frame_name or code.name,
        )

    def _run_frame(self, frame: VMFrame, *, base_pushed: bool,
                   bind_function=None,
                   bind_arguments=None,
                   bind_name: str = "") -> PowangAny:
        saved = None
        pushed_base = False
        closure = frame.closure
        if not base_pushed:
            saved = ScopeStack.save_scopes()
            if isinstance(closure, tuple) and len(closure) == 5:
                ScopeStack.restore_scopes(closure)
            elif isinstance(closure, dict):
                ScopeStack.reset_scopes()
                ScopeStack.push_captured(
                    closure.get('variables', {}),
                    closure.get('functions', {}),
                    closure.get('ObjectTypes', {}),
                )
            elif frame.module_scope is not None:
                module_variables = getattr(frame.module_scope, 'variables', None)
                if module_variables is not None and not any(
                    scope is module_variables for scope in ScopeStack.variables
                ):
                    ScopeStack.reset_scopes()
                    ScopeStack.push_captured(
                        module_variables,
                        getattr(frame.module_scope, 'functions', {}),
                        getattr(frame.module_scope, 'types', {}),
                    )
            ## A function with no closure and no captures uses the caller's
            ## scopes, exactly like the tree walker. This keeps nested named
            ## functions and default argument expressions dynamic.
            ScopeStack.push_captured(frame.locals, frame.functions, frame.types)
            ScopeStack.wildcard_sources[-1] = frame.wildcards
            pushed_base = True
        relative = self.state.paths.get('RELATIVE')
        source = str(relative) if relative is not None else ""
        frame_name = getattr(frame, 'name', None) or frame.code.name
        if bind_function is not None:
            dispatch.bind_parameters(
                self, frame, bind_function, list(bind_arguments or []),
                bind_name or frame.code.name,
            )
        line = column = None
        if self.frames:
            caller = self.frames[-1]
            if 0 <= caller.span_index < len(caller.code.spans):
                span = caller.code.spans[caller.span_index]
                if span.start_line:
                    line = span.start_line
                    column = span.start_column
        if frame.is_function:
            self.state.call_frames.append(Frame(frame_name, source or None, line, column))
            if self._trace_sink is not None:
                self._emit_trace("call", frame, None, frame_name)
        self.frames.append(frame)
        try:
            value = self._execute(frame)
            if self._trace_sink is not None and frame.is_function:
                self._emit_trace("return", frame, None, frame_name)
            return value
        except PowangError as error:
            _attach_frames(error)
            if self._trace_sink is not None:
                self._emit_trace("error", frame, None, str(error))
            raise
        finally:
            self.frames.pop()
            if frame.is_function:
                self.state.call_frames.pop()
            if pushed_base:
                ScopeStack.pop()
            if saved is not None:
                ScopeStack.restore_scopes(saved)

    # --------------------------------------------------------------- helpers
    def call_function(self, function: PowangFunction,
                      arguments: list[PowangAny],
                      where: str = "function call",
                      *, receiver: Optional[PowangObjectType] = None,
                      is_static: bool = False,
                      frame_name: Optional[str] = None) -> PowangAny:
        return dispatch.call_function_value(
            self, None, function, arguments, [], where,
            receiver=receiver, is_static=is_static, frame_name=frame_name,
        )

    def _position(self, frame: VMFrame, span_index: int) -> tuple[int, int]:
        code = frame.code
        if 0 <= span_index < len(code.spans):
            span = code.spans[span_index]
            return (span.start_line, span.start_column)
        return (0, 0)

    def _where(self, frame: VMFrame, span_index: int,
               opcode: str | None = None) -> str:
        if opcode is not None:
            mapped = _WHERE_BY_OPCODE.get(opcode)
            if mapped is not None:
                return mapped
        line, column = self._position(frame, span_index)
        return f"line {line}:{column}"

    def _emit_trace(self, kind: str, frame: VMFrame, decoded: Optional[_Decoded],
                    detail: str = "") -> None:
        if self._trace_sink is None:
            return
        line = column = 0
        if 0 <= frame.span_index < len(frame.code.spans):
            span = frame.code.spans[frame.span_index]
            line, column = span.start_line, span.start_column
        self._trace_sink.emit(TraceEvent(
            kind=kind,
            frame_name=frame.name,
            ip=decoded.offset if decoded is not None else frame.ip,
            opcode=decoded.spec.name if decoded is not None else "",
            stack_depth=len(frame.stack),
            line=line,
            column=column,
            detail=detail,
        ))

    def _exception_entry_for(self, code: CodeObject, start_ip: int) -> Optional[ExceptionEntry]:
        for entry in code.exception_table:
            if entry.start_ip == start_ip:
                return entry
        return None

    def _handle_error(self, frame: VMFrame, error: PowangError,
                      fault_ip: int) -> bool:
        """Route one error to a handler. Return False when no handler exists."""
        for index in range(len(frame.handlers) - 1, -1, -1):
            handler = frame.handlers[index]
            if handler.state == "finally":
                continue
            if not (handler.start_ip <= fault_ip < handler.end_ip):
                continue
            while len(ScopeStack.variables) > handler.scope_depth:
                _pop_block_scope(frame)
            if handler.catch_ip >= 0 and handler.state == "active":
                del frame.handlers[index + 1:]
                frame.stack[:] = frame.stack[:handler.stack_depth]
                handler.state = "catch"
                frame.pending_error = None
                frame.pending_return = None
                frame.transfer = None
                frame.ip = handler.catch_ip
                frame.stack.append(PowangErrorValue.from_error(error))
                return True
            if handler.finally_ip >= 0:
                del frame.handlers[index + 1:]
                frame.stack[:] = frame.stack[:handler.stack_depth]
                handler.state = "finally"
                frame.pending_error = error
                frame.pending_return = None
                frame.transfer = None
                frame.ip = handler.finally_ip
                return True
            ## The handler cannot route this error. Drop it and keep looking
            ## for an enclosing handler.
            del frame.handlers[index]
        return False

    # ---------------------------------------------------------------- execute
    def _execute(self, frame: VMFrame) -> PowangAny:
        decoded = self.decode(frame.code)
        stack = frame.stack
        while True:
            current = decoded.get(frame.ip)
            if current is None:
                raise VMError(f"instruction pointer {frame.ip} is not an instruction boundary")
            frame.span_index = current.span_index
            frame.ip = current.next_offset
            self._budget[0] += 1
            self.instruction_count = self._budget[0]
            if self.options.instruction_budget and \
                    self._budget[0] > self.options.instruction_budget:
                raise powang_throw(powang_error_format(
                    'BUDGET', 'vm', 'Instruction budget exceeded', [
                        f"budget: {self.options.instruction_budget}",
                    ],
                ))
            if self._trace_sink is not None:
                self._emit_trace("instruction", frame, current)
            name = current.spec.name
            operands = current.operands
            try:
                result = self._dispatch(name, frame, operands, current)
            except PowangError as error:
                if self._handle_error(frame, error, current.offset):
                    continue
                raise
            except RecursionError:
                raise PowangError(
                    'RECURSION', 'Maximum evaluation depth exceeded', [
                        f"depth limit: {self.options.max_frames}",
                        "check for unbounded or deeply nested recursion",
                    ],
                ) from None
            if result is not _NO_RETURN:
                return result

    def _dispatch(self, name: str, frame: VMFrame, operands: dict[str, Any],
                  current: _Decoded) -> Any:
        stack = frame.stack
        image = self.image
        code = frame.code
        span_index = current.span_index
        where = self._where(frame, span_index, name)
        position = self._position(frame, span_index)

        if name == "NOP":
            return _NO_RETURN
        if name == "POP":
            stack.pop()
            return _NO_RETURN
        if name == "DUP":
            stack.append(stack[-1])
            return _NO_RETURN
        if name == "DUP2":
            first = stack[-2]
            second = stack[-1]
            stack.append(first)
            stack.append(second)
            return _NO_RETURN
        if name == "SWAP":
            stack[-1], stack[-2] = stack[-2], stack[-1]
            return _NO_RETURN
        if name == "ROT3":
            a, b, c = stack[-3], stack[-2], stack[-1]
            stack[-3:] = [b, c, a]
            return _NO_RETURN
        if name == "ROT":
            count = int(operands["count"])
            if count <= 0:
                return _NO_RETURN
            window = stack[-count:]
            stack[-count:] = [window[-1]] + window[:-1]
            return _NO_RETURN
        if name == "LOAD_NOVA":
            stack.append(PowangNova())
            return _NO_RETURN
        if name == "LOAD_UNDEF":
            value = PowangAnyType()
            value.defined = False
            value.any = PowangAnyType.type
            stack.append(value)
            return _NO_RETURN
        if name == "LOAD_TRUE":
            stack.append(PowangBoolean(True))
            return _NO_RETURN
        if name == "LOAD_FALSE":
            stack.append(PowangBoolean(False))
            return _NO_RETURN
        if name == "LOAD_INT":
            stack.append(PowangInteger(int(operands["value"])))
            return _NO_RETURN
        if name == "LOAD_BIGINT":
            constant = code.constants[int(operands["const"])]
            stack.append(PowangInteger(int(constant.value)))
            return _NO_RETURN
        if name == "LOAD_NUM":
            stack.append(PowangNumber(float(operands["value"])))
            return _NO_RETURN
        if name == "LOAD_CHAR":
            stack.append(PowangChar(chr(int(operands["value"]))))
            return _NO_RETURN
        if name == "LOAD_STR":
            stack.append(PowangString(str(code.constants[int(operands["const"])].value)))
            return _NO_RETURN
        if name == "LOAD_CONST":
            stack.append(constant_to_value(code.constants[int(operands["const"])]))
            return _NO_RETURN

        if name == "DECLARE_LOCAL":
            slot = int(operands["slot"])
            spec_index = int(operands["spec"])
            flags = int(operands["flags"])
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            display = code.local_names[slot]
            existing = frame.locals.value_at(slot)
            if not (flags & 1) and existing.defined:
                raise powang_throw(powang_error_format(
                    'REDEFINE', 'declaration undefined', "Cannot redefine variables", [
                        f"redefined: {display}"
                    ]))
            value = getUndefinedVariable('declaration undefined', type_inner or {})
            frame.locals.set_at(slot, value)
            publish_local(frame, slot, value)
            stack.append(value)
            return _NO_RETURN
        if name == "DECLARE_GLOBAL":
            name_id = int(operands["name"])
            spec_index = int(operands["spec"])
            flags = int(operands["flags"])
            global_name = image.global_names[name_id]
            module_store = frame.module_scope.variables
            existing = module_store.get(global_name)
            if not (flags & 1) and existing is not None and existing.defined:
                raise powang_throw(powang_error_format(
                    'REDEFINE', 'declaration undefined', "Cannot redefine variables", [
                        f"redefined: {global_name}"
                    ]))
            _ensure_store_name(module_store, global_name)
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            value = getUndefinedVariable('declaration undefined', type_inner or {})
            module_store[global_name] = value
            stack.append(value)
            return _NO_RETURN
        if name == "DECLARE_TYPED":
            slot = int(operands["slot"])
            spec_index = int(operands["spec"])
            value = stack.pop()
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            display = code.local_names[slot]
            existing = frame.locals.value_at(slot)
            if existing.defined:
                raise powang_throw(powang_error_format(
                    'REDEFINE', 'declaration typed var', "Cannot redefine variables", [
                        f"redefined: {display}"
                    ]))
            target = getUndefinedVariable('declaration typed var', type_inner or {})
            typed_value = assignWithChecks('declaration typed var', target, value, False)
            frame.locals.set_at(slot, typed_value)
            publish_local(frame, slot, typed_value)
            stack.append(typed_value)
            return _NO_RETURN
        if name == "DECLARE_INFER":
            slot = int(operands["slot"])
            value = stack.pop()
            inferred = _infer_declaration(value, 'declaration interpret')
            frame.locals.set_at(slot, inferred)
            publish_local(frame, slot, inferred)
            stack.append(inferred)
            return _NO_RETURN
        if name == "DECLARE_TYPED_GLOBAL":
            name_id = int(operands["name"])
            spec_index = int(operands["spec"])
            value = stack.pop()
            global_name = image.global_names[name_id]
            module_store = frame.module_scope.variables
            _ensure_store_name(module_store, global_name)
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            target = getUndefinedVariable('declaration typed var', type_inner or {})
            typed_value = assignWithChecks('declaration typed var', target, value, False)
            module_store[global_name] = typed_value
            stack.append(typed_value)
            return _NO_RETURN
        if name == "DECLARE_INFER_GLOBAL":
            name_id = int(operands["name"])
            value = stack.pop()
            global_name = image.global_names[name_id]
            inferred = _infer_declaration(value, 'declaration interpret')
            _ensure_store_name(frame.module_scope.variables, global_name)
            frame.module_scope.variables[global_name] = inferred
            stack.append(inferred)
            return _NO_RETURN
        if name == "DECLARE_UNDEFINED_GLOBAL":
            name_id = int(operands["name"])
            spec_index = int(operands["spec"])
            flags = int(operands["flags"])
            global_name = image.global_names[name_id]
            module_store = frame.module_scope.variables
            existing = module_store.get(global_name)
            if not (flags & 1) and existing is not None and existing.defined:
                raise powang_throw(powang_error_format(
                    'REDEFINE', 'declaration undefined', "Cannot redefine variables", [
                        f"redefined: {global_name}"
                    ]))
            _ensure_store_name(module_store, global_name)
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            value = getUndefinedVariable('declaration undefined', type_inner or {})
            module_store[global_name] = value
            stack.append(value)
            return _NO_RETURN
        if name == "DESTRUCTURE":
            descriptor = code.constants[int(operands["descriptor"])].value
            source_slot = int(operands["source_slot"])
            source = frame.locals.value_at(source_slot)
            from .declarations import destructure
            result = destructure(self, frame, descriptor, source)
            stack.append(result)
            return _NO_RETURN
        if name == "DECLARE_FUNCTION":
            fn_index = int(operands["function"])
            function = _make_function(self, fn_index)
            _declare_function(frame, function)
            stack.append(function)
            return _NO_RETURN
        if name == "MAKE_FUNCTION":
            fn_index = int(operands["function"])
            function = _make_function(self, fn_index)
            stack.append(function)
            return _NO_RETURN
        if name == "DECLARE_TYPE":
            from .declarations import declare_type
            value = declare_type(self, frame, int(operands["type"]))
            stack.append(value)
            return _NO_RETURN
        if name == "DECLARE_TRAIT":
            from .declarations import declare_trait
            declare_trait(self, frame, int(operands["trait"]))
            return _NO_RETURN
        if name == "DECLARE_EXTERN":
            descriptor = code.constants[int(operands["extern"])].value
            from .declarations import declare_extern
            declare_extern(self, frame, descriptor)
            return _NO_RETURN

        if name == "LOAD_LOCAL":
            slot = int(operands["slot"])
            value = frame.locals.value_at(slot)
            if value.type == PowangReference.type:
                value = value.get()
            stack.append(value)
            return _NO_RETURN
        if name == "LOAD_RAW":
            slot = int(operands["slot"])
            stack.append(frame.locals.value_at(slot))
            return _NO_RETURN
        if name == "STORE_LOCAL":
            slot = int(operands["slot"])
            stored = copy_value(stack.pop())
            frame.locals.set_at(slot, stored)
            sync_local(frame, slot, stored)
            return _NO_RETURN
        if name == "STORE_RAW":
            slot = int(operands["slot"])
            stored = stack.pop()
            frame.locals.set_at(slot, stored)
            sync_local(frame, slot, stored)
            return _NO_RETURN
        if name == "ASSIGN_LOCAL":
            slot = int(operands["slot"])
            value = stack.pop()
            _assign_slot(frame, slot, value, where)
            sync_local(frame, slot, frame.locals.value_at(slot))
            return _NO_RETURN
        if name == "LOAD_GLOBAL":
            global_name = image.global_names[int(operands["name"])]
            stack.append(_load_from_store(frame.module_scope.variables, global_name, where))
            return _NO_RETURN
        if name == "STORE_GLOBAL":
            global_name = image.global_names[int(operands["name"])]
            _ensure_store_name(frame.module_scope.variables, global_name)
            frame.module_scope.variables[global_name] = copy_value(stack.pop())
            return _NO_RETURN
        if name == "LOAD_NAME":
            global_name = image.global_names[int(operands["name"])]
            stack.append(_load_name(global_name, where, frame))
            return _NO_RETURN
        if name == "LOAD_FREE":
            global_name = image.global_names[int(operands["name"])]
            stack.append(_load_free(global_name, where, frame))
            return _NO_RETURN
        if name == "SCOPE_PUSH":
            ScopeStack.push()
            return _NO_RETURN
        if name == "SCOPE_POP":
            _pop_block_scope(frame)
            return _NO_RETURN
        if name == "STORE_NAME":
            global_name = image.global_names[int(operands["name"])]
            _store_name(global_name, copy_value(stack.pop()), where)
            return _NO_RETURN
        if name == "ASSIGN_NAME":
            global_name = image.global_names[int(operands["name"])]
            _assign_name(global_name, stack.pop(), where)
            return _NO_RETURN
        if name == "LOAD_CAPTURE":
            index = int(operands["index"])
            captures = getattr(frame, "captures", None)
            if not captures or index >= len(captures):
                raise VMError("LOAD_CAPTURE without a capture table")
            stack.append(captures[index])
            return _NO_RETURN
        if name == "MAKE_CAPTURE":
            slot = int(operands["slot"])
            if not hasattr(frame, "captures"):
                frame.captures = []
            frame.captures.append(frame.locals.value_at(slot))
            return _NO_RETURN
        if name == "MAKE_SPREAD":
            stack.append(SpreadValue(stack.pop()))
            return _NO_RETURN
        if name == "LOAD_THIS":
            if frame.receiver is None:
                raise powang_throw(powang_error_identifier_not_found(None, 'this'))
            stack.append(frame.receiver)
            return _NO_RETURN
        if name == "COPY":
            stack.append(copy_value(stack.pop()))
            return _NO_RETURN
        if name == "CAST_ASSIGN":
            spec_index = int(operands["spec"])
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            value = stack.pop()
            target = getUndefinedVariable('assignment', type_inner or {})
            stack.append(assignWithChecks('assignment', target, value, False))
            return _NO_RETURN
        if name == "CAST_RETURN":
            spec_index = int(operands["spec"])
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            value = stack.pop()
            if isinstance(type_inner, dict) and type_inner.get("error_union") \
                    and value.type == PowangErrorValue.type:
                stack.append(value)
                return _NO_RETURN
            frame_name = getattr(frame, 'name', None) or frame.code.name
            target = getUndefinedVariable(f'function return: {frame_name}', type_inner or {})
            stack.append(assignWithChecks(
                f'function return: {frame_name}', target, value,
                areSameObjectType(target, value),
            ))
            return _NO_RETURN
        if name == "BOX_ANY":
            spec_index = int(operands["spec"])
            type_node = code.constants[spec_index].value
            type_inner = type_node.get("value") if isinstance(type_node, dict) else None
            value = stack.pop()
            boxed = PowangAnyType()
            try:
                boxed.declared_spec = _typespec.from_ast_node(type_node)
            except Exception:
                pass
            assignWithChecks('box any', boxed, value, False)
            stack.append(boxed)
            return _NO_RETURN
        if name == "UNBOX_ANY":
            stack.append(PowangUnwrapAny(stack.pop()))
            return _NO_RETURN

        if name == "MAKE_ARRAY":
            count = int(operands["count"])
            values = _pop_many(stack, count)
            stack.append(PowangArray(values))
            return _NO_RETURN
        if name == "MAKE_ARRAY_TYPED":
            spec_index = int(operands["spec"])
            count = int(operands["count"])
            type_node = code.constants[spec_index].value
            values = _pop_many(stack, count)
            stack.append(PowangArray([
                coerce_value_to_type_node('instantiation', item, type_node)
                for item in values
            ]))
            return _NO_RETURN
        if name == "MAKE_TUPLE":
            count = int(operands["count"])
            stack.append(PowangTuple(_pop_many(stack, count)))
            return _NO_RETURN
        if name == "MAKE_TUPLE_TYPED":
            spec_index = int(operands["spec"])
            count = int(operands["count"])
            type_node = code.constants[spec_index].value
            values = _pop_many(stack, count)
            stack.append(PowangTuple([
                coerce_value_to_type_node('instantiation', item, type_node)
                for item in values
            ]))
            return _NO_RETURN
        if name == "MAKE_MAP":
            count = int(operands["count"])
            entries = _pop_many(stack, count * 2)
            result: dict[PowangAny, PowangAny] = {}
            for index in range(0, len(entries), 2):
                result[entries[index]] = entries[index + 1]
            stack.append(PowangMap(result))
            return _NO_RETURN
        if name == "MAKE_MAP_TYPED":
            count = int(operands["count"])
            entries = _pop_many(stack, count * 2)
            result: dict[PowangAny, PowangAny] = {}
            for index in range(0, len(entries), 2):
                result[entries[index]] = entries[index + 1]
            stack.append(PowangMap(result))
            return _NO_RETURN
        if name == "MAKE_SET":
            count = int(operands["count"])
            stack.append(PowangSet(_pop_many(stack, count)))
            return _NO_RETURN
        if name == "MAKE_SET_TYPED":
            spec_index = int(operands["spec"])
            count = int(operands["count"])
            type_node = code.constants[spec_index].value
            values = _pop_many(stack, count)
            stack.append(PowangSet([
                coerce_value_to_type_node('instantiation', item, type_node)
                for item in values
            ]))
            return _NO_RETURN
        if name == "MAKE_EMPTY_MAP":
            stack.append(PowangMap())
            return _NO_RETURN
        if name == "MAKE_EMPTY_SET":
            stack.append(PowangSet())
            return _NO_RETURN
        if name == "INDEX_GET":
            index = stack.pop()
            container = unwrap(stack.pop())
            if container.type == PowangAnyType.type:
                container = unwrap(container)
            stack.append(container.index(index))
            return _NO_RETURN
        if name == "INDEX_SET":
            value = stack.pop()
            index = stack.pop()
            container = unwrap(stack.pop())
            stack.append(_index_set(container, index, value, where))
            return _NO_RETURN
        if name == "SLICE":
            end = stack.pop()
            start = stack.pop()
            target = unwrap(stack.pop())
            stack.append(slice_value(
                where, target,
                None if is_nova(start) else start,
                None if is_nova(end) else end,
            ))
            return _NO_RETURN
        if name == "SIZE":
            stack.append(builtin_size(stack.pop()))
            return _NO_RETURN
        if name == "ITER_NEW":
            iterable = unwrap(stack.pop())
            if iterable.type not in {
                PowangArray.type, PowangString.type, PowangMap.type, PowangSet.type,
            }:
                raise powang_throw(powang_error_format(
                    "VALUE", 'for each statement', "Expression is not an iterable value", [
                        f"Expression is of type {iterable.type}"
                    ]))
            stack.append(VMIterator(list(iterable.iterate().data)))
            return _NO_RETURN
        if name == "ITER_NEXT":
            iterator = stack[-1]
            if not isinstance(iterator, VMIterator):
                raise VMError("ITER_NEXT without an iterator")
            if iterator.index >= len(iterator.values):
                stack.pop()
                frame.ip = int(operands["target"])
                return _NO_RETURN
            item = iterator.values[iterator.index]
            iterator.index += 1
            stack.append(copy_value(item))
            return _NO_RETURN

        if name in _BINARY_OPS:
            right = stack.pop()
            left = stack.pop()
            stack.append(performOperation(
                _BINARY_OPS[name], left, right, name.endswith("_TYPED"),
                position,
            ))
            return _NO_RETURN
        if name == "NEG":
            value = stack.pop()
            if value.type == PowangObjectType.type:
                overloaded = _call_operator_method(
                    'operator -', value, None,
                    trait_method(UNARY_OPERATOR_TRAITS['-']), [], position,
                )
                if overloaded is not None:
                    stack.append(overloaded)
                    return _NO_RETURN
            if value.type == PowangInteger.type:
                stack.append(PowangInteger(-value.data))
                return _NO_RETURN
            if value.type == PowangNumber.type:
                stack.append(PowangNumber(-value.data))
                return _NO_RETURN
            raise powang_throw(powang_error_invalid_type_for_prefix_operator(
                None, '-', value.type,
            ))
        if name == "NOT":
            stack.append(PowangBoolean(not PowangBoolean.cast(stack.pop()).data))
            return _NO_RETURN
        if name == "CONCAT_STR":
            count = int(operands["count"])
            values = _pop_many(stack, count)
            pieces = []
            for value in values:
                if isinstance(value, _Skip):
                    continue
                if value.type == PowangString.type:
                    pieces.append(value.data)
            stack.append(PowangString(''.join(pieces)))
            return _NO_RETURN
        if name == "TO_STRING":
            value = stack.pop()
            casted = _explicit_string(value)
            stack.append(casted if casted is not None else _SKIP)
            return _NO_RETURN
        if name == "TO_BOOL":
            stack.append(PowangBoolean(truthy(stack.pop())))
            return _NO_RETURN
        if name == "REVERSE":
            value = stack.pop()
            if value.type == PowangInteger.type:
                casted_string = explicitCastString(value)
                stack.append(explicitCastInteger(
                    PowangString(casted_string.data[::-1])
                ))
                return _NO_RETURN
            if value.type == PowangNumber.type:
                casted_string = explicitCastString(value)
                stack.append(explicitCastNumber(
                    PowangString(casted_string.data[::-1])
                ))
                return _NO_RETURN
            if value.type == PowangString.type:
                stack.append(PowangString(value.data[::-1]))
                return _NO_RETURN
            if value.type == PowangArray.type:
                stack.append(PowangArray(list(reversed(value.data))))
                return _NO_RETURN
            ## The tree walker falls through for unsupported reverse targets
            ## and yields nova. Keep the same observable result.
            stack.append(PowangNova())
            return _NO_RETURN
        if name == "CAST":
            type_node = code.constants[int(operands["spec"])].value
            stack.append(_explicit_as_cast(stack.pop(), type_node, where))
            return _NO_RETURN
        if name == "TYPE_CHECK":
            type_node = code.constants[int(operands["spec"])].value
            stack.append(PowangBoolean(runtime_type_matches(stack.pop(), type_node)))
            return _NO_RETURN
        if name == "TYPE_CHECK_NOT":
            type_node = code.constants[int(operands["spec"])].value
            stack.append(PowangBoolean(not runtime_type_matches(stack.pop(), type_node)))
            return _NO_RETURN
        if name == "TYPE_CHECK_VALUE":
            right = stack.pop()
            left = stack.pop()
            condition = True
            if right.weak:
                condition = condition and left.weak.it_is
            if right.const:
                condition = condition and left.const.it_is
            stack.append(PowangBoolean(condition))
            return _NO_RETURN
        if name == "IS_NOVA":
            stack.append(PowangBoolean(is_nova(stack.pop())))
            return _NO_RETURN
        if name == "IS_DEFINED":
            stack.append(PowangBoolean(is_defined(stack.pop())))
            return _NO_RETURN
        if name == "IS_WEAK":
            stack.append(PowangBoolean(is_weak(stack.pop())))
            return _NO_RETURN

        if name == "JUMP":
            frame.ip = int(operands["target"])
            return _NO_RETURN
        if name in {"JUMP_IF_FALSE", "JUMP_IF_TRUE"}:
            value = stack.pop()
            taken = truthy(value)
            if name == "JUMP_IF_FALSE":
                taken = not taken
            if taken:
                frame.ip = int(operands["target"])
            return _NO_RETURN
        if name in {"JUMP_IF_FALSE_KEEP", "JUMP_IF_TRUE_KEEP"}:
            value = stack.pop()
            taken = truthy(value)
            if name == "JUMP_IF_FALSE_KEEP":
                taken = not taken
            stack.append(value)
            if taken:
                frame.ip = int(operands["target"])
            return _NO_RETURN
        if name in {"JUMP_IF_NOVA", "JUMP_IF_NOT_NOVA"}:
            value = stack.pop()
            condition = is_nova(value) or not value.weak.has_value
            if name == "JUMP_IF_NOT_NOVA":
                condition = not condition
            if condition:
                frame.ip = int(operands["target"])
            return _NO_RETURN
        if name == "MATCH":
            subject = stack.pop()
            descriptor = image.pattern(int(operands["pattern"]))
            if not _match_descriptor(self, frame, descriptor, subject):
                frame.ip = int(operands["target"])
            return _NO_RETURN
        if name == "RETURN":
            value = stack.pop()
            if frame.is_function:
                return copy_value(value)
            return value
        if name == "CHECK_CANCEL":
            check_cancellation()
            return _NO_RETURN
        if name == "SET_RETURN":
            value = stack.pop()
            _restore_scopes_for_transfer(frame, current.offset)
            frame.pending_return = copy_value(value)
            frame.pending_error = None
            frame.transfer = ("return", -1)
            return _NO_RETURN
        if name == "SET_TRANSFER":
            kind = int(operands["kind"])
            _restore_scopes_for_transfer(frame, current.offset)
            frame.transfer = ("jump", int(operands["target"])) if kind == 0 else ("return", -1)
            frame.pending_error = None
            frame.pending_return = None
            return _NO_RETURN
        if name == "JUMP_IF_TRANSFER":
            if frame.transfer is not None or frame.pending_return is not None:
                frame.ip = int(operands["target"])
            return _NO_RETURN
        if name == "ABANDON_FINALLY":
            if frame.handlers and frame.handlers[-1].state == "finally":
                frame.handlers.pop()
            frame.pending_error = None
            frame.pending_return = None
            frame.transfer = None
            return _NO_RETURN
        if name == "APPLY_TRANSFER":
            transfer = frame.transfer
            pending_return = frame.pending_return
            if transfer is None and pending_return is None:
                return _NO_RETURN
            frame.transfer = None
            if transfer is not None and transfer[0] == "jump":
                frame.ip = transfer[1]
                return _NO_RETURN
            value = pending_return if pending_return is not None else PowangNova()
            frame.pending_return = None
            return copy_value(value) if frame.is_function else value

        if name in {
            "CALL", "CALL_BUILTIN", "CALL_EXTERN",
            "CALL_VALUE", "CALL_METHOD", "CALL_STATIC", "CALL_MODULE",
            "CALL_NATIVE", "CALL_TRAIT", "CALL_OPERATOR",
            "CALL_ASYNC", "CALL_ASYNC_METHOD", "SPAWN", "CONSTRUCT",
        }:
            return _handle_call(self, frame, name, operands, code)
        if name == "AWAIT":
            awaited = unwrap(stack.pop())
            if awaited.type != PowangTask.type:
                raise powang_throw(powang_error_type_match(
                    'await', PowangTask.type, awaited.type,
                ))
            if awaited.lazy_pool is not None:
                stack.append(run_lazy_task(awaited))
            else:
                stack.append(builtin_wait(awaited))
            return _NO_RETURN

        if name == "NEW_ENUM":
            enum_index = int(operands["enum"])
            variant = int(operands["variant"])
            stack.append(_new_enum(image, enum_index, variant))
            return _NO_RETURN
        if name == "LOAD_FIELD":
            member_name = image.global_names[int(operands["field"])]
            stack.append(_load_member(unwrap(stack.pop()), member_name, where, safe=False))
            return _NO_RETURN
        if name == "STORE_FIELD":
            value = stack.pop()
            owner = unwrap(stack.pop())
            member_name = image.global_names[int(operands["field"])]
            stack.append(_store_member(owner, member_name, value, where))
            return _NO_RETURN
        if name == "LOAD_MEMBER":
            member_name = image.global_names[int(operands["name"])]
            stack.append(_load_member(unwrap(stack.pop()), member_name, where, safe=False))
            return _NO_RETURN
        if name == "STORE_MEMBER":
            value = stack.pop()
            owner = unwrap(stack.pop())
            member_name = image.global_names[int(operands["name"])]
            stack.append(_store_member(owner, member_name, value, where))
            return _NO_RETURN
        if name == "LOAD_MEMBER_SAFE":
            member_name = image.global_names[int(operands["name"])]
            stack.append(_load_member(unwrap(stack.pop()), member_name, where, safe=True))
            return _NO_RETURN
        if name == "LOAD_ENUM_MEMBER":
            enum_index = int(operands["enum"])
            variant = int(operands["variant"])
            stack.append(_new_enum(image, enum_index, variant))
            return _NO_RETURN
        if name == "SET_LOCKS":
            flags = int(operands["flags"])
            owner = stack.pop()
            if flags & 1:
                owner.structure_locked = True
            if flags & 2:
                owner.elements_locked = True
            return _NO_RETURN

        if name == "CHECK_TRAIT":
            trait_index = int(operands["trait"])
            trait_info = image.trait_info(trait_index)
            trait = get_state().traits.get(trait_info.name)
            value = unwrap(stack.pop())
            if trait is None or value.type != PowangObjectType.type \
                    or not _object_satisfies_trait(value, trait):
                raise powang_throw(powang_error_format(
                    'IMPLEMENTATION', where,
                    f"value does not satisfy trait '{trait_info.name}'",
                ))
            stack.append(value)
            return _NO_RETURN
        if name == "TRAIT_CAST":
            trait_index = int(operands["trait"])
            trait_info = image.trait_info(trait_index)
            trait = get_state().traits.get(trait_info.name)
            value = unwrap(stack.pop())
            if trait is None or value.type != PowangObjectType.type \
                    or not _object_satisfies_trait(value, trait):
                raise powang_throw(powang_error_format(
                    'IMPLEMENTATION', where,
                    f"value does not satisfy trait '{trait_info.name}'",
                ))
            stack.append(value)
            return _NO_RETURN

        if name == "MAKE_ERROR":
            descriptor = code.constants[int(operands["spec"])].value
            count = _bind_count(descriptor)
            arguments = _pop_many(stack, count)
            from .declarations import make_error
            stack.append(make_error(descriptor, arguments))
            return _NO_RETURN
        if name == "ERROR_PROPERTY":
            property_index = int(operands["property"])
            error_value = stack.pop()
            if error_value.type != PowangErrorValue.type:
                raise powang_throw(powang_error_type_match(
                    'error property', PowangErrorValue.type, error_value.type,
                ))
            property_name = _PROPERTY_NAMES[property_index] \
                if 0 <= property_index < len(_PROPERTY_NAMES) else 'kind'
            stack.append(getErrorProperty(where, error_value, property_name))
            return _NO_RETURN
        if name == "THROW":
            error_value = stack.pop()
            _throw_value(error_value)
            return _NO_RETURN
        if name == "PROPAGATE":
            value = unwrap(stack.pop())
            if value.type == PowangErrorValue.type:
                if not frame.is_function:
                    current_scope_type = ScopeStack.current_scope_type()
                    raise powang_throw(powang_error_format(
                        'LOGIC', 'postfix unwrap',
                        "Trying to use the '?' operator outside a function scope", [
                            f"the scope you are trying to unwrap from it's {ScopeType.toStr(current_scope_type)}"
                        ],
                    ))
                for handler in reversed(frame.handlers):
                    if handler.state == "finally":
                        continue
                    if not (handler.start_ip <= current.offset < handler.end_ip):
                        continue
                    if handler.finally_ip >= 0:
                        handler.state = "finally"
                        frame.pending_return = copy_value(value)
                        frame.pending_error = None
                        frame.transfer = ("return", -1)
                        frame.ip = handler.finally_ip
                        return _NO_RETURN
                return copy_value(value)
            stack.append(value)
            return _NO_RETURN
        if name == "TRY_BEGIN":
            next_ip = frame.ip
            entry = self._exception_entry_for(code, next_ip)
            if entry is None:
                raise VMError(f"TRY_BEGIN at {current.offset} has no exception entry")
            frame.handlers.append(HandlerEntry(
                start_ip=entry.start_ip,
                end_ip=entry.end_ip,
                catch_ip=entry.catch_ip,
                finally_ip=entry.finally_ip,
                resume_ip=entry.resume_ip,
                stack_depth=len(stack),
                local_watermark=entry.local_watermark,
                kind=entry.kind,
                scope_depth=len(ScopeStack.variables),
            ))
            return _NO_RETURN
        if name == "TRY_END":
            if frame.handlers:
                frame.handlers.pop()
            return _NO_RETURN
        if name == "FINALLY_END":
            handler = frame.handlers.pop() if frame.handlers else None
            if frame.pending_error is not None:
                error = frame.pending_error
                frame.pending_error = None
                raise error
            if handler is not None:
                frame.ip = handler.resume_ip
            return _NO_RETURN
        if name == "RETHROW":
            _throw_value(stack.pop())
            return _NO_RETURN

        if name == "REF_LOCAL":
            slot = int(operands["slot"])
            stack.append(_ref_local(frame, slot, where))
            return _NO_RETURN
        if name == "REF_GLOBAL":
            global_name = image.global_names[int(operands["name"])]
            stack.append(_ref_store(frame.module_scope.variables, global_name, where))
            return _NO_RETURN
        if name == "REF_FIELD":
            owner = unwrap(stack.pop())
            member_name = image.global_names[int(operands["field"])]
            stack.append(_ref_field(owner, member_name, where))
            return _NO_RETURN
        if name == "REF_INDEX":
            index = stack.pop()
            container = unwrap(stack.pop())
            stack.append(_ref_index(container, index, where))
            return _NO_RETURN
        if name == "LOAD_REF":
            reference = stack.pop()
            stack.append(reference.get())
            return _NO_RETURN
        if name == "STORE_REF":
            value = stack.pop()
            reference = stack.pop()
            target = reference.get()
            assigned = assignWithChecks(where, target, value, False)
            reference.set(assigned)
            return _NO_RETURN

        if name == "IMPORT":
            module_index = int(operands["module"])
            slot = int(operands["slot"])
            descriptor = image.module_info(module_index).imports[0]
            loader = get_module_loader()
            module_value = loader.load(descriptor)
            alias = descriptor.get("alias")
            if not isinstance(alias, str) or not alias:
                alias = Path(str(descriptor.get("name") or "")).stem
            existing = ScopeStack.get_variable(alias)
            if existing is not None and getattr(existing, 'defined', True) and existing is not module_value:
                raise powang_throw(powang_error_format(
                    'MODULE', 'use expression', f"Import collision for '{alias}'", [
                        f"module '{module_value.name}' cannot be bound",
                        f"'{alias}' is already declared in this scope",
                    ]
                ))
            frame.locals.set_at(slot, module_value)
            frame.locals.bind_slot(slot, alias)
            if module_value.legacy and descriptor.get("alias") is None:
                from ..runtime import bindWildcardImport
                bindWildcardImport('use expression', module_value)
            return _NO_RETURN
        if name == "IMPORT_WILDCARD":
            module_index = int(operands["module"])
            descriptor = image.module_info(module_index).imports[0]
            loader = get_module_loader()
            module_value = loader.load(descriptor)
            from ..runtime import bindWildcardImport
            bindWildcardImport('use expression', module_value)
            return _NO_RETURN
        if name == "LOAD_MODULE_MEMBER":
            module_index = int(operands["module"])
            export_index = int(operands["export"])
            module_info = image.module_info(module_index)
            if 0 <= export_index < len(module_info.exports):
                member_name = module_info.exports[export_index][0]
            else:
                member_name = image.global_names[export_index]
            loader = get_module_loader()
            module_value = None
            for cached in loader.cache.values():
                if cached.name == module_info.name:
                    module_value = cached
                    break
            if module_value is None:
                raise powang_throw(powang_error_identifier_not_found(
                    where, module_info.name,
                ))
            stack.append(moduleMemberValue(where, module_value, member_name))
            return _NO_RETURN
        if name == "LOAD_PROJECT":
            project = getattr(get_state(), 'project_value', None)
            stack.append(project if project is not None else PowangNova())
            return _NO_RETURN
        if name == "EXPORT":
            stack.pop()
            return _NO_RETURN
        if name == "TRACE_EVENT":
            if self._trace_sink is not None:
                self._emit_trace("trace", frame, current, str(operands["event"]))
            return _NO_RETURN
        if name == "HOST_CALL":
            host_index = int(operands["host"])
            callbacks = getattr(self, 'host_callbacks', [])
            if host_index < 0 or host_index >= len(callbacks):
                raise VMError(f"HOST_CALL {host_index} is not registered")
            stack.append(callbacks[host_index]())
            return _NO_RETURN

        raise VMError(f"unhandled opcode {name}")


def _restore_scopes_for_transfer(frame: VMFrame, fault_ip: int) -> None:
    for handler in reversed(frame.handlers):
        if handler.state == "finally":
            continue
        if handler.finally_ip < 0:
            continue
        if handler.start_ip <= fault_ip < handler.end_ip:
            while len(ScopeStack.variables) > handler.scope_depth:
                _pop_block_scope(frame)
            return


def _pop_block_scope(frame: VMFrame) -> None:
    """Pop one runtime block scope and hide its locals from the frame store."""
    if len(ScopeStack.variables) <= 1:
        return
    top = ScopeStack.variables[-1]
    if top is frame.locals:
        return
    ScopeStack.pop()
    slots = frame.block_slots.pop(id(top), {})
    if slots:
        frame.locals.hide_names(list(slots.values()))


_NO_RETURN = object()

_WHERE_BY_OPCODE = {
    "LOAD_CONST": "expression statement",
    "LOAD_LOCAL": "identifier",
    "LOAD_GLOBAL": "identifier",
    "LOAD_NAME": "identifier",
    "LOAD_FREE": "identifier",
    "LOAD_THIS": "identifier",
    "LOAD_CAPTURE": "identifier",
    "STORE_LOCAL": "assignment",
    "STORE_GLOBAL": "assignment",
    "STORE_NAME": "assignment",
    "ASSIGN_LOCAL": "assignment",
    "ASSIGN_NAME": "assignment",
    "DECLARE_LOCAL": "declaration undefined",
    "DECLARE_GLOBAL": "declaration undefined",
    "DECLARE_UNDEFINED_GLOBAL": "declaration undefined",
    "DECLARE_TYPED": "declaration typed var",
    "DECLARE_TYPED_GLOBAL": "declaration typed var",
    "DECLARE_INFER": "declaration interpret",
    "DECLARE_INFER_GLOBAL": "declaration interpret",
    "DECLARE_FUNCTION": "declaration fun",
    "DECLARE_TYPE": "type declaration",
    "DECLARE_TRAIT": "trait declaration",
    "DECLARE_EXTERN": "extern reference",
    "DESTRUCTURE": "destructure declaration",
    "LOAD_MEMBER": "access expression",
    "LOAD_FIELD": "access expression",
    "LOAD_MEMBER_SAFE": "safe access expression",
    "STORE_MEMBER": "assignment",
    "STORE_FIELD": "assignment",
    "INDEX_GET": "index expression",
    "INDEX_SET": "assignment",
    "SLICE": "slice expression",
    "ITER_NEW": "for each statement",
    "ITER_NEXT": "for each statement",
    "ADD": "binary expression",
    "SUB": "binary expression",
    "MUL": "binary expression",
    "DIV": "binary expression",
    "MOD": "binary expression",
    "NEG": "unary expression",
    "NOT": "unary expression",
    "REVERSE": "unary expression",
    "EQ": "binary expression",
    "NEQ": "binary expression",
    "LT": "binary expression",
    "LE": "binary expression",
    "GT": "binary expression",
    "GE": "binary expression",
    "EQ_TYPED": "binary expression",
    "NEQ_TYPED": "binary expression",
    "LT_TYPED": "binary expression",
    "LE_TYPED": "binary expression",
    "GT_TYPED": "binary expression",
    "GE_TYPED": "binary expression",
    "ADD_TYPED": "binary expression",
    "SUB_TYPED": "binary expression",
    "MUL_TYPED": "binary expression",
    "DIV_TYPED": "binary expression",
    "MOD_TYPED": "binary expression",
    "CAST": "binary expression",
    "TYPE_CHECK": "binary expression",
    "TYPE_CHECK_NOT": "binary expression",
    "TYPE_CHECK_VALUE": "binary expression",
    "CONCAT_STR": "interpolated string",
    "TO_STRING": "interpolated string",
    "CALL": "call expression",
    "CALL_VALUE": "call expression",
    "CALL_MODULE": "call expression",
    "CALL_STATIC": "method call",
    "CALL_METHOD": "method call",
    "CALL_NATIVE": "method call",
    "CALL_TRAIT": "method call",
    "CALL_OPERATOR": "operator call",
    "CALL_EXTERN": "extern function",
    "CALL_ASYNC": "call expression",
    "CALL_ASYNC_METHOD": "method call",
    "SPAWN": "spawn expression",
    "CONSTRUCT": "instantiation",
    "MAKE_ARRAY": "instantiation",
    "MAKE_ARRAY_TYPED": "instantiation",
    "MAKE_TUPLE": "instantiation",
    "MAKE_TUPLE_TYPED": "instantiation",
    "MAKE_MAP": "instantiation",
    "MAKE_MAP_TYPED": "instantiation",
    "MAKE_SET": "instantiation",
    "MAKE_SET_TYPED": "instantiation",
    "MATCH": "match statement",
    "THROW": "throw",
    "PROPAGATE": "postfix unwrap",
    "REF_LOCAL": "reference expression",
    "REF_GLOBAL": "reference expression",
    "REF_FIELD": "reference expression",
    "REF_INDEX": "reference expression",
    "IMPORT": "use expression",
    "IMPORT_WILDCARD": "use expression",
    "LOAD_MODULE_MEMBER": "access expression",
    "ERROR_PROPERTY": "access expression",
    "RETURN": "return expression",
}


_BINARY_OPS = {
    "ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "%",
    "ADD_TYPED": "+", "SUB_TYPED": "-", "MUL_TYPED": "*",
    "DIV_TYPED": "/", "MOD_TYPED": "%",
    "EQ": "==", "NEQ": "!=", "LT": "<", "LE": "<=", "GT": ">", "GE": ">=",
    "EQ_TYPED": "==", "NEQ_TYPED": "!=", "LT_TYPED": "<", "LE_TYPED": "<=",
    "GT_TYPED": ">", "GE_TYPED": ">=",
}


def _ensure_store_name(store, name: str) -> None:
    if name not in store:
        store.add_slot(name)


def _pop_many(stack: list[Any], count: int) -> list[Any]:
    if count <= 0:
        return []
    values = stack[-count:]
    del stack[-count:]
    return values


def _infer_declaration(value: PowangAny, where: str) -> PowangAny:
    if value.type in {
        PowangFunction.type,
        PowangFileStream.type,
        PowangModule.type,
        PowangTask.type,
    }:
        return value
    if value.type == PowangObjectType.type \
            and ScopeStack.get_ObjectType(value.type_name) is None:
        return PowangCopyConstruct(value)
    inferred = getUndefinedVariable(where, {
        "weak": value.weak.it_is,
        "const": value.const.it_is,
        "value": {
            PowangAnyType.type: value.any,
            PowangObjectType.type: value.type_name,
        }.get(value.type, value.type),
    })
    assignWithChecks(where, inferred, value, False)
    return inferred


def _load_from_store(store, name: str, where: str) -> PowangAny:
    try:
        value = store[name]
    except KeyError:
        raise powang_throw(powang_error_identifier_not_found(None, name)) from None
    if value.type == PowangReference.type:
        return value.get()
    return value


def _scope_allows_name(scope, name: str, frame: VMFrame) -> bool:
    module_scope = getattr(frame, 'module_scope', None)
    if module_scope is None:
        return True
    if scope is not module_scope.variables:
        return True
    allowed = getattr(module_scope, 'global_names', None)
    if allowed is None:
        return True
    if name in allowed:
        return True
    ## Wildcard imports add names at run time. They are real module bindings
    ## even though the compiler did not declare them as globals.
    wildcards = getattr(module_scope, 'wildcards', None)
    return wildcards is not None and name in wildcards


def _lookup_variable_in_scope(name: str, where: str, frame: VMFrame,
                              scopes: list, filter_module: bool = True) -> Optional[PowangAny]:
    for scope in reversed(scopes):
        if filter_module and not _scope_allows_name(scope, name, frame):
            continue
        try:
            value = scope[name]
        except KeyError:
            continue
        if value.type == PowangReference.type:
            value = value.get()
        if not value.defined:
            raise powang_throw(powang_error_identifier_not_found(where, name))
        return value
    return None


def _load_name(name: str, where: str, frame: VMFrame) -> PowangAny:
    value = _lookup_variable_in_scope(name, where, frame, ScopeStack.variables)
    if value is not None:
        return value
    functions = ScopeStack.get_functions(name)
    if functions is not None:
        return functions[-1]
    raise powang_throw(powang_error_identifier_not_found(None, name))


def _load_free(name: str, where: str, frame: VMFrame) -> PowangAny:
    try:
        frame_index = next(
            index for index, scope in enumerate(ScopeStack.variables)
            if scope is frame.locals
        )
    except StopIteration:
        frame_index = len(ScopeStack.variables)
    scopes = list(ScopeStack.variables[:frame_index])
    value = _lookup_variable_in_scope(name, where, frame, scopes, filter_module=False)
    if value is not None:
        return value
    for functions in reversed(ScopeStack.functions[:frame_index]):
        if name in functions:
            return functions[name][-1]
    raise powang_throw(powang_error_identifier_not_found(None, name))


def _store_name(name: str, value: PowangAny, where: str) -> None:
    slot = ScopeStack.find_variable_slot(name)
    if slot is None:
        raise powang_throw(powang_error_identifier_not_found(where, name))
    owner, _current = slot
    owner[name] = value


def _assign_slot(frame: VMFrame, slot: int, value: PowangAny, where: str) -> None:
    try:
        target = frame.locals.value_at(slot)
    except KeyError:
        frame.locals.set_at(slot, copy_value(value))
        return
    if target.type == PowangReference.type:
        referenced = target.get()
        assigned = assignWithChecks(where, referenced, value, False)
        target.set(assigned)
        return
    assigned = assignWithChecks(where, target, value, False)
    frame.locals.set_at(slot, assigned)


def _assign_name(name: str, value: PowangAny, where: str) -> None:
    slot = ScopeStack.find_variable_slot(name)
    if slot is None:
        raise powang_throw(powang_error_identifier_not_found(where, name))
    owner, target = slot
    if target.type == PowangReference.type:
        referenced = target.get()
        assigned = assignWithChecks(where, referenced, value, False)
        target.set(assigned)
        return
    assigned = assignWithChecks(where, target, value, False)
    owner[name] = assigned


def _make_function(vm: VM, fn_index: int) -> PowangFunction:
    info = vm.image.function_info(fn_index)
    function = dispatch.make_function(info, vm.image)
    frame = vm.frames[-1] if vm.frames else None
    module_scope = frame.module_scope if frame is not None else vm.current_module_scope()
    function.vm_module_scope = module_scope
    return function


def _declare_function(frame: VMFrame, function: PowangFunction) -> None:
    name = function.vm_name
    existing = frame.functions.get(name)
    if existing is not None and not getattr(function, 'trait_qualifier', None):
        for candidate in existing:
            if len(candidate.args) != len(function.args):
                continue
            different = False
            for found_arg, new_arg in zip(candidate.args, function.args):
                found_type = found_arg['value']['type']['value']
                new_type = new_arg['value']['type']['value']
                if found_type['value'] != new_type['value']:
                    different = True
                    break
                if found_type['weak'] != new_type['weak']:
                    different = True
                    break
            if not different:
                from ..error import powang_error_redefined
                raise powang_throw(powang_error_redefined(
                    'declaration fun', name, [
                        "remember, type qualifiers such as const does not determine function signatures, same with return types",
                    ],
                ))
    frame.functions.setdefault(name, []).append(function)


def _explicit_string(value: PowangAny) -> Optional[PowangString]:
    from ..builtins.cast import explicitCastString
    casted = explicitCastString(value)
    if casted is None and value.type == PowangObjectType.type:
        return PowangString(f"<type: {value.type_name}>")
    return casted


def _explicit_as_cast(value: PowangAny, type_node: Any, where: str) -> PowangAny:
    target_spec = _typespec.from_ast_expr(type_node)
    cast_name = getCastTypeName(where, type_node)
    if value.type == PowangAnyType.type:
        value = PowangUnwrapAny(value)
    if cast_name == 'obj' and value.type == PowangObjectType.type:
        return PowangCopyConstruct(value)
    if value.type == PowangObjectType.type and value.type_name == cast_name:
        return PowangCopyConstruct(value)
    if target_spec.kind is _typespec.Kind.UNION:
        return PowangCopyConstruct(cast_to_union_type(where, target_spec, value))
    if cast_name in get_state().type_alias:
        cast_name = get_state().type_alias[cast_name]['value']
    if cast_name not in NATI_TYPES and not target_spec.nominal:
        user_type = ScopeStack.get_ObjectType(cast_name)
        if user_type is None:
            raise powang_throw(powang_error_identifier_type(where, cast_name))
        return checkObjectTypes(where, user_type, value)
    casted = explicitCast(target_spec, value)
    if casted is None:
        raise powang_throw(powang_error_invalid_cast(
            where, cast_name, value.type, True,
        ))
    return PowangCopyConstruct(casted)


def _load_member(target: PowangAny, name: str, where: str, *, safe: bool) -> PowangAny:
    if safe and (target.type == PowangNova.type or not target.weak.has_value):
        return PowangNova()
    if safe and target.type == PowangMap.type:
        raise powang_throw(powang_error_syntax(where, "Invalid safe access", [
            f"{target.type} cannot be accessed in any way or has no properties"
        ]))
    if target.type == PowangErrorValue.type:
        return getErrorProperty(where, target, name)
    if target.type == PowangModule.type:
        return moduleMemberValue(where, target, name)
    if target.type == PowangMap.type:
        key = PowangString(name)
        if key in target.data:
            return target.data[key]
        raise powang_throw(powang_error_identifier_not_found(where, name, [
            "perhaps it is a private variant?"
        ]))
    if target.type == PowangProject.type:
        if not target.defined:
            raise powang_throw(powang_error_undefined_reference(where, name))
        property_value = target.getProperty(name)
        if property_value is None:
            from ..powang_types import BUILTIN_OBJECT_TYPES
            raise powang_throw(powang_error_identifier_not_found(where, name, [
                f"fields: {', '.join(BUILTIN_OBJECT_TYPES[PowangProject.type])}"
            ]))
        return property_value
    if safe:
        if target.type != PowangObjectType.type:
            raise powang_throw(powang_error_syntax(where, "Invalid safe access", [
                f"{target.type} cannot be accessed in any way or has no properties"
            ]))
        if not target.defined:
            raise powang_throw(powang_error_undefined_reference(where, name))
    else:
        if target.type != PowangObjectType.type:
            raise powang_throw(powang_error_syntax(where, "Invalid access", [
                f"{target.type} cannot be accessed in any way or has no properties"
            ]))
        if not target.defined:
            raise powang_throw(powang_error_undefined_reference(where, name))
        if not target.weak.has_value:
            raise powang_throw(powang_error_format("VALUE", where, "Invalid access", [
                f"Trying to access property {name} from a nova weak {target.type_name}"
            ]))
    is_private = _private_access_allowed(target)
    property_value = target.getProperty(name, is_private)
    if property_value is None:
        raise powang_throw(powang_error_identifier_not_found(where, name, [
            "perhaps it is a private property?"
        ] if not is_private else []))
    return property_value


def _store_member(owner: PowangAny, name: str, value: PowangAny, where: str) -> PowangAny:
    if owner.type == PowangModule.type:
        raise powang_throw(powang_error_format(
            'MODULE', where, "Modules are immutable", [
                f"cannot assign to '{owner.name}.{name}'",
            ]
        ))
    if getattr(owner, 'structure_locked', False):
        raise powang_throw(powang_error_format(
            'CONST', where, "object fields are locked", [
                "the type annotation ends with '!'",
            ],
        ))
    target = _load_member_for_assignment(owner, name, where)
    return assignWithChecks(where, target, value, False)


def _load_member_for_assignment(owner: PowangAny, name: str, where: str) -> PowangAny:
    if owner.type == PowangMap.type:
        key = PowangString(name)
        if key in owner.data:
            return owner.data[key]
        raise powang_throw(powang_error_identifier_not_found(where, name, [
            "perhaps it is a private variant?"
        ]))
    if owner.type == PowangProject.type:
        property_value = owner.getProperty(name)
        if property_value is None:
            raise powang_throw(powang_error_identifier_not_found(where, name))
        return property_value
    if owner.type == PowangObjectType.type:
        is_private = _private_access_allowed(owner)
        property_value = owner.getProperty(name, is_private)
        if property_value is None:
            raise powang_throw(powang_error_identifier_not_found(where, name, [
                "perhaps it is a private property?"
            ] if not is_private else []))
        return property_value
    raise powang_throw(powang_error_syntax(where, "Invalid access", [
        f"{owner.type} cannot be accessed in any way or has no properties"
    ]))


def _index_set(container: PowangAny, index: PowangAny, value: PowangAny, where: str) -> PowangAny:
    if container.type == PowangMap.type:
        if index in container.data:
            if getattr(container, 'elements_locked', False):
                raise powang_throw(powang_error_format(
                    'CONST', where, "map values are locked", [
                        "the value type ends with '!'",
                    ],
                ))
        elif getattr(container, 'structure_locked', False):
            raise powang_throw(powang_error_format(
                'CONST', where, "map structure is locked", [
                    "the map type ends with '!'",
                ],
            ))
        container.data[index] = copy_for_task(value)
        return value
    if container.type == PowangArray.type:
        if getattr(container, 'elements_locked', False):
            raise powang_throw(powang_error_format(
                'CONST', where, "array elements are locked", [
                    "the element type ends with '!'",
                ],
            ))
        target = container.index(index)
        return assignWithChecks(where, target, value, False)
    if container.type == PowangTuple.type:
        raise powang_throw(powang_error_format(
            'CONST', where, "tuples are immutable",
        ))
    target = container.index(index)
    return assignWithChecks(where, target, value, False)


def _ref_local(frame: VMFrame, slot: int, where: str) -> PowangAny:
    name = frame.code.local_names[slot]
    bound = frame.locals.value_at(slot)
    if bound.type == PowangReference.type:
        raise powang_throw(powang_error_format(
            'REFERENCE', where, "Cannot take a reference to a reference", [
                f"'{name}' already holds a reference",
            ]))
    if bool(bound.const):
        raise powang_throw(powang_error_format(
            'REFERENCE', where, "Cannot take a reference to a constant", [
                f"'{name}' is constant",
                "references mutate the target, so the target must be assignable",
            ]))
    return PowangReference(frame.locals, name, _runtime_reference_type(bound))


def _ref_store(store, name: str, where: str) -> PowangAny:
    try:
        bound = store[name]
    except KeyError:
        raise powang_throw(powang_error_identifier_not_found(where, name)) from None
    if bound.type == PowangReference.type:
        raise powang_throw(powang_error_format(
            'REFERENCE', where, "Cannot take a reference to a reference", [
                f"'{name}' already holds a reference",
            ]))
    if bool(bound.const):
        raise powang_throw(powang_error_format(
            'REFERENCE', where, "Cannot take a reference to a constant", [
                f"'{name}' is constant",
                "references mutate the target, so the target must be assignable",
            ]))
    return PowangReference(store, name, _runtime_reference_type(bound))


def _ref_field(owner: PowangAny, name: str, where: str) -> PowangAny:
    if owner.type == PowangModule.type:
        raise powang_throw(powang_error_format(
            'MODULE', where, "Modules are immutable", [
                "module properties cannot be referenced",
            ],
        ))
    if owner.type != PowangObjectType.type:
        raise powang_throw(powang_error_format(
            'REFERENCE', where, 'Only object properties can be referenced', [
                f"but {owner.type} was encountered",
            ],
        ))
    is_private = _private_access_allowed(owner)
    property_value = owner.getProperty(name, is_private)
    if property_value is None:
        raise powang_throw(powang_error_identifier_not_found(where, name, [
            "perhaps it is a private property?",
        ]))
    if property_value.type == PowangReference.type:
        raise powang_throw(powang_error_format(
            'REFERENCE', where, "Cannot take a reference to a reference", [
                f"'{name}' already holds a reference",
            ]))
    if bool(property_value.const):
        raise powang_throw(powang_error_format(
            'REFERENCE', where, "Cannot take a reference to a constant", [
                f"'{name}' is constant",
                "references mutate the target, so the target must be assignable",
            ]))
    if getattr(owner, 'structure_locked', False):
        raise powang_throw(powang_error_format(
            'CONST', where, "object fields are locked", [
                "the object type ends with '!'",
            ],
        ))
    return PowangPropertyReference(
        owner, name, _runtime_reference_type(property_value), is_private,
    )


def _ref_index(container: PowangAny, index: PowangAny, where: str) -> PowangAny:
    if container.type == PowangArray.type:
        if index.type != PowangInteger.type:
            raise powang_throw(powang_error_format(
                'REFERENCE', where, 'Array references need an int index', [
                    f"but {index.type} was encountered",
                ],
            ))
        resolved = index.data
        if resolved < 0:
            resolved += len(container.data)
        if resolved < 0 or resolved >= len(container.data):
            raise powang_throw(powang_error_index_out_of_range(
                resolved, len(container.data),
            ))
        if getattr(container, 'elements_locked', False):
            raise powang_throw(powang_error_format(
                'CONST', where, "array elements are locked", [
                    "the element type ends with '!'",
                ],
            ))
        element = container.data[resolved]
        return PowangElementReference(
            container, resolved, _runtime_reference_type(element),
        )
    raise powang_throw(powang_error_format(
        'REFERENCE', where, 'Only array elements can be referenced by index', [
            f"but {container.type} was encountered",
        ],
    ))


def _new_enum(image: ProgramImage, enum_index: int, variant: int) -> PowangAny:
    info = image.type_info(enum_index)
    variants = info.variants
    if variant < 0 or variant >= len(variants):
        raise powang_throw(powang_error_format(
            'TYPE', 'enum', f"Unknown variant {variant} for enum {info.name}",
        ))
    instance = PowangObjectType({'name': PowangString(variants[variant])}, {}, {}, {})
    instance.type_name = info.name
    instance.is_enum = True
    instance.defined = True
    return instance


def _throw_value(value: PowangAny) -> None:
    if value.type != PowangErrorValue.type:
        raise powang_throw(powang_error_type_match(
            'throw', PowangErrorValue.type, value.type,
        ))
    error = getattr(value, 'error', None)
    if isinstance(error, PowangError):
        raise error
    if isinstance(error, BaseException):
        raise error
    raise powang_throw(powang_error_format('USER', 'throw', str(value.data)))


def _bind_count(descriptor: dict) -> int:
    return int(descriptor.get("argument_count", 1))


def _match_descriptor(vm: VM, frame: VMFrame, descriptor, subject: PowangAny) -> bool:
    subject = unwrap(subject)
    kind = descriptor.kind
    if kind == "wildcard":
        return True
    if kind == "binding":
        for _name, slot in descriptor.bindings:
            if slot >= 0:
                bound = copy_value(subject)
                frame.locals.set_at(slot, bound)
                publish_local(frame, slot, bound)
        return True
    if kind == "literal":
        literal = evaluateAstExpression(descriptor.literal)
        literal = unwrap(literal)
        return subject.type == literal.type and subject == literal
    if kind == "range":
        start_value = unwrap(evaluateAstExpression(descriptor.start_ast))
        end_value = unwrap(evaluateAstExpression(descriptor.end_ast))
        if subject.type not in {PowangInteger.type, PowangNumber.type}:
            return False
        if start_value.type not in {PowangInteger.type, PowangNumber.type}:
            raise powang_throw(powang_error_type_match(
                'match range', 'int or num', start_value.type,
            ))
        if end_value.type not in {PowangInteger.type, PowangNumber.type}:
            raise powang_throw(powang_error_type_match(
                'match range', 'int or num', end_value.type,
            ))
        return start_value.data <= subject.data < end_value.data
    if kind in {"array", "tuple"}:
        if kind == "tuple":
            if subject.type != PowangTuple.type:
                return False
        elif subject.type not in {PowangArray.type, PowangTuple.type}:
            return False
        entries = descriptor.nested
        data = subject.data
        rest_slot = descriptor.rest_slot
        has_rest = rest_slot != -1
        if not has_rest and len(data) != len(entries):
            return False
        if has_rest and len(data) < len(entries):
            return False
        for entry, item in zip(entries, data):
            if not _match_descriptor(vm, frame, entry, item):
                return False
        if rest_slot >= 0:
            tail = data[len(entries):]
            if subject.type == PowangTuple.type:
                rest_value: PowangAny = PowangTuple([copy_value(item) for item in tail])
            else:
                rest_value = PowangArray([copy_value(item) for item in tail])
            frame.locals.set_at(rest_slot, rest_value)
            publish_local(frame, rest_slot, rest_value)
        return True
    if kind == "object":
        if subject.type != PowangObjectType.type:
            return False
        if getattr(subject, 'type_name', None) != descriptor.type_name:
            return False
        for field_name, nested in descriptor.fields:
            property_value = subject.getProperty(
                field_name, _private_access_allowed(subject)
            )
            if property_value is None:
                return False
            if not _match_descriptor(vm, frame, nested, property_value):
                return False
        return True
    return False


def _handle_call(vm: VM, frame: VMFrame, name: str, operands: dict[str, Any],
                 code: CodeObject) -> Any:
    site = vm.image.call_site(int(operands["call"]))
    count = site.positional_count
    stack = frame.stack
    if name == "CALL":
        raw = _pop_many(stack, count)
        stack.append(dispatch.call_identifier(vm, frame, site, raw))
        return _NO_RETURN
    if name == "CALL_BUILTIN":
        raw = _pop_many(stack, count)
        stack.append(dispatch.call_builtin(vm, frame, site, raw))
        return _NO_RETURN
    if name == "CALL_EXTERN":
        raw = _pop_many(stack, count)
        stack.append(dispatch.call_extern(vm, frame, site, raw))
        return _NO_RETURN
    if name == "CALL_VALUE":
        raw = _pop_many(stack, count)
        callee = stack.pop()
        positional, named = dispatch.flatten_arguments(site, raw)
        stack.append(dispatch.call_value(vm, frame, callee, positional, named, 'call expression'))
        return _NO_RETURN
    if name == "CALL_METHOD":
        raw = _pop_many(stack, count)
        receiver = stack.pop()
        stack.append(dispatch.call_method(vm, frame, site, raw, receiver))
        return _NO_RETURN
    if name == "CALL_STATIC":
        raw = _pop_many(stack, count)
        stack.append(dispatch.call_static(vm, frame, site, raw))
        return _NO_RETURN
    if name == "CALL_MODULE":
        raw = _pop_many(stack, count)
        target = stack.pop()
        stack.append(dispatch.call_module(vm, frame, site, raw, target))
        return _NO_RETURN
    if name == "CALL_NATIVE":
        raw = _pop_many(stack, count)
        stack.append(dispatch.call_native(vm, frame, site, raw))
        return _NO_RETURN
    if name == "CALL_TRAIT":
        raw = _pop_many(stack, count)
        stack.append(dispatch.call_trait(vm, frame, site, raw))
        return _NO_RETURN
    if name == "CALL_OPERATOR":
        raw = _pop_many(stack, count)
        positional, _named = dispatch.flatten_arguments(site, raw)
        if not positional:
            raise powang_throw(powang_error_format(
                'OPERATION', 'operator call', 'missing receiver',
            ))
        receiver = unwrap(positional[0])
        arguments = positional[1:]
        if receiver.type != PowangObjectType.type:
            raise powang_throw(powang_error_format(
                'OPERATION', 'operator call', 'operator methods require an object receiver',
            ))
        candidate = _call_operator_method(
            f'operator {site.name}', receiver, site.operator_trait,
            site.name, arguments, vm._position(frame, frame.span_index),
        )
        if candidate is None:
            raise powang_throw(powang_error_unsupported_operation(
                'operation', receiver.type, site.name,
            ))
        stack.append(candidate)
        return _NO_RETURN
    if name in {"CALL_ASYNC", "CALL_ASYNC_METHOD"}:
        raw = _pop_many(stack, count)
        target = None
        if site.dispatch in {"method", "module", "value"}:
            target = stack.pop()
        from .tasks import create_lazy_site_task
        stack.append(create_lazy_site_task(vm, frame, site, raw, target))
        return _NO_RETURN
    if name == "SPAWN":
        raw = _pop_many(stack, count)
        receiver = None
        if site.method_ast is not None and site.dispatch != "spawn_static":
            receiver = stack.pop()
        from .tasks import create_worker_site_task
        stack.append(create_worker_site_task(vm, frame, site, raw, receiver))
        return _NO_RETURN
    if name == "CONSTRUCT":
        raw = _pop_many(stack, count)
        stack.append(dispatch.construct(vm, frame, site, raw))
        return _NO_RETURN
    raise VMError(f"unhandled call opcode {name}")


def run_program(source: str, *, path: str | Path, check: bool = True,
                state=None, trace: bool = False,
                engine_options: Optional[VMRunOptions] = None) -> PowangAny:
    """Compile and run one source file on the VM."""
    from .compiler import compile_source
    from .modules import evaluate_program_image

    active_state = state if state is not None else get_state()
    options = engine_options or VMRunOptions(trace=trace)
    previous_vm = getattr(active_state, 'vm_instance', None)
    previous_cache = getattr(active_state, 'bytecode_cache', None)
    try:
        image = None
        cache = None
        cache_key = None
        if options.cache_dir:
            from .modules import BytecodeCache
            from ..parser import Parser
            from .compiler import collect_program_globals
            cache = BytecodeCache(options.cache_dir)
            active_state.bytecode_cache = cache
            cache_key = cache.key(source, path)
            image = cache.load(cache_key)
            if image is not None:
                try:
                    program_ast = Parser(source, source_path=Path(path)).parse()
                except Exception:
                    image = None
                else:
                    image.entry_ast = program_ast  # type: ignore[attr-defined]
                    image.vm_globals = collect_program_globals(program_ast)  # type: ignore[attr-defined]
        if image is None:
            image = compile_source(
                source, path=path, module_name=Path(path).stem,
                check=check, state=active_state,
            )
            if cache is not None and cache_key is not None:
                cache.store(cache_key, image)
        result = evaluate_program_image(image, active_state, options)
    except PowangError as error:
        active_state.emit_warnings()
        if error.line is None:
            raise error.with_line(source.count('\n') + 1) from None
        raise
    finally:
        active_state.vm_instance = previous_vm
        active_state.bytecode_cache = previous_cache
        active_state.emit_warnings()
    return result
