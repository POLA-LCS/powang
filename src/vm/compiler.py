"""AST lowering for the Powang bytecode VM.

The compiler is the only component that knows the shape of the parsed AST. It
turns one module into a ``ProgramImage``: code objects, constant pools, call
site descriptors, pattern descriptors, type and trait tables and module
metadata. It never executes user code.

The lowering follows the feature tables in
``docs/phase-4b-bytecode-vm/04-compiler-lowering.md``. Every language construct
maps to at least one instruction. Complex declarations carry a descriptor
constant and are executed by one instruction so the bytecode stays linear and
verifiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from ..lexer.token import DictRepr, LexerTokenType, ParserTokenType, TokenToString
from ..powang_types import *
from ..error import powang_throw, powang_error_format, powang_error_syntax
from .. import typespec as _typespec
from ..operator_traits import (
    BINARY_OPERATOR_TRAITS,
    COMPARISON_OPERATOR_TRAIT,
    COMPARISON_OPERATORS,
    OPERATOR_TRAIT_NAMES,
    UNARY_OPERATOR_TRAITS,
    trait_method,
)
from ..builtins import BUILTINS
from ..builtins.native_methods import NATIVE_METHOD_TYPES

from .builder import Builder, Label
from .image import (
    CallSite,
    CodeObject,
    ExceptionEntry,
    FunctionInfo,
    ModuleInfo,
    PatternDescriptor,
    ProgramImage,
    SourceSpan,
    TraitInfo,
    TypeInfo,
    FORMAT_VERSION,
    LANGUAGE_VERSION,
)
from .values import stable_key
from .opcodes import spec as opcode_spec


FLAG_ASYNC = 1
FLAG_VARIADIC = 2
FLAG_METHOD = 4
FLAG_STATIC = 8


class CompileError(PowangError):
    """A compile time lowering failure."""

    def __init__(self, message: str, where: str | None = None,
                 details: Optional[list[str]] = None):
        super().__init__("COMPILE", message, details or [], where)


def _node_line(node: Any) -> Optional[int]:
    if isinstance(node, dict) and isinstance(node.get("line"), int):
        return node["line"]
    return None


def _node_column(node: Any) -> Optional[int]:
    if isinstance(node, dict) and isinstance(node.get("column"), int):
        return node["column"]
    return None


def _type_inner(node: Any) -> dict:
    if isinstance(node, dict):
        if node.get("type") == ParserTokenType.TYPE:
            inner = node.get("value")
            return inner if isinstance(inner, dict) else {}
        inner = node.get("value")
        return inner if isinstance(inner, dict) else {}
    return {}


def _inner_to_type_node(inner: Any) -> dict:
    """Wrap a type inner dictionary in a TYPE node."""
    return {"type": ParserTokenType.TYPE, "value": inner if isinstance(inner, dict) else {}}


def _any_type_node() -> dict:
    """Return a complete gradual any TYPE node."""
    return _inner_to_type_node({
        "value": PowangAnyType.type,
        "weak": False,
        "const": False,
        "error_union": False,
        "reference": False,
        "element_type": None,
        "generics": [],
        "variadic": False,
        "alternatives": [],
        "auto": False,
    })


def _replace_type_parameters(node: Any, parameters: set[str]) -> Any:
    """Copy of the tree walker helper so descriptors match its type rules."""
    if isinstance(node, list):
        return [_replace_type_parameters(item, parameters) for item in node]
    if not isinstance(node, tuple):
        if not isinstance(node, dict):
            return node
    if isinstance(node, tuple):
        return tuple(_replace_type_parameters(item, parameters) for item in node)
    if node.get("type") == ParserTokenType.TYPE:
        inner = node.get("value")
        if isinstance(inner, dict) and inner.get("value") in parameters:
            return {
                "type": ParserTokenType.TYPE,
                "value": {
                    "value": PowangAnyType.type,
                    "weak": False,
                    "const": bool(inner.get("const")),
                    "error_union": bool(inner.get("error_union")),
                    "reference": False,
                    "element_type": None,
                    "generics": [],
                    "variadic": False,
                    "alternatives": [],
                    "auto": False,
                },
            }
    return {
        key: _replace_type_parameters(value, parameters)
        for key, value in node.items()
    }


class _Scope:
    __slots__ = ("kind", "entries", "display", "keys")

    def __init__(self, kind: str):
        self.kind = kind
        self.entries: dict[str, int] = {}
        self.display: dict[str, str] = {}
        self.keys: dict[str, str] = {}


@dataclass
class _Loop:
    label: Optional[str]
    break_label: Label
    continue_label: Label
    finally_depth: int = 0
    try_depth: int = 0
    runtime_depth: int = 0
    continue_depth: int = 0


@dataclass
class _PendingException:
    start: Label
    end: Label
    catch: Label
    finally_: Label
    resume: Label
    stack_depth: int
    local_watermark: int
    kind: str


class Compilation:
    """Shared mutable state for one program image."""

    def __init__(self, path: str | Path, module_name: str, state=None,
                 repl: bool = False):
        self.path = Path(path).resolve() if path is not None else Path("<memory>")
        self.module_name = module_name
        self.state = state
        self.repl = repl
        self.sources: list[str] = []
        self.source_ids: dict[str, int] = {}
        self.codes: list[CodeObject] = []
        self.types: list[TypeInfo] = []
        self.traits: list[TraitInfo] = []
        self.functions: list[FunctionInfo] = []
        self.modules: list[ModuleInfo] = []
        self.call_sites: list[CallSite] = []
        self.patterns: list[PatternDescriptor] = []
        self.type_specs: list[Any] = []
        self.imports: list[dict] = []
        self.global_names: list[str] = []
        self.strings: list[str] = []
        self._global_name_ids: dict[str, int] = {}
        self._type_spec_ids: dict[str, int] = {}
        self._call_site_ids: dict[str, int] = {}
        self._pattern_ids: dict[str, int] = {}
        self._string_ids: dict[str, int] = {}
        self.module_declared: set[str] = set()
        self.module_types: set[str] = set()
        self.module_traits: set[str] = set()
        self.module_functions: set[str] = set()
        self.types_name_index: dict[str, int] = {}

    def source_id(self, path: str | Path) -> int:
        key = str(Path(path).resolve()) if path is not None else str(path)
        existing = self.source_ids.get(key)
        if existing is not None:
            return existing
        index = len(self.sources)
        self.sources.append(key)
        self.source_ids[key] = index
        return index

    def name_id(self, name: str) -> int:
        existing = self._global_name_ids.get(name)
        if existing is not None:
            return existing
        index = len(self.global_names)
        self.global_names.append(name)
        self._global_name_ids[name] = index
        return index

    def string_id(self, value: str) -> int:
        existing = self._string_ids.get(value)
        if existing is not None:
            return existing
        index = len(self.strings)
        self.strings.append(value)
        self._string_ids[value] = index
        return index

    def type_spec_id(self, node: Any) -> int:
        key = stable_key(node)
        existing = self._type_spec_ids.get(key)
        if existing is not None:
            return existing
        index = len(self.type_specs)
        self.type_specs.append(node)
        self._type_spec_ids[key] = index
        return index

    def call_site_id(self, site: CallSite) -> int:
        key = stable_key(site)
        existing = self._call_site_ids.get(key)
        if existing is not None:
            return existing
        index = len(self.call_sites)
        self.call_sites.append(site)
        self._call_site_ids[key] = index
        return index

    def pattern_id(self, pattern: PatternDescriptor) -> int:
        key = stable_key(pattern)
        existing = self._pattern_ids.get(key)
        if existing is not None:
            return existing
        index = len(self.patterns)
        self.patterns.append(pattern)
        self._pattern_ids[key] = index
        return index

    def add_code(self, code: CodeObject) -> int:
        self.codes.append(code)
        return len(self.codes) - 1

    def add_function(self, info: FunctionInfo) -> int:
        self.functions.append(info)
        return len(self.functions) - 1

    def add_type(self, info: TypeInfo) -> int:
        self.types.append(info)
        index = len(self.types) - 1
        self.types_name_index[info.name] = index
        return index

    def add_trait(self, info: TraitInfo) -> int:
        self.traits.append(info)
        return len(self.traits) - 1

    def add_module(self, info: ModuleInfo) -> int:
        self.modules.append(info)
        return len(self.modules) - 1

    def image(self, entry_module: int, entry_code: int) -> ProgramImage:
        result = ProgramImage(
            format_version=FORMAT_VERSION,
            language_version=LANGUAGE_VERSION,
            flags=0,
            entry_module=entry_module,
            entry_code=entry_code,
            modules=list(self.modules),
            types=list(self.types),
            traits=list(self.traits),
            functions=list(self.functions),
            constants=[],
            call_sites=list(self.call_sites),
            patterns=list(self.patterns),
            type_specs=list(self.type_specs),
            sources=list(self.sources),
            global_names=list(self.global_names),
            strings=list(self.strings),
            debug_lines=[],
            codes=list(self.codes),
        )
        return result


class FunctionCompiler:
    """Lowers one code object."""

    def __init__(
        self,
        compilation: Compilation,
        *,
        name: str,
        qualname: str,
        params: Sequence[Any] = (),
        is_function: bool = True,
        is_method: bool = False,
        is_static: bool = False,
        is_async: bool = False,
        return_node: Any = None,
        type_parameters: Optional[set[str]] = None,
        fallback_ast: Any = None,
        source_path: str | Path | None = None,
    ):
        self.c = compilation
        self.name = name
        self.qualname = qualname
        self.is_function = is_function
        self.is_method = is_method
        self.is_static = is_static
        self.is_async = is_async
        self.return_node = return_node
        self.type_parameters = set(type_parameters or set())
        self.fallback_ast = fallback_ast
        self.source_file = self.c.source_id(source_path or self.c.path)
        self.b = Builder(name, qualname, self.source_file)
        self.param_scope = _Scope("function" if is_function else "module")
        self.scopes: list[_Scope] = [self.param_scope]
        self.loops: list[_Loop] = []
        self.finally_stack: list[Label] = []
        self.try_stack: list[bool] = []
        self.in_finally: int = 0
        self.local_keys: dict[str, int] = {}
        self.slot_keys: list[str] = []
        self.display_names: list[str] = []
        self.runtime_depth: int = 0
        self.pending_exceptions: list[_PendingException] = []
        self.span_cache: dict[tuple[Any, ...], int] = {}
        self.parameter_names: list[str] = []
        self.default_codes: list[int] = []
        self.imports: list[dict] = []
        self.repl = compilation.repl and not is_function
        self._result_slot = -1

        for index, param in enumerate(params):
            param_value = param.get("value") if isinstance(param, dict) else None
            if not isinstance(param_value, dict):
                continue
            identifier = param_value.get("identifier", {})
            param_name = identifier.get("value")
            if not isinstance(param_name, str):
                param_name = f"#arg{index}"
            slot = self._allocate_slot(param_name)
            self.param_scope.entries[param_name] = slot
            self.param_scope.display[param_name] = param_name
            self.parameter_names.append(param_name)

    # ------------------------------------------------------------------ slots
    def _allocate_slot(self, display_name: str) -> int:
        count = self.local_keys.get(display_name, 0)
        self.local_keys[display_name] = count + 1
        key = display_name if count == 0 else f"{display_name}~{count}"
        slot = self.b.declare_local(key)
        self.slot_keys.append(key)
        self.display_names.append(display_name)
        return slot

    def _allocate_hidden(self, hint: str = "#tmp") -> int:
        count = self.local_keys.get(hint, 0)
        self.local_keys[hint] = count + 1
        key = hint if count == 0 else f"{hint}~{count}"
        slot = self.b.declare_local(key)
        self.slot_keys.append(key)
        self.display_names.append(hint)
        return slot

    def reserve_local(self) -> int:
        return self._allocate_hidden()

    def declare(self, name: str, *, allow_shadow: bool) -> int:
        current = self.scopes[-1]
        slot = self._allocate_slot(name)
        current.entries[name] = slot
        current.display[name] = name
        current.keys[name] = self.slot_keys[slot]
        return slot

    def check_redeclare(self, name: str, allow_shadow: bool,
                        where: str) -> None:
        if allow_shadow:
            return
        if self.resolve_local(name) is not None:
            raise powang_throw(powang_error_format(
                'REDEFINE', where, "Cannot redefine variables", [
                    f"redefined: {name}",
                ],
            ))

    def resolve_local(self, name: str) -> Optional[int]:
        for scope in reversed(self.scopes):
            if name in scope.entries:
                return scope.entries[name]
        return None

    def push_scope(self, kind: str = "block") -> _Scope:
        scope = _Scope(kind)
        self.scopes.append(scope)
        return scope

    def pop_scope(self) -> None:
        if len(self.scopes) == 1:
            return
        self.scopes.pop()

    def in_nested_block(self) -> bool:
        return len(self.scopes) > 1

    def is_declared_anywhere(self, name: str) -> bool:
        if self.resolve_local(name) is not None:
            return True
        return name in self.c.module_declared

    # ------------------------------------------------------------------ spans
    def span(self, node: Any) -> int:
        line = _node_line(node)
        column = _node_column(node)
        key = (line, column)
        cached = self.span_cache.get(key)
        if cached is not None:
            return cached
        span = SourceSpan(
            self.source_file,
            line if line is not None else 0,
            column if column is not None else 0,
            line if line is not None else 0,
            (column + 1) if column is not None else 0,
        )
        index = self.b.add_span(span)
        self.span_cache[key] = index
        return index

    def emit(self, opcode: str, *operands: Any, node: Any = None) -> int:
        return self.b.emit(opcode, *operands, span=self.span(node))

    def label(self) -> Label:
        return self.b.new_label()

    def place(self, label: Label, node: Any = None) -> None:
        self.b.place(label)

    # -------------------------------------------------------------- constants
    def const(self, kind: str, value: Any) -> int:
        return self.b.new_constant(kind, value)

    def const_ast(self, node: Any) -> int:
        return self.const("ast", node)

    def spec(self, node: Any) -> int:
        return self.const("spec", node)

    def name_const(self, name: str) -> int:
        return self.c.name_id(name)

    def string_const(self, value: str) -> int:
        return self.const("str", value)

    # ---------------------------------------------------------------- helpers
    def emit_jump(self, opcode: str, target: Label, node: Any = None) -> int:
        return self.b.emit(opcode, target, span=self.span(node))

    def compile_condition(self, node: Any) -> None:
        self.compile_expression(node)
        self.emit("TO_BOOL", node=node)

    def compile_statement(self, node: Any) -> None:
        if not isinstance(node, dict) or not node:
            return
        self.emit("CHECK_CANCEL", node=node)
        node_type = node.get("type")
        value = node.get("value")
        if node_type == ParserTokenType.RETURN_EXPRESSION:
            self.compile_return(value, node)
            return
        if node_type in {ParserTokenType.BREAK_STATEMENT, ParserTokenType.CONTINUE_STATEMENT}:
            self.compile_loop_control(node_type, value, node)
            return
        if node_type == ParserTokenType.BLOCK_STATEMENT:
            ## A bare block in statement position comes from the boolean
            ## simplifier. The tree walker evaluates it without pushing a
            ## scope, so a declaration inside it stays in the enclosing scope.
            self.compile_bare_block(value, want_value=False)
            return
        if node_type == ParserTokenType.IF_STATEMENT:
            self.compile_if(value, node)
            return
        if node_type == ParserTokenType.LOOP_STATEMENT:
            self.compile_loop(value, node)
            return
        if node_type == ParserTokenType.FOR_STATEMENT:
            self.compile_for(value, node)
            return
        if node_type == ParserTokenType.FOR_EACH_STATEMENT:
            self.compile_for_each(value, node)
            return
        if node_type == ParserTokenType.TRY_STATEMENT:
            self.compile_try(value, node)
            return
        if node_type == ParserTokenType.MATCH_EXPRESSION:
            self.compile_match(value, node, want_value=True)
            self.emit("POP", node=node)
            return
        if node_type == ParserTokenType.MATCH_STATEMENT:
            self.compile_match(value, node, want_value=False)
            return
        if node_type in {
            ParserTokenType.DECLARATION_FUN,
            ParserTokenType.DECLARATION_UNDEFINED,
            ParserTokenType.DECLARATION_TYPED_VAR,
            ParserTokenType.DECLARATION_INTERPRET,
            ParserTokenType.DESTRUCTURE_DECLARATION,
            ParserTokenType.TYPE_DECLARATION,
            ParserTokenType.TRAIT_DECLARATION,
            ParserTokenType.USE_EXPRESSION,
            ParserTokenType.EXTERN_REFERENCE,
            ParserTokenType.MODULE_DECLARATION,
            ParserTokenType.TYPE_ALIAS,
            ParserTokenType.CONST_DECLARATION,
        }:
            self.compile_expression(node)
            self.emit("POP", node=node)
            return
        self.compile_expression(node)
        self.emit("POP", node=node)

    def compile_block(self, statements: Any, want_value: bool = False) -> None:
        if not isinstance(statements, list):
            statements = []
        if not statements:
            if want_value:
                self.emit("LOAD_NOVA")
            return
        self.push_scope("block")
        self.emit("SCOPE_PUSH")
        self.runtime_depth += 1
        try:
            for index, statement in enumerate(statements):
                last = index == len(statements) - 1
                if last and want_value:
                    self.compile_expression(statement)
                else:
                    self.compile_statement(statement)
            self.emit("SCOPE_POP")
            self.runtime_depth -= 1
        finally:
            self.pop_scope()
        if not want_value:
            return

    def compile_bare_block(self, statements: Any, want_value: bool = False) -> None:
        if not isinstance(statements, list):
            statements = []
        if not statements:
            if want_value:
                self.emit("LOAD_NOVA")
            return
        for index, statement in enumerate(statements):
            last = index == len(statements) - 1
            if last and want_value:
                self.compile_expression(statement)
            else:
                self.compile_statement(statement)

    # ------------------------------------------------------------- statements
    def compile_return(self, value: Any, node: Any) -> None:
        if not self.is_function:
            raise powang_throw(powang_error_format(
                'LOGIC', None,
                "Trying to return with a non function scope", [
                    "the scope you are trying to return from it's global"
                ],
            ))
        if value is None:
            self.emit("LOAD_NOVA", node=node)
        else:
            self.compile_expression(value)
        if self.return_node is not None:
            self.emit("CAST_RETURN", self.spec(self.return_node), node=node)
        if self.in_finally:
            self.emit("ABANDON_FINALLY", node=node)
        if self.finally_stack:
            self.emit("SET_RETURN", node=node)
            self.emit_jump("JUMP", self.finally_stack[-1], node)
            return
        self.emit("RETURN", node=node)

    def compile_loop_control(self, node_type: Any, value: Any, node: Any) -> None:
        label = None
        if isinstance(value, dict):
            label = value.get("label")
        target_loop: Optional[_Loop] = None
        for loop in reversed(self.loops):
            if label is None or loop.label == label:
                target_loop = loop
                break
        if target_loop is None:
            if label is None:
                raise CompileError(
                    "Loop control outside a loop", "compile",
                    ["break and continue require an enclosing loop"],
                )
            raise CompileError(
                f"Unknown loop label '{label}'", "compile",
                ["declare the label on an enclosing loop"],
            )
        if node_type == ParserTokenType.BREAK_STATEMENT:
            target = target_loop.break_label
        else:
            target = target_loop.continue_label
        if self.in_finally:
            self.emit("ABANDON_FINALLY", node=node)
        scope_depth = (
            target_loop.runtime_depth
            if node_type == ParserTokenType.BREAK_STATEMENT
            else target_loop.continue_depth
        )
        for _ in range(max(0, self.runtime_depth - scope_depth)):
            self.emit("SCOPE_POP", node=node)
        for index in range(len(self.try_stack) - 1, target_loop.try_depth - 1, -1):
            if not self.try_stack[index]:
                self.emit("TRY_END", node=node)
        if len(self.finally_stack) > target_loop.finally_depth:
            self.emit("SET_TRANSFER", 0, target, node=node)
            self.emit_jump("JUMP", self.finally_stack[-1], node)
            return
        self.emit_jump("JUMP", target, node)

    def compile_if(self, value: dict, node: Any) -> None:
        condition = value.get("expression")
        block = value.get("block")
        else_block = value.get("else")
        else_label = self.label()
        end_label = self.label()
        self.push_scope("if")
        self.emit("SCOPE_PUSH")
        self.runtime_depth += 1
        try:
            self.compile_condition(condition)
            self.emit_jump("JUMP_IF_FALSE", else_label, node)
            if isinstance(block, dict):
                self.compile_block(block.get("value"), want_value=False)
            self.emit("SCOPE_POP")
            self.runtime_depth -= 1
            self.emit_jump("JUMP", end_label, node)
            self.place(else_label)
            self.emit("SCOPE_POP")
            self.runtime_depth -= 1
        finally:
            self.pop_scope()
        if isinstance(else_block, dict):
            self.compile_block(else_block.get("value"), want_value=False)
        self.place(end_label)

    def compile_loop(self, value: dict, node: Any) -> None:
        loop_label = value.get("label")
        condition = value.get("condition")
        block = value.get("block")
        start_label = self.label()
        continue_label = self.label()
        end_label = self.label()
        self.place(start_label)
        self.emit("CHECK_CANCEL", node=node)
        if condition is not None:
            self.compile_condition(condition)
            self.emit_jump("JUMP_IF_FALSE", end_label, node)
        self.loops.append(_Loop(loop_label, end_label, continue_label, len(self.finally_stack), len(self.try_stack), self.runtime_depth, self.runtime_depth))
        try:
            if isinstance(block, dict):
                self.compile_block(block.get("value"), want_value=False)
        finally:
            self.loops.pop()
        self.place(continue_label)
        self.emit_jump("JUMP", start_label, node)
        self.place(end_label)

    def compile_for(self, value: dict, node: Any) -> None:
        loop_label = value.get("label")
        start_expression = value.get("start_expression")
        middle_expression = value.get("middle_expression")
        last_expression = value.get("last_expression")
        block = value.get("block")
        if middle_expression is None:
            middle_expression = start_expression
            start_expression = None
        self.push_scope("loop")
        self.emit("SCOPE_PUSH")
        self.runtime_depth += 1
        outer_depth = self.runtime_depth - 1
        continue_depth = self.runtime_depth
        try:
            if start_expression is not None:
                self.compile_statement(start_expression)
            condition_label = self.label()
            continue_label = self.label()
            end_label = self.label()
            break_label = self.label()
            self.place(condition_label)
            self.emit("CHECK_CANCEL", node=node)
            self.compile_condition(middle_expression)
            self.emit_jump("JUMP_IF_FALSE", end_label, node)
            self.loops.append(_Loop(
                loop_label, break_label, continue_label,
                len(self.finally_stack), len(self.try_stack),
                outer_depth, continue_depth,
            ))
            try:
                if isinstance(block, dict):
                    self.compile_block(block.get("value"), want_value=False)
            finally:
                self.loops.pop()
            self.place(continue_label)
            if last_expression is not None:
                self.compile_statement(last_expression)
            self.emit_jump("JUMP", condition_label, node)
            self.place(end_label)
            self.emit("SCOPE_POP")
            self.runtime_depth -= 1
            self.place(break_label)
        finally:
            self.pop_scope()

    def compile_for_each(self, value: dict, node: Any) -> None:
        loop_label = value.get("label")
        iterator = value.get("iterator")
        iterable = value.get("expression")
        block = value.get("block")
        condition = value.get("if_expression")
        self.push_scope("loop")
        self.emit("SCOPE_PUSH")
        self.runtime_depth += 1
        outer_depth = self.runtime_depth - 1
        continue_depth = self.runtime_depth
        try:
            iterator_slot = -1
            if isinstance(iterator, dict) and iterator.get("type") == ParserTokenType.DECLARATION_UNDEFINED:
                iterator_value = iterator.get("value", {})
                identifier = iterator_value.get("identifier", {})
                name = identifier.get("value")
                if not isinstance(name, str):
                    raise CompileError("Invalid for-each iterator", "compile")
                type_node = iterator_value.get("type")
                if not isinstance(type_node, dict):
                    type_node = _any_type_node()
                iterator_slot = self.declare(name, allow_shadow=self.in_nested_block())
                self.emit("DECLARE_LOCAL", iterator_slot, self.spec(type_node), 1, node=node)
                self.emit("POP", node=node)
            elif isinstance(iterator, dict) and iterator.get("type") == ParserTokenType.IDENTIFIER:
                name = iterator.get("value")
                if isinstance(name, str):
                    iterator_slot = self.resolve_local(name)
                    if iterator_slot is None:
                        iterator_slot = -2
                        iterator_name = name
            else:
                raise CompileError("Invalid for-each iterator", "compile")
            self.compile_expression(iterable)
            self.emit("ITER_NEW", node=node)
            start_label = self.label()
            continue_label = self.label()
            break_label = self.label()
            end_label = self.label()
            break_done_label = self.label()
            self.place(start_label)
            self.emit("CHECK_CANCEL", node=node)
            self.emit_jump("ITER_NEXT", end_label, node)
            if iterator_slot >= 0:
                self.emit("ASSIGN_LOCAL", iterator_slot, node=node)
            elif iterator_slot == -2:
                self.emit("ASSIGN_NAME", self.name_const(iterator_name), node=node)
            else:
                raise CompileError("Invalid for-each iterator", "compile")
            if condition is not None:
                self.compile_condition(condition)
                self.emit_jump("JUMP_IF_FALSE", continue_label, node)
            self.loops.append(_Loop(
                loop_label, break_label, continue_label,
                len(self.finally_stack), len(self.try_stack),
                outer_depth, continue_depth,
            ))
            try:
                if isinstance(block, dict):
                    self.compile_block(block.get("value"), want_value=False)
            finally:
                self.loops.pop()
            self.place(continue_label)
            self.emit_jump("JUMP", start_label, node)
            self.place(break_label)
            self.emit("POP", node=node)
            self.emit_jump("JUMP", break_done_label, node)
            self.place(end_label)
            self.emit("SCOPE_POP")
            self.runtime_depth -= 1
            self.place(break_done_label)
        finally:
            self.pop_scope()

    def compile_try(self, value: dict, node: Any) -> None:
        block = value.get("block")
        catches = value.get("catches") or []
        finally_block = value.get("finally_block")
        has_finally = isinstance(finally_block, dict)
        catch_label = self.label() if catches else None
        finally_label = self.label() if has_finally else None
        end_label = self.label()
        protected_start = self.label()
        depth = self._estimated_depth()
        outer_finally = self.finally_stack[-1] if self.finally_stack else None
        self.emit("TRY_BEGIN",
                  catch_label if catch_label is not None else -1,
                  finally_label if finally_label is not None else -1,
                  node=node)
        self.place(protected_start)
        self.try_stack.append(has_finally)
        if has_finally:
            self.finally_stack.append(finally_label)
        try:
            if isinstance(block, dict):
                self.compile_block(block.get("value"), want_value=False)
        finally:
            if has_finally:
                self.finally_stack.pop()
            self.try_stack.pop()
        if catch_label is None:
            if not has_finally:
                self.emit("TRY_END", node=node)
                self.emit_jump("JUMP", end_label, node)
            else:
                self.emit_jump("JUMP", finally_label, node)
        else:
            if not has_finally:
                self.emit("TRY_END", node=node)
            self.emit_jump("JUMP", finally_label if has_finally else end_label, node)
            self.place(catch_label)
            self.push_scope("catch")
            self.emit("SCOPE_PUSH")
            self.runtime_depth += 1
            self.try_stack.append(has_finally)
            if has_finally:
                self.finally_stack.append(finally_label)
            try:
                catch = catches[0] if catches else {}
                catch_name = catch.get("name") if isinstance(catch, dict) else None
                if isinstance(catch_name, dict) and isinstance(catch_name.get("value"), str):
                    slot = self.declare(catch_name["value"], allow_shadow=True)
                    self.emit("DECLARE_LOCAL", slot, self.spec(_any_type_node()), 1, node=node)
                    self.emit("POP", node=node)
                    self.emit("STORE_LOCAL", slot, node=node)
                else:
                    self.emit("POP", node=node)
                catch_block = catch.get("block") if isinstance(catch, dict) else None
                if isinstance(catch_block, dict):
                    self.compile_block(catch_block.get("value"), want_value=False)
            finally:
                if has_finally:
                    self.finally_stack.pop()
                self.try_stack.pop()
                self.emit("SCOPE_POP")
                self.runtime_depth -= 1
                self.pop_scope()
            self.emit_jump("JUMP", finally_label if has_finally else end_label, node)
        if finally_label is not None:
            self.place(finally_label)
            self.in_finally += 1
            try:
                self.compile_block(finally_block.get("value"), want_value=False)
            finally:
                self.in_finally -= 1
            self.emit("FINALLY_END", node=node)
        self.place(end_label)
        if has_finally:
            if outer_finally is not None:
                self.emit_jump("JUMP_IF_TRANSFER", outer_finally, node)
            else:
                self.emit("APPLY_TRANSFER", node=node)
        protected_end = end_label
        if has_finally:
            protected_end = finally_label
        elif catch_label is not None:
            protected_end = catch_label
        self.pending_exceptions.append(_PendingException(
            start=protected_start,
            end=protected_end,
            catch=catch_label if catch_label is not None else -1,
            finally_=finally_label if finally_label is not None else -1,
            resume=end_label,
            stack_depth=depth,
            local_watermark=0,
            kind="finally" if has_finally else "catch",
        ))

    def _estimated_depth(self) -> int:
        return max(0, self.b.stack_effect_bound())

    # ------------------------------------------------------------------ match
    def compile_match(self, value: dict, node: Any, want_value: bool) -> None:
        subject = value.get("subject")
        cases = value.get("cases") or []
        end_label = self.label()
        result_slot = self._allocate_hidden("#match") if want_value else -1
        if want_value:
            self.emit("LOAD_NOVA")
            self.emit("STORE_RAW", result_slot)
        self.compile_expression(subject)
        subject_slot = self._allocate_hidden("#subject")
        self.emit("STORE_RAW", subject_slot)
        for case in cases:
            if not isinstance(case, dict):
                continue
            next_case = self.label()
            self.push_scope("case")
            self.emit("SCOPE_PUSH")
            self.runtime_depth += 1
            try:
                pattern = case.get("pattern")
                descriptor, _bindings = self.compile_pattern(pattern)
                self.emit("LOAD_LOCAL", subject_slot)
                self.emit("MATCH", self.c.pattern_id(descriptor), next_case, node=node)
                guard = case.get("guard")
                if guard is not None:
                    self.compile_condition(guard)
                    self.emit_jump("JUMP_IF_FALSE", next_case, node)
                if case.get("is_expression"):
                    self.compile_expression(case.get("value"))
                    if want_value:
                        self.emit("STORE_RAW", result_slot)
                    else:
                        self.emit("POP", node=node)
                else:
                    block = case.get("block")
                    if isinstance(block, dict):
                        if want_value:
                            self.compile_block(block.get("value"), want_value=True)
                            self.emit("STORE_RAW", result_slot)
                        else:
                            self.compile_block(block.get("value"), want_value=False)
                self.emit("SCOPE_POP")
                self.runtime_depth -= 1
                self.emit_jump("JUMP", end_label, node)
            finally:
                self.pop_scope()
            self.place(next_case)
            self.emit("SCOPE_POP")
            self.runtime_depth -= 1
        self.place(end_label)
        if want_value:
            self.emit("LOAD_LOCAL", result_slot, node=node)
        else:
            return

    def compile_pattern(self, pattern: Any) -> tuple[PatternDescriptor, list[tuple[str, int]]]:
        bindings: list[tuple[str, int]] = []
        descriptor = self._build_pattern(pattern, bindings)
        return descriptor, bindings

    def _build_pattern(self, pattern: Any,
                       bindings: list[tuple[str, int]]) -> PatternDescriptor:
        if not isinstance(pattern, dict):
            return PatternDescriptor(
                kind="wildcard", literal=None, bindings=(), nested=(),
                type_name=None, fields=(), rest_slot=-1,
                start_ast=None, end_ast=None,
            )
        kind = pattern.get("kind")
        if kind == "binding":
            value = pattern.get("value")
            name = value.get("value") if isinstance(value, dict) else None
            slot = -1
            if isinstance(name, str):
                slot = self.declare(name, allow_shadow=True)
                bindings.append((name, slot))
            return PatternDescriptor(
                kind="binding", literal=None, bindings=((name, slot),) if isinstance(name, str) else (),
                nested=(), type_name=None, fields=(), rest_slot=-1,
                start_ast=None, end_ast=None,
            )
        if kind == "literal":
            return PatternDescriptor(
                kind="literal", literal=pattern.get("value"), bindings=(), nested=(),
                type_name=None, fields=(), rest_slot=-1, start_ast=None, end_ast=None,
            )
        if kind == "range":
            return PatternDescriptor(
                kind="range", literal=None, bindings=(), nested=(),
                type_name=None, fields=(), rest_slot=-1,
                start_ast=pattern.get("start"), end_ast=pattern.get("end"),
            )
        if kind in {"array", "tuple"}:
            entries = pattern.get("entries") or []
            nested = tuple(self._build_pattern(entry, bindings) for entry in entries)
            rest_slot = -1
            rest = pattern.get("rest")
            if rest is not None:
                rest_slot = -2
                if isinstance(rest, dict):
                    rest_name = rest.get("name")
                    if isinstance(rest_name, str):
                        rest_slot = self.declare(rest_name, allow_shadow=True)
                        bindings.append((rest_name, rest_slot))
            return PatternDescriptor(
                kind=kind, literal=None, bindings=(), nested=nested,
                type_name=None, fields=(), rest_slot=rest_slot,
                start_ast=None, end_ast=None,
            )
        if kind == "object":
            entries = pattern.get("entries") or []
            fields = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                field = entry.get("field")
                if isinstance(field, str):
                    fields.append((field, self._build_pattern(entry.get("pattern"), bindings)))
            return PatternDescriptor(
                kind="object", literal=None, bindings=(), nested=(),
                type_name=pattern.get("type_name"), fields=tuple(fields),
                rest_slot=-1, start_ast=None, end_ast=None,
            )
        return PatternDescriptor(
            kind="wildcard", literal=None, bindings=(), nested=(),
            type_name=None, fields=(), rest_slot=-1,
            start_ast=None, end_ast=None,
        )

    # ------------------------------------------------------------- expressions
    def compile_expression(self, node: Any) -> None:
        if not isinstance(node, dict) or not node:
            self.emit("LOAD_NOVA")
            return
        node_type = node.get("type")
        value = node.get("value")
        if node_type == LexerTokenType.IDENTIFIER:
            self.compile_identifier(value, node)
            return
        if node_type == LexerTokenType.NOVA_LITERAL or node_type == LexerTokenType.KEYWORD:
            if value in {"nova", None}:
                self.emit("LOAD_NOVA", node=node)
                return
            if value == "true":
                self.emit("LOAD_TRUE", node=node)
                return
            if value == "false":
                self.emit("LOAD_FALSE", node=node)
                return
            self.compile_identifier(value, node)
            return
        if node_type == LexerTokenType.BOOLEAN_LITERAL:
            text = str(value).lower()
            self.emit("LOAD_TRUE" if text == "true" else "LOAD_FALSE", node=node)
            return
        if node_type == LexerTokenType.INTEGER_LITERAL:
            integer = int(value)
            if -(1 << 62) <= integer < (1 << 62):
                self.emit("LOAD_INT", integer, node=node)
            else:
                self.emit("LOAD_BIGINT", self.const("bigint", integer), node=node)
            return
        if node_type == LexerTokenType.FLOATING_LITERAL:
            self.emit("LOAD_NUM", float(value), node=node)
            return
        if node_type == LexerTokenType.STRING_LITERAL:
            self.emit("LOAD_STR", self.string_const(str(value)), node=node)
            return
        if node_type == LexerTokenType.CHAR_LITERAL:
            self.emit("LOAD_CHAR", ord(str(value)), node=node)
            return
        if node_type == ParserTokenType.INTERPOLATED_STRING:
            self.compile_interpolation(value, node)
            return
        if node_type == ParserTokenType.BLOCK_STATEMENT:
            self.compile_block(value, want_value=True)
            return
        if node_type == ParserTokenType.UNARY_EXPRESSION:
            self.compile_unary(value, node)
            return
        if node_type == ParserTokenType.BINARY_EXPRESSION:
            self.compile_binary(value, node)
            return
        if node_type == ParserTokenType.ARRAY_EXPRESSION:
            self.compile_array(value, node)
            return
        if node_type == ParserTokenType.TUPLE_EXPRESSION:
            self.compile_tuple(value, node)
            return
        if node_type == ParserTokenType.INDEX_EXPRESSION:
            self.compile_index(value, node)
            return
        if node_type == ParserTokenType.SLICE_EXPRESSION:
            self.compile_slice(value, node)
            return
        if node_type == ParserTokenType.ACCESS_EXPRESSION:
            self.compile_access(value, node, safe=False)
            return
        if node_type == ParserTokenType.SAFE_ACCESS_EXPRESSION:
            self.compile_access(value, node, safe=True)
            return
        if node_type == ParserTokenType.CALL_EXPRESSION:
            self.compile_call(value, node)
            return
        if node_type == ParserTokenType.METHOD_CALL:
            self.compile_method_call(value, node)
            return
        if node_type == ParserTokenType.INSTANTIATION:
            self.compile_instantiation(value, node)
            return
        if node_type == ParserTokenType.FUN_EXPRESSION:
            self.compile_lambda(value, node)
            return
        if node_type == ParserTokenType.REFERENCE_EXPRESSION:
            self.compile_reference(value, node)
            return
        if node_type == ParserTokenType.POSTFIX_UNWRAP:
            self.compile_expression(value.get("expression"))
            self.emit("PROPAGATE", node=node)
            return
        if node_type == ParserTokenType.AWAIT_EXPRESSION:
            self.compile_expression(value)
            self.emit("AWAIT", node=node)
            return
        if node_type == ParserTokenType.SPAWN_EXPRESSION:
            self.compile_spawn(value, node)
            return
        if node_type == ParserTokenType.ASSIGNMENT:
            self.compile_assignment(value, node, want_value=True)
            return
        if node_type == ParserTokenType.DECLARATION_UNDEFINED:
            self.compile_declaration_undefined(value, node)
            return
        if node_type == ParserTokenType.DECLARATION_TYPED_VAR:
            self.compile_declaration_typed(value, node)
            return
        if node_type == ParserTokenType.DECLARATION_INTERPRET:
            self.compile_declaration_infer(value, node)
            return
        if node_type == ParserTokenType.DESTRUCTURE_DECLARATION:
            self.compile_destructure(value, node)
            return
        if node_type == ParserTokenType.DECLARATION_FUN:
            self.compile_function_declaration(value, node)
            return
        if node_type == ParserTokenType.TYPE_DECLARATION:
            self.compile_type_declaration(value, node)
            return
        if node_type == ParserTokenType.TRAIT_DECLARATION:
            self.compile_trait_declaration(value, node)
            return
        if node_type == ParserTokenType.USE_EXPRESSION:
            self.compile_use(value, node)
            return
        if node_type == ParserTokenType.EXTERN_REFERENCE:
            self.compile_extern(value, node)
            return
        if node_type == ParserTokenType.MODULE_DECLARATION:
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.TYPE_ALIAS:
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.CONST_DECLARATION:
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.MATCH_EXPRESSION:
            self.compile_match(value, node, want_value=True)
            return
        if node_type == ParserTokenType.MATCH_STATEMENT:
            self.compile_match(value, node, want_value=True)
            return
        if node_type == ParserTokenType.IF_STATEMENT:
            self.compile_if(value, node)
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.LOOP_STATEMENT:
            self.compile_loop(value, node)
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.FOR_STATEMENT:
            self.compile_for(value, node)
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.FOR_EACH_STATEMENT:
            self.compile_for_each(value, node)
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.TRY_STATEMENT:
            self.compile_try(value, node)
            self.emit("LOAD_NOVA", node=node)
            return
        if node_type == ParserTokenType.RETURN_EXPRESSION:
            self.compile_return(value, node)
            self.emit("LOAD_NOVA", node=node)
            return
        raise CompileError(
            f"Unsupported AST node in expression position: {TokenToString(node_type)}",
            "compile",
        )

    def compile_identifier(self, name: Any, node: Any) -> None:
        if name == "nova":
            self.emit("LOAD_NOVA", node=node)
            return
        if name == "true":
            self.emit("LOAD_TRUE", node=node)
            return
        if name == "false":
            self.emit("LOAD_FALSE", node=node)
            return
        if name == "this":
            self.emit("LOAD_THIS", node=node)
            return
        if not isinstance(name, str):
            raise CompileError("Invalid identifier", "compile")
        slot = self.resolve_local(name)
        if slot is not None:
            self.emit("LOAD_LOCAL", slot, node=node)
            return
        if self.is_function:
            self.emit("LOAD_FREE", self.name_const(name), node=node)
            return
        self.emit("LOAD_NAME", self.name_const(name), node=node)

    def compile_interpolation(self, value: dict, node: Any) -> None:
        parts = value.get("parts") if isinstance(value, dict) else None
        if not isinstance(parts, list):
            parts = []
        count = 0
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("kind") == "text":
                self.emit("LOAD_STR", self.string_const(str(part.get("value", ""))), node=node)
                count += 1
            else:
                self.compile_expression(part.get("value"))
                self.emit("TO_STRING", node=node)
                count += 1
        self.emit("CONCAT_STR", count, node=node)

    def compile_unary(self, value: dict, node: Any) -> None:
        operator = value.get("operator", {}).get("value")
        self.compile_expression(value.get("right"))
        if operator == "!":
            self.emit("NOT", node=node)
            return
        if operator == "-":
            self.emit("NEG", node=node)
            return
        if operator == "[-]":
            self.emit("REVERSE", node=node)
            return
        raise CompileError(f"Unsupported unary operator '{operator}'", "compile")

    def compile_binary(self, value: dict, node: Any) -> None:
        operator = value.get("operator", {}).get("value")
        typed = bool(value.get("typed"))
        left = value.get("left")
        right = value.get("right")
        if operator == "::" or operator == "!:":
            self.compile_type_check(left, right, operator == "!:", node)
            return
        if operator == "as":
            self.compile_expression(left)
            self.emit("CAST", self.spec(right), node=node)
            return
        if operator == ":>":
            self.compile_pipeline(left, right, node)
            return
        if operator == "??":
            end_label = self.label()
            self.compile_expression(left)
            self.emit("DUP", node=node)
            self.emit_jump("JUMP_IF_NOT_NOVA", end_label, node)
            self.emit("POP", node=node)
            self.compile_expression(right)
            self.place(end_label)
            return
        if operator in {"&&", "||"}:
            self.compile_short_circuit(operator, left, right, node)
            return
        self.compile_expression(left)
        self.compile_expression(right)
        mapping = {
            "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
            "==": "EQ", "!=": "NEQ", "<": "LT", "<=": "LE", ">": "GT", ">=": "GE",
        }
        base = mapping.get(operator)
        if base is None:
            raise CompileError(f"Unsupported binary operator '{operator}'", "compile")
        opcode = base + "_TYPED" if typed else base
        self.emit(opcode, node=node)

    def compile_short_circuit(self, operator: str, left: Any, right: Any, node: Any) -> None:
        is_and = operator == "&&"
        end_label = self.label()
        self.compile_expression(left)
        self.emit("TO_BOOL", node=node)
        if is_and:
            self.emit_jump("JUMP_IF_FALSE_KEEP", end_label, node)
        else:
            self.emit_jump("JUMP_IF_TRUE_KEEP", end_label, node)
        self.emit("POP", node=node)
        self.compile_expression(right)
        self.emit("TO_BOOL", node=node)
        self.place(end_label)

    def compile_type_check(self, left: Any, right: Any, negate: bool, node: Any) -> None:
        right_type = right.get("type") if isinstance(right, dict) else None
        if right_type == ParserTokenType.TYPE:
            self.compile_expression(left)
            self.emit("TYPE_CHECK_NOT" if negate else "TYPE_CHECK", self.spec(right), node=node)
            return
        if right_type == LexerTokenType.IDENTIFIER:
            self.compile_expression(left)
            self.emit("TYPE_CHECK_NOT" if negate else "TYPE_CHECK", self.spec(_inner_to_type_node({
                "value": right.get("value"),
                "weak": False,
                "const": False,
                "auto": False,
            })), node=node)
            return
        self.compile_expression(left)
        self.compile_expression(right)
        self.emit("TYPE_CHECK_VALUE", node=node)
        if negate:
            self.emit("NOT", node=node)

    def compile_array(self, value: dict, node: Any) -> None:
        elements = value.get("elements") or []
        if value.get("type") == PowangMap.type:
            count = 0
            for entry in elements:
                pair = entry.get("value") if isinstance(entry, dict) else None
                if not isinstance(pair, dict):
                    continue
                self.compile_expression(pair.get("key"))
                self.compile_expression(pair.get("value"))
                count += 1
            self.emit("MAKE_MAP", count, node=node)
            return
        for element in elements:
            self.compile_expression(element)
        self.emit("MAKE_ARRAY", len(elements), node=node)

    def compile_tuple(self, value: dict, node: Any) -> None:
        elements = value.get("elements") or []
        for element in elements:
            self.compile_expression(element)
        self.emit("MAKE_TUPLE", len(elements), node=node)

    def compile_index(self, value: dict, node: Any) -> None:
        self.compile_expression(value.get("target"))
        self.compile_expression(value.get("index"))
        self.emit("INDEX_GET", node=node)

    def compile_slice(self, value: dict, node: Any) -> None:
        self.compile_expression(value.get("target"))
        start = value.get("start")
        end = value.get("end")
        if start is None:
            self.emit("LOAD_NOVA", node=node)
        else:
            self.compile_expression(start)
        if end is None:
            self.emit("LOAD_NOVA", node=node)
        else:
            self.compile_expression(end)
        self.emit("SLICE", node=node)

    def compile_access(self, value: dict, node: Any, safe: bool) -> None:
        target = value.get("target")
        property_node = value.get("property")
        property_name = property_node.get("value") if isinstance(property_node, dict) else property_node
        if safe:
            end_label = self.label()
            self.compile_expression(target)
            self.emit("DUP", node=node)
            self.emit_jump("JUMP_IF_NOVA", end_label, node)
        else:
            self.compile_expression(target)
        self.emit("LOAD_MEMBER_SAFE" if safe else "LOAD_MEMBER", self.name_const(str(property_name)), node=node)
        if safe:
            self.place(end_label)

    def compile_pipeline(self, left: Any, right: Any, node: Any) -> None:
        right_type = right.get("type") if isinstance(right, dict) else None
        temp = self._allocate_hidden("#pipe")
        self.compile_expression(left)
        self.emit("STORE_RAW", temp, node=node)
        if right_type == ParserTokenType.CALL_EXPRESSION:
            call_value = right.get("value", {})
            callee = call_value.get("callee")
            arguments = call_value.get("arguments") or []
            kinds, names = self.compile_arguments(arguments)
            self.emit("LOAD_RAW", temp, node=node)
            self.emit("ROT", len(kinds) + 1, node=node)
            site = self.make_call_site(
                dispatch="call", name=self.callee_name(callee), callee_ast=callee,
                argument_kinds=("positional",) + kinds,
                argument_names=("",) + names,
            )
            self.emit("CALL", self.c.call_site_id(site), node=node)
            return
        if right_type == ParserTokenType.METHOD_CALL:
            method_value = right.get("value", {})
            owner = method_value.get("owner")
            method = method_value.get("method", {}).get("value")
            arguments = method_value.get("arguments") or []
            owner_name = owner.get("value") if isinstance(owner, dict) else None
            if isinstance(owner, dict) and owner.get("type") == LexerTokenType.IDENTIFIER \
                    and owner_name in NATIVE_METHOD_TYPES:
                kinds, names = self.compile_arguments(arguments)
                self.emit("LOAD_RAW", temp, node=node)
                self.emit("ROT", len(kinds) + 1, node=node)
                site = self.make_call_site(
                    dispatch="native", name=str(method), native_type=owner_name,
                    callee_ast=owner, method_ast=method_value,
                    argument_kinds=("positional",) + kinds,
                    argument_names=("",) + names,
                )
                self.emit("CALL_NATIVE", self.c.call_site_id(site), node=node)
                return
            self.compile_expression(owner)
            self.emit("LOAD_RAW", temp, node=node)
            kinds, names = self.compile_arguments(arguments)
            site = self.make_call_site(
                dispatch="method", name=str(method), method_ast=method_value,
                argument_kinds=("positional",) + kinds,
                argument_names=("",) + names,
            )
            self.emit("CALL_METHOD", self.c.call_site_id(site), node=node)
            return
        if right_type == ParserTokenType.ACCESS_EXPRESSION:
            access_value = right.get("value", {})
            target = access_value.get("target")
            method_name = access_value.get("property", {}).get("value")
            target_name = target.get("value") if isinstance(target, dict) else None
            if isinstance(target, dict) and target.get("type") == LexerTokenType.IDENTIFIER \
                    and target_name in NATIVE_METHOD_TYPES:
                self.emit("LOAD_RAW", temp, node=node)
                site = self.make_call_site(
                    dispatch="native", name=str(method_name), native_type=target_name,
                    callee_ast=target, method_ast=access_value,
                    argument_kinds=("positional",), argument_names=("",),
                )
                self.emit("CALL_NATIVE", self.c.call_site_id(site), node=node)
                return
        self.compile_expression(right)
        self.emit("LOAD_RAW", temp, node=node)
        site = self.make_call_site(
            dispatch="value", name="<pipeline>", callee_ast=right,
            argument_kinds=("positional",), argument_names=("",),
        )
        self.emit("CALL_VALUE", self.c.call_site_id(site), node=node)

    def compile_argument(self, argument: Any) -> str:
        if isinstance(argument, dict) and argument.get("type") == ParserTokenType.NAMED_ARGUMENT:
            named_value = argument.get("value", {})
            name_node = named_value.get("name")
            self.compile_expression(named_value.get("value"))
            return str(name_node.get("value") if isinstance(name_node, dict) else "")
        if isinstance(argument, dict) and argument.get("type") == ParserTokenType.SPREAD_EXPRESSION:
            self.compile_expression(argument.get("value"))
            self.emit("MAKE_SPREAD")
            return "*"
        self.compile_expression(argument)
        return ""

    def compile_arguments(self, arguments: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
        kinds: list[str] = []
        names: list[str] = []
        for argument in arguments if isinstance(arguments, list) else []:
            if isinstance(argument, dict) and argument.get("type") == ParserTokenType.NAMED_ARGUMENT:
                named_value = argument.get("value", {})
                name_node = named_value.get("name")
                self.compile_expression(named_value.get("value"))
                kinds.append("named")
                names.append(str(name_node.get("value") if isinstance(name_node, dict) else ""))
            elif isinstance(argument, dict) and argument.get("type") == ParserTokenType.SPREAD_EXPRESSION:
                self.compile_expression(argument.get("value"))
                self.emit("MAKE_SPREAD")
                kinds.append("spread")
                names.append("")
            else:
                self.compile_expression(argument)
                kinds.append("positional")
                names.append("")
        return tuple(kinds), tuple(names)

    def callee_name(self, callee: Any) -> str:
        if isinstance(callee, dict) and callee.get("type") == LexerTokenType.IDENTIFIER:
            return str(callee.get("value"))
        if isinstance(callee, dict) and callee.get("type") == ParserTokenType.ACCESS_EXPRESSION:
            property_node = callee.get("value", {}).get("property")
            if isinstance(property_node, dict):
                return str(property_node.get("value"))
        return "<expression>"

    def make_call_site(self, **kwargs: Any) -> CallSite:
        extra_leading = int(kwargs.pop("extra_leading", 0))
        arguments = kwargs.pop("arguments", None)
        kinds = tuple(kwargs.pop("argument_kinds", ()))
        names = tuple(kwargs.pop("argument_names", ()))
        if arguments is not None:
            if not kinds:
                kinds = tuple("positional" for _ in arguments)
                names = tuple("" for _ in arguments)
        if extra_leading and kinds:
            kinds = ("positional",) * extra_leading + kinds
            names = ("",) * extra_leading + names
        elif extra_leading:
            kinds = ("positional",) * extra_leading
            names = ("",) * extra_leading
        positional_count = len(kinds)
        return CallSite(
            dispatch=kwargs.pop("dispatch", "call"),
            name=kwargs.pop("name", ""),
            module=kwargs.pop("module", None),
            type_name=kwargs.pop("type_name", None),
            trait_name=kwargs.pop("trait_name", None),
            operator_trait=kwargs.pop("operator_trait", None),
            native_type=kwargs.pop("native_type", None),
            positional_count=positional_count,
            argument_kinds=kinds,
            argument_names=names,
            type_argument_count=kwargs.pop("type_argument_count", 0),
            return_spec=kwargs.pop("return_spec", -1),
            is_async=kwargs.pop("is_async", False),
            callee_ast=kwargs.pop("callee_ast", None),
            method_ast=kwargs.pop("method_ast", None),
        )

    def compile_call(self, value: dict, node: Any) -> None:
        callee = value.get("callee")
        arguments = value.get("arguments") or []
        type_arguments = value.get("type_arguments") or []
        is_async = "async_result_type" in value
        callee_type = callee.get("type") if isinstance(callee, dict) else None
        if callee_type == LexerTokenType.IDENTIFIER:
            name = str(callee.get("value"))
            special = self.compile_special_builtin(name, arguments, node)
            if special:
                return
            kinds, names = self.compile_arguments(arguments)
            site = self.make_call_site(
                dispatch="call", name=name, callee_ast=callee,
                argument_kinds=kinds, argument_names=names,
                type_argument_count=len(type_arguments), is_async=is_async,
            )
            self.emit("CALL_ASYNC" if is_async else "CALL", self.c.call_site_id(site), node=callee)
            return
        if callee_type == ParserTokenType.ACCESS_EXPRESSION:
            access_value = callee.get("value", {})
            target = access_value.get("target")
            member = access_value.get("property", {}).get("value")
            owner_name = target.get("value") if isinstance(target, dict) else None
            if isinstance(target, dict) and target.get("type") == LexerTokenType.IDENTIFIER:
                if owner_name in self.c.module_traits or owner_name in OPERATOR_TRAIT_NAMES:
                    kinds, names = self.compile_arguments(arguments)
                    site = self.make_call_site(
                        dispatch="trait", name=str(member), trait_name=owner_name,
                        callee_ast=callee, argument_kinds=kinds, argument_names=names,
                        is_async=is_async,
                    )
                    self.emit("CALL_ASYNC" if is_async else "CALL_TRAIT", self.c.call_site_id(site), node=callee)
                    return
                if owner_name in self.c.module_types:
                    kinds, names = self.compile_arguments(arguments)
                    site = self.make_call_site(
                        dispatch="static", name=str(member), type_name=owner_name,
                        callee_ast=callee, argument_kinds=kinds, argument_names=names,
                        is_async=is_async,
                    )
                    self.emit("CALL_ASYNC" if is_async else "CALL_STATIC", self.c.call_site_id(site), node=callee)
                    return
            kinds, names = self.compile_arguments(arguments)
            self.compile_expression(target)
            self.emit("ROT", len(kinds) + 1, node=node)
            site = self.make_call_site(
                dispatch="module", name=str(member), callee_ast=callee,
                argument_kinds=kinds, argument_names=names, is_async=is_async,
            )
            self.emit("CALL_ASYNC" if is_async else "CALL_MODULE", self.c.call_site_id(site), node=callee)
            return
        kinds, names = self.compile_arguments(arguments)
        self.compile_expression(callee)
        self.emit("ROT", len(kinds) + 1, node=node)
        site = self.make_call_site(
            dispatch="value", name="<expression>", callee_ast=callee,
            argument_kinds=kinds, argument_names=names, is_async=is_async,
        )
        self.emit("CALL_ASYNC" if is_async else "CALL_VALUE", self.c.call_site_id(site), node=callee)

    def compile_special_builtin(self, name: str, arguments: list, node: Any) -> bool:
        if name not in {"error", "fail"}:
            return False
        if self.is_declared_anywhere(name):
            return False
        if not arguments:
            return False
        kinds, names = self.compile_arguments(arguments)
        mode = "raise" if name == "error" else "value"
        descriptor = {
            "kind": "error_spec",
            "mode": mode,
            "where": "builtin: error" if name == "error" else "builtin: fail",
            "has_kind": name == "fail",
            "argument_count": len(kinds),
        }
        self.emit("MAKE_ERROR", self.const("descriptor", descriptor), node=node)
        if name == "error":
            self.emit("THROW", node=node)
            self.emit("LOAD_NOVA", node=node)
        return True

    def compile_method_call(self, value: dict, node: Any) -> None:
        owner = value.get("owner")
        method_node = value.get("method")
        method = method_node.get("value") if isinstance(method_node, dict) else method_node
        arguments = value.get("arguments") or []
        resolved_trait = value.get("resolved_trait")
        is_async = "async_result_type" in value
        owner_type = owner.get("type") if isinstance(owner, dict) else None
        owner_name = owner.get("value") if isinstance(owner, dict) else None
        if owner_type == LexerTokenType.IDENTIFIER:
            if owner_name in self.c.module_traits or owner_name in OPERATOR_TRAIT_NAMES:
                kinds, names = self.compile_arguments(arguments)
                site = self.make_call_site(
                    dispatch="trait", name=str(method), trait_name=owner_name,
                    callee_ast=owner, method_ast=value,
                    argument_kinds=kinds, argument_names=names, is_async=is_async,
                )
                self.emit("CALL_ASYNC_METHOD" if is_async else "CALL_TRAIT", self.c.call_site_id(site), node=method_node)
                return
            if owner_name in NATIVE_METHOD_TYPES:
                kinds, names = self.compile_arguments(arguments)
                site = self.make_call_site(
                    dispatch="native", name=str(method), native_type=owner_name,
                    callee_ast=owner, method_ast=value,
                    argument_kinds=kinds, argument_names=names, is_async=is_async,
                )
                self.emit("CALL_ASYNC_METHOD" if is_async else "CALL_NATIVE", self.c.call_site_id(site), node=method_node)
                return
            if owner_name in self.c.module_types:
                kinds, names = self.compile_arguments(arguments)
                site = self.make_call_site(
                    dispatch="static", name=str(method), type_name=owner_name,
                    callee_ast=owner, method_ast=value,
                    argument_kinds=kinds, argument_names=names, is_async=is_async,
                )
                self.emit("CALL_ASYNC_METHOD" if is_async else "CALL_STATIC", self.c.call_site_id(site), node=method_node)
                return
        self.compile_expression(owner)
        kinds, names = self.compile_arguments(arguments)
        site = self.make_call_site(
            dispatch="method", name=str(method), trait_name=resolved_trait,
            callee_ast=owner, method_ast=value,
            argument_kinds=kinds, argument_names=names, is_async=is_async,
        )
        self.emit("CALL_ASYNC_METHOD" if is_async else "CALL_METHOD", self.c.call_site_id(site), node=method_node)

    def compile_instantiation(self, value: dict, node: Any) -> None:
        type_ref = value.get("type_ref", {})
        type_name = type_ref.get("name")
        arguments = value.get("arguments") or []
        kinds: list[str] = []
        names: list[str] = []
        for argument in arguments:
            if not isinstance(argument, dict):
                continue
            named = argument.get("name")
            argument_value = argument.get("value")
            if isinstance(named, str):
                self.compile_expression(argument_value)
                kinds.append("named")
                names.append(named)
            elif isinstance(argument_value, dict) and argument_value.get("type") == ParserTokenType.KEY_VALUE_PAIR:
                pair = argument_value.get("value", {})
                self.compile_expression(pair.get("key"))
                self.compile_expression(pair.get("value"))
                kinds.append("pair")
                names.append("")
            elif isinstance(argument_value, dict) and argument_value.get("type") == ParserTokenType.SPREAD_EXPRESSION:
                self.compile_expression(argument_value.get("value"))
                self.emit("MAKE_SPREAD")
                kinds.append("spread")
                names.append("")
            else:
                self.compile_expression(argument_value)
                kinds.append("positional")
                names.append("")
        stack_count = sum(2 if kind == "pair" else 1 for kind in kinds)
        site = CallSite(
            dispatch="construct",
            name=str(type_name),
            module=None,
            type_name=str(type_name),
            trait_name=None,
            operator_trait=None,
            native_type=None,
            positional_count=stack_count,
            argument_kinds=tuple(kinds),
            argument_names=tuple(names),
            type_argument_count=len(type_ref.get("type_parameters") or []),
            return_spec=-1,
            is_async=False,
            callee_ast=type_ref,
            method_ast=value,
        )
        type_index = self.c.types_name_index.get(type_name, -1)
        self.emit("CONSTRUCT", type_index if type_index >= 0 else 0, self.c.call_site_id(site), node=node)

    def compile_lambda(self, value: dict, node: Any) -> None:
        descriptor, fn_index = self.compile_function_node(
            {"type": ParserTokenType.DECLARATION_FUN, "value": {
                "identifier": {"type": LexerTokenType.IDENTIFIER, "value": value.get("name") or "<lambda>"},
                "args": value.get("args") or [],
                "min_argc": value.get("min_argc", 0),
                "return": value.get("return"),
                "block": value.get("block"),
                "instance_method": False,
                "trait_qualifier": None,
                "signature_only": False,
                "is_async": bool(value.get("is_async")),
                "type_parameters": value.get("type_parameters") or [],
                "variadic": bool(value.get("variadic")),
                "variadic_index": value.get("variadic_index"),
            }},
            is_lambda=True,
            lambda_name=value.get("name"),
            mutable_capture=bool(value.get("mutable_capture")),
        )
        self.emit("MAKE_FUNCTION", fn_index, node=node)

    def compile_reference(self, value: dict, node: Any) -> None:
        target = value.get("target")
        target_type = target.get("type") if isinstance(target, dict) else None
        if target_type == LexerTokenType.IDENTIFIER:
            name = target.get("value")
            slot = self.resolve_local(name) if isinstance(name, str) else None
            if slot is not None:
                self.emit("REF_LOCAL", slot, node=node)
            else:
                self.emit("REF_GLOBAL", self.name_const(str(name)), node=node)
            return
        if target_type == ParserTokenType.ACCESS_EXPRESSION:
            access_value = target.get("value", {})
            property_name = access_value.get("property", {}).get("value")
            self.compile_expression(access_value.get("target"))
            self.emit("REF_FIELD", self.name_const(str(property_name)), node=node)
            return
        if target_type == ParserTokenType.INDEX_EXPRESSION:
            index_value = target.get("value", {})
            self.compile_expression(index_value.get("target"))
            self.compile_expression(index_value.get("index"))
            self.emit("REF_INDEX", node=node)
            return
        raise CompileError("Invalid reference target", "compile")

    def compile_spawn(self, value: dict, node: Any) -> None:
        call_node = value.get("call")
        call_value = call_node.get("value", {}) if isinstance(call_node, dict) else {}
        if call_node.get("type") == ParserTokenType.METHOD_CALL:
            method_value = call_value
            owner = method_value.get("owner")
            method_node = method_value.get("method")
            method_name = method_node.get("value") if isinstance(method_node, dict) else "<spawn>"
            arguments = method_value.get("arguments") or []
            owner_name = owner.get("value") if isinstance(owner, dict) else None
            if isinstance(owner, dict) and owner.get("type") == LexerTokenType.IDENTIFIER \
                    and owner_name in self.c.module_types:
                kinds, names = self.compile_arguments(arguments)
                site = self.make_call_site(
                    dispatch="spawn_static", name=str(method_name),
                    type_name=owner_name, method_ast=method_value,
                    argument_kinds=kinds, argument_names=names,
                )
                self.emit("SPAWN", self.c.call_site_id(site), node=node)
                return
            self.compile_expression(owner)
            kinds, names = self.compile_arguments(arguments)
            site = self.make_call_site(
                dispatch="spawn", name=str(method_name), method_ast=method_value,
                argument_kinds=kinds, argument_names=names,
            )
            self.emit("SPAWN", self.c.call_site_id(site), node=node)
            return
        callee = call_value.get("callee")
        arguments = call_value.get("arguments") or []
        kinds, names = self.compile_arguments(arguments)
        site = self.make_call_site(
            dispatch="spawn", name=self.callee_name(callee), callee_ast=callee,
            argument_kinds=kinds, argument_names=names,
        )
        self.emit("SPAWN", self.c.call_site_id(site), node=node)

    # --------------------------------------------------------- declarations
    def _declare_target(self, name: str, *, allow_shadow: bool) -> tuple[bool, int, int]:
        """Return (is_global, slot, name_constant)."""
        if self.repl:
            return True, -1, self.name_const(name)
        slot = self.declare(name, allow_shadow=allow_shadow)
        return False, slot, -1

    def compile_declaration_undefined(self, value: dict, node: Any) -> None:
        identifier = value.get("identifier", {})
        name = identifier.get("value")
        if not isinstance(name, str):
            raise CompileError("Invalid declaration", "compile")
        type_node = value.get("type")
        if not isinstance(type_node, dict):
            type_node = _any_type_node()
        allow_shadow = self.in_nested_block() and self.resolve_local(name) is not None
        self.check_redeclare(name, allow_shadow, 'declaration undefined')
        is_global, slot, name_const = self._declare_target(name, allow_shadow=allow_shadow)
        shadow_flag = 1 if allow_shadow else 0
        if is_global:
            self.emit("DECLARE_UNDEFINED_GLOBAL", name_const, self.spec(type_node), shadow_flag, node=node)
        else:
            self.emit("DECLARE_LOCAL", slot, self.spec(type_node), shadow_flag, node=node)

    def compile_declaration_typed(self, value: dict, node: Any) -> None:
        identifier = value.get("identifier", {})
        name = identifier.get("value")
        if not isinstance(name, str):
            raise CompileError("Invalid declaration", "compile")
        type_node = value.get("type")
        if not isinstance(type_node, dict):
            type_node = _any_type_node()
        allow_shadow = self.in_nested_block() and self.resolve_local(name) is not None
        self.check_redeclare(name, allow_shadow, 'declaration typed var')
        self.compile_expression(value.get("expression"))
        is_global, slot, name_const = self._declare_target(name, allow_shadow=allow_shadow)
        if is_global:
            self.emit("DECLARE_TYPED_GLOBAL", name_const, self.spec(type_node), node=node)
        else:
            self.emit("DECLARE_TYPED", slot, self.spec(type_node), node=node)

    def compile_declaration_infer(self, value: dict, node: Any) -> None:
        identifier = value.get("identifier", {})
        name = identifier.get("value")
        if not isinstance(name, str):
            raise CompileError("Invalid declaration", "compile")
        allow_shadow = self.in_nested_block() and self.resolve_local(name) is not None
        self.check_redeclare(name, allow_shadow, 'declaration interpret')
        self.compile_expression(value.get("expression"))
        is_global, slot, name_const = self._declare_target(name, allow_shadow=allow_shadow)
        if is_global:
            self.emit("DECLARE_INFER_GLOBAL", name_const, node=node)
        else:
            self.emit("DECLARE_INFER", slot, node=node)

    def compile_destructure(self, value: dict, node: Any) -> None:
        pattern = value.get("pattern")
        pattern_value = pattern.get("value") if isinstance(pattern, dict) else pattern
        if not isinstance(pattern_value, dict):
            pattern_value = {}
        entries = pattern_value.get("entries") or []
        group_type = pattern_value.get("group_type")
        group_reference = bool(pattern_value.get("group_reference"))
        source_slot = self._allocate_hidden("#destructure")
        self.compile_expression(value.get("expression"))
        self.emit("STORE_RAW", source_slot, node=node)
        descriptor_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            identifier = entry.get("identifier", {})
            name = identifier.get("value")
            if not isinstance(name, str):
                continue
            allow_shadow = self.in_nested_block() and self.resolve_local(name) is not None
            self.check_redeclare(name, allow_shadow, 'destructure declaration')
            if self.repl:
                descriptor_entries.append({
                    "name": name, "slot": -1, "type": entry.get("type") or group_type,
                    "reference": bool(entry.get("reference")) or group_reference,
                })
            else:
                slot = self.declare(name, allow_shadow=allow_shadow)
                descriptor_entries.append({
                    "name": name, "slot": slot, "type": entry.get("type") or group_type,
                    "reference": bool(entry.get("reference")) or group_reference,
                })
        descriptor = {
            "kind": "destructure",
            "entries": descriptor_entries,
            "group_type": group_type,
            "group_reference": group_reference,
        }
        self.emit("DESTRUCTURE", self.const("descriptor", descriptor), source_slot, node=node)

    def compile_function_declaration(self, value: dict, node: Any) -> None:
        name = value.get("identifier", {}).get("value")
        if not isinstance(name, str):
            raise CompileError("Function declaration without a name", "compile")
        descriptor, fn_index = self.compile_function_node(node)
        self.emit("DECLARE_FUNCTION", fn_index, node=node)

    def compile_function_node(
        self,
        node: dict,
        *,
        owner_type: str | None = None,
        owner_trait: str | None = None,
        is_lambda: bool = False,
        lambda_name: str | None = None,
        mutable_capture: bool = False,
    ) -> tuple[dict, int]:
        value = node.get("value", {})
        name = value.get("identifier", {}).get("value")
        if not isinstance(name, str):
            name = "<lambda>" if is_lambda else "<function>"
        args = list(value.get("args") or [])
        return_node = value.get("return")
        block = value.get("block")
        body = list(block.get("value") or []) if isinstance(block, dict) else []
        if is_lambda:
            body = list(value.get("block", {}).get("value") or []) if isinstance(value.get("block"), dict) else []
        return_inner = return_node.get("value") if isinstance(return_node, dict) and return_node.get("type") == ParserTokenType.TYPE else return_node
        if return_node is None and not is_lambda:
            return_node = _inner_to_type_node({
                "value": PowangNova.type,
                "weak": False,
                "const": False,
                "error_union": False,
                "reference": False,
                "element_type": None,
                "generics": [],
                "variadic": False,
                "alternatives": [],
                "auto": False,
            })
            return_inner = return_node["value"]
        type_parameters = set(value.get("type_parameters") or [])
        instance_method = bool(value.get("instance_method"))
        is_static = bool(owner_type is not None and not instance_method and not is_lambda)
        is_method = bool(owner_type is not None and instance_method)
        flags = 0
        if value.get("is_async"):
            flags |= FLAG_ASYNC
        if value.get("variadic"):
            flags |= FLAG_VARIADIC
        if is_method:
            flags |= FLAG_METHOD
        if is_static:
            flags |= FLAG_STATIC
        qualname = name if owner_type is None else f"{owner_type}.{name}"
        child = FunctionCompiler(
            self.c,
            name=name,
            qualname=qualname,
            params=args,
            is_function=True,
            is_method=is_method,
            is_static=is_static,
            is_async=bool(value.get("is_async")),
            return_node=return_node,
            type_parameters=type_parameters,
            fallback_ast=body,
        )
        for argument in args:
            default_code = child.compile_default_for(argument)
            child.default_codes.append(default_code)
        for statement in body:
            child.compile_statement(statement)
        if return_node is not None:
            child.emit("LOAD_NOVA")
            child.emit("CAST_RETURN", child.spec(return_node))
            child.emit("RETURN")
        else:
            child.emit("LOAD_NOVA")
            child.emit("RETURN")
        code = child.finish(flags=flags)
        code_index = self.c.add_code(code)
        info = FunctionInfo(
            name=name,
            code_index=code_index,
            args=list(args),
            min_argc=int(value.get("min_argc", len(args))),
            return_node=return_inner,
            flags={
                "is_async": bool(value.get("is_async")),
                "is_lambda": is_lambda,
                "mutable_capture": mutable_capture,
                "variadic": bool(value.get("variadic")),
                "variadic_index": value.get("variadic_index"),
                "type_parameters": list(value.get("type_parameters") or []),
                "function_type": self._function_type(args, return_node),
                "instance_method": instance_method,
                "trait_qualifier": value.get("trait_qualifier", {}).get("value") if isinstance(value.get("trait_qualifier"), dict) else None,
                "is_static": is_static,
                "lambda_name": lambda_name,
                "signature_only": bool(value.get("signature_only")),
                "trait_member": bool(value.get("trait_member")),
                "defaults": list(child.default_codes),
                "body": body,
            },
        )
        fn_index = self.c.add_function(info)
        descriptor = {
            "kind": "function",
            "name": name,
            "code": code_index,
            "function": fn_index,
            "args": args,
            "min_argc": int(value.get("min_argc", len(args))),
            "return_node": return_node,
            "return_inner": return_inner,
            "flags": info.flags,
            "body": body,
        }
        return descriptor, fn_index

    def _function_type(self, args: list, return_node: Any) -> Optional[str]:
        from ..runtime import _lambda_function_type
        try:
            return _lambda_function_type(args, return_node)
        except Exception:
            return None

    def compile_default_for(self, argument: Any) -> int:
        argument_value = argument.get("value") if isinstance(argument, dict) else None
        if not isinstance(argument_value, dict):
            return -1
        expression = argument_value.get("expression")
        if expression is None:
            return -1
        child = FunctionCompiler(
            self.c,
            name="<default>",
            qualname=f"{self.qualname}.<default>",
            params=(),
            is_function=True,
            is_method=self.is_method,
            is_static=self.is_static,
            return_node=None,
        )
        child.compile_expression(expression)
        child.emit("RETURN")
        code = child.finish(flags=0)
        return self.c.add_code(code)

    def compile_type_declaration(self, value: dict, node: Any) -> None:
        name = value.get("identifier", {}).get("value")
        if not isinstance(name, str):
            raise CompileError("Type declaration without a name", "compile")
        type_parameters = set(value.get("type_parameters") or [])
        if value.get("is_enum"):
            info = TypeInfo(
                name=name,
                kind="enum",
                type_parameters=tuple(value.get("type_parameters") or []),
                properties=(),
                methods=(),
                variants=tuple(value.get("variants") or []),
            )
            index = self.c.add_type(info)
            self.c.module_types.add(name)
            self.emit("DECLARE_TYPE", index, node=node)
            return
        properties = []
        for entry in value.get("properties") or []:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                public, property_node = entry
                property_node = _replace_type_parameters(property_node, type_parameters)
                property_value = property_node.get("value", {})
                property_name = property_value.get("identifier", {}).get("value")
                if isinstance(property_name, str):
                    properties.append((bool(public), property_name, self.c.type_spec_id(property_node), property_value.get("explicit_access")))
        methods = []
        for entry in value.get("methods") or []:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                public, method_node = entry
                method_node = _replace_type_parameters(method_node, type_parameters)
                method_value = method_node.get("value", {})
                method_name = method_value.get("identifier", {}).get("value")
                if not isinstance(method_name, str):
                    continue
                if method_value.get("signature_only") or method_value.get("block") is None:
                    methods.append((bool(public), method_name, -1, None, bool(method_value.get("instance_method"))))
                    continue
                _, fn_index = self.compile_function_node(method_node, owner_type=name)
                qualifier_node = method_value.get("trait_qualifier")
                qualifier = qualifier_node.get("value") if isinstance(qualifier_node, dict) else None
                methods.append((bool(public), method_name, fn_index, qualifier, bool(method_value.get("instance_method"))))
        info = TypeInfo(
            name=name,
            kind="object",
            type_parameters=tuple(value.get("type_parameters") or []),
            properties=tuple(properties),
            methods=tuple(methods),
            variants=(),
        )
        index = self.c.add_type(info)
        self.c.module_types.add(name)
        self.emit("DECLARE_TYPE", index, node=node)

    def compile_trait_declaration(self, value: dict, node: Any) -> None:
        name = value.get("identifier", {}).get("value")
        if not isinstance(name, str):
            raise CompileError("Trait declaration without a name", "compile")
        properties = []
        for property_node in value.get("properties") or []:
            property_value = property_node.get("value", {}) if isinstance(property_node, dict) else {}
            property_name = property_value.get("identifier", {}).get("value")
            if isinstance(property_name, str):
                properties.append(property_name)
        methods = []
        for method_node in value.get("methods") or []:
            method_value = method_node.get("value", {}) if isinstance(method_node, dict) else {}
            method_name = method_value.get("identifier", {}).get("value")
            if not isinstance(method_name, str):
                continue
            signature_only = bool(method_value.get("signature_only")) or method_value.get("block") is None
            if signature_only:
                methods.append((method_name, -1, True))
                continue
            _, fn_index = self.compile_function_node(method_node, owner_type=name)
            methods.append((method_name, fn_index, False))
        info = TraitInfo(
            name=name,
            properties=tuple(properties),
            methods=tuple(methods),
        )
        index = self.c.add_trait(info)
        self.c.module_traits.add(name)
        self.emit("DECLARE_TRAIT", index, node=node)
        self.emit("LOAD_NOVA", node=node)

    def compile_use(self, value: dict, node: Any) -> None:
        descriptor = {**value, "kind": value.get("kind", "name")}
        self.imports.append(descriptor)
        index = self.c.add_module(ModuleInfo(
            name=str(value.get("name") or ""),
            path=str(self.c.path),
            code_index=0,
            imports=(descriptor,),
            exports=(),
        ))
        if value.get("wildcard"):
            self.emit("IMPORT_WILDCARD", index, node=node)
            self.emit("LOAD_NOVA", node=node)
            return
        alias = value.get("alias")
        if not isinstance(alias, str) or not alias:
            raw_name = str(value.get("name") or "")
            alias = Path(raw_name).stem
        allow_shadow = self.in_nested_block() and self.resolve_local(alias) is not None
        slot = self.declare(alias, allow_shadow=allow_shadow)
        self.emit("IMPORT", index, slot, node=node)
        self.emit("LOAD_NOVA", node=node)

    def compile_extern(self, value: dict, node: Any) -> None:
        descriptor = {
            "kind": "extern",
            "powang": value.get("powang"),
            "python": value.get("python"),
        }
        index = self.const("descriptor", descriptor)
        self.emit("DECLARE_EXTERN", index, node=node)
        self.emit("LOAD_NOVA", node=node)

    # ------------------------------------------------------------ assignment
    def compile_assignment(self, value: dict, node: Any, want_value: bool) -> None:
        target = value.get("target")
        expression = value.get("expression")
        target_type = target.get("type") if isinstance(target, dict) else None
        if target_type == ParserTokenType.ACCESS_EXPRESSION:
            access_value = target.get("value", {})
            owner = access_value.get("target")
            property_name = access_value.get("property", {}).get("value")
            self.compile_expression(owner)
            self.emit("POP", node=node)
            self.compile_expression(owner)
            self.compile_expression(expression)
            self.emit("STORE_MEMBER", self.name_const(str(property_name)), node=node)
            if not want_value:
                self.emit("POP", node=node)
            return
        if target_type == ParserTokenType.INDEX_EXPRESSION:
            index_value = target.get("value", {})
            self.compile_expression(index_value.get("target"))
            self.compile_expression(index_value.get("index"))
            self.compile_expression(expression)
            self.emit("INDEX_SET", node=node)
            if not want_value:
                self.emit("POP", node=node)
            return
        if target_type == LexerTokenType.IDENTIFIER:
            name = target.get("value")
            if not isinstance(name, str):
                raise CompileError("Invalid assignment target", "compile")
            self.compile_expression(expression)
            if want_value:
                self.emit("DUP", node=node)
            slot = self.resolve_local(name)
            if slot is not None:
                self.emit("ASSIGN_LOCAL", slot, node=node)
            else:
                self.emit("ASSIGN_NAME", self.name_const(name), node=node)
            return
        raise CompileError("Invalid assignment target", "compile")

    # ------------------------------------------------------------------ finish
    def finish(self, flags: int = 0) -> CodeObject:
        self.b.set_parameter_names(self.parameter_names)
        self.b.patch()
        exception_entries: list[ExceptionEntry] = []
        for pending in self.pending_exceptions:
            exception_entries.append(ExceptionEntry(
                start_ip=self.b.label_offset(pending.start),
                end_ip=self.b.label_offset(pending.end),
                catch_ip=(
                    self.b.label_offset(pending.catch)
                    if isinstance(pending.catch, Label) else int(pending.catch)
                ),
                finally_ip=(
                    self.b.label_offset(pending.finally_)
                    if isinstance(pending.finally_, Label) else int(pending.finally_)
                ),
                resume_ip=self.b.label_offset(pending.resume),
                stack_depth=pending.stack_depth,
                local_watermark=pending.local_watermark or len(self.display_names),
                kind=pending.kind,
            ))
        return self.b.finish(
            local_count=len(self.display_names),
            capture_count=0,
            flags=flags,
            return_spec=(
                self.c.type_spec_id(self.return_node)
                if self.return_node is not None else -1
            ),
            fallback_ast=self.fallback_ast,
            exception_table=exception_entries,
        )


def _collect_declarations(program_ast: list[DictRepr], compilation: Compilation) -> None:
    for statement in program_ast:
        if not isinstance(statement, dict):
            continue
        node_type = statement.get("type")
        value = statement.get("value")
        if not isinstance(value, dict):
            continue
        if node_type == ParserTokenType.DECLARATION_FUN:
            name = value.get("identifier", {}).get("value")
            if isinstance(name, str):
                compilation.module_functions.add(name)
                compilation.module_declared.add(name)
        elif node_type == ParserTokenType.DECLARATION_UNDEFINED:
            name = value.get("identifier", {}).get("value")
            if isinstance(name, str):
                compilation.module_declared.add(name)
        elif node_type == ParserTokenType.DECLARATION_TYPED_VAR:
            name = value.get("identifier", {}).get("value")
            if isinstance(name, str):
                compilation.module_declared.add(name)
        elif node_type == ParserTokenType.DECLARATION_INTERPRET:
            name = value.get("identifier", {}).get("value")
            if isinstance(name, str):
                compilation.module_declared.add(name)
        elif node_type == ParserTokenType.TYPE_DECLARATION:
            name = value.get("identifier", {}).get("value")
            if isinstance(name, str):
                compilation.module_types.add(name)
                compilation.module_declared.add(name)
        elif node_type == ParserTokenType.TRAIT_DECLARATION:
            name = value.get("identifier", {}).get("value")
            if isinstance(name, str):
                compilation.module_traits.add(name)
                compilation.module_declared.add(name)
        elif node_type == ParserTokenType.DESTRUCTURE_DECLARATION:
            pattern = value.get("pattern")
            pattern_value = pattern.get("value") if isinstance(pattern, dict) else pattern
            if isinstance(pattern_value, dict):
                for entry in pattern_value.get("entries") or []:
                    if isinstance(entry, dict):
                        name = entry.get("identifier", {}).get("value")
                        if isinstance(name, str):
                            compilation.module_declared.add(name)
        elif node_type == ParserTokenType.USE_EXPRESSION:
            alias = value.get("alias")
            if not isinstance(alias, str) or not alias:
                alias = Path(str(value.get("name") or "")).stem
            compilation.module_declared.add(alias)


def _exports(program_ast: list[DictRepr]) -> tuple[bool, list[tuple[str, str]]]:
    exported: list[tuple[str, str]] = []
    has_exports = False
    for statement in program_ast:
        if not isinstance(statement, dict) or not statement.get("exported"):
            continue
        has_exports = True
        statement_type = statement.get("type")
        value = statement.get("value")
        if statement_type == ParserTokenType.EXTERN_REFERENCE and isinstance(value, dict):
            inner = value.get("powang")
            if isinstance(inner, dict):
                statement_type = inner.get("type")
                value = inner.get("value")
        if statement_type not in {
            ParserTokenType.DECLARATION_FUN,
            ParserTokenType.DECLARATION_UNDEFINED,
            ParserTokenType.DECLARATION_TYPED_VAR,
            ParserTokenType.DECLARATION_INTERPRET,
            ParserTokenType.TYPE_DECLARATION,
        } or not isinstance(value, dict):
            continue
        identifier = value.get("identifier")
        if not isinstance(identifier, dict):
            continue
        name = identifier.get("value")
        if not isinstance(name, str):
            continue
        kind = "function" if statement_type == ParserTokenType.DECLARATION_FUN else (
            "type" if statement_type == ParserTokenType.TYPE_DECLARATION else "variable"
        )
        exported.append((name, kind))
    return has_exports, exported


def collect_program_globals(program_ast: list[DictRepr]) -> set[str]:
    """Return the top level declaration names of a parsed program."""
    compilation = Compilation("<cache>", "<cache>")
    _collect_declarations(program_ast, compilation)
    return set(compilation.module_declared)


def compile_ast(
    program_ast: list[DictRepr],
    *,
    path: str | Path,
    module_name: str = "main",
    state=None,
    repl: bool = False,
) -> ProgramImage:
    """Compile one parsed module into a program image."""
    compilation = Compilation(path, module_name, state=state, repl=repl)
    _collect_declarations(program_ast, compilation)
    has_exports, exported = _exports(program_ast)
    compiler = FunctionCompiler(
        compilation,
        name=module_name,
        qualname=module_name,
        params=(),
        is_function=False,
        fallback_ast=list(program_ast),
        source_path=path,
    )
    compiler._result_slot = compiler._allocate_hidden("#result")
    compiler.emit("LOAD_NOVA")
    compiler.emit("STORE_LOCAL", compiler._result_slot)
    for statement in program_ast:
        compiler.emit("CHECK_CANCEL", node=statement)
        if isinstance(statement, dict) and \
                statement.get("type") == ParserTokenType.BLOCK_STATEMENT:
            compiler.compile_bare_block(statement.get("value"), want_value=True)
        else:
            compiler.compile_expression(statement)
        compiler.emit("STORE_RAW", compiler._result_slot, node=statement)
    compiler.emit("LOAD_LOCAL", compiler._result_slot)
    compiler.emit("RETURN")
    code = compiler.finish(flags=0)
    code_index = compilation.add_code(code)
    module = ModuleInfo(
        name=module_name,
        path=str(Path(path).resolve()) if path is not None else str(path),
        code_index=code_index,
        imports=tuple(compiler.imports),
        exports=tuple(exported),
    )
    compilation.modules.append(module)
    entry_module = len(compilation.modules) - 1
    module.exports = tuple(exported)
    module.has_exports = has_exports  # type: ignore[attr-defined]
    result = compilation.image(entry_module, code_index)
    _link_constants(result)
    result.entry_ast = list(program_ast)  # type: ignore[attr-defined]
    result.vm_globals = set(compilation.module_declared)  # type: ignore[attr-defined]
    return result


def _link_constants(image: ProgramImage) -> None:
    """Build the image constant pool and rewrite per code indices.

    The verifier treats ``constant_indices`` as indices into the image pool, so
    each code object's inline constants are deduplicated into one image table.
    """
    global_constants: list[Any] = []
    keys: dict[tuple[str, str], int] = {}
    for code in image.codes:
        indices: list[int] = []
        for constant in code.constants:
            key = (constant.kind, stable_key(constant.value))
            index = keys.get(key)
            if index is None:
                index = len(global_constants)
                global_constants.append(constant)
                keys[key] = index
            indices.append(index)
        code.constant_indices = tuple(indices)
    image.constants = global_constants


def compile_source(
    source: str,
    *,
    path: str | Path,
    module_name: str = "main",
    check: bool = False,
    state=None,
    repl: bool = False,
) -> ProgramImage:
    """Parse, optionally check and lower one source file."""
    from ..parser import Parser
    from ..simplify import simplify_program
    from ..typecheck import type_check
    from ..state import get_state

    active_state = state if state is not None else get_state()
    parser = Parser(source, source_path=Path(path))
    try:
        program_ast = parser.parse()
    except PowangError as error:
        if error.line is not None:
            raise
        raise error.with_line(parser.tokenizer.row + 1) from None
    program_ast = simplify_program(program_ast, active_state.warn)
    if check:
        errors = type_check(program_ast, str(Path(path).resolve()))
        if errors:
            errors[0]._from_type_check = True  # type: ignore[attr-defined]
            raise errors[0]
    return compile_ast(program_ast, path=path, module_name=module_name,
                       state=active_state, repl=repl)
