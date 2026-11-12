"""Program image dataclasses and the deterministic binary codec.

A program image is the unit that the compiler produces, the verifier checks
and the interpreter runs. This module owns the table layouts and a little
endian `PWB1` container. The container is deterministic, uses CRC32 for
integrity and never relies on Python pickles.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from .values import decode_constant_json, encode_constant_json


FORMAT_MAGIC = b"PWB1"
FORMAT_VERSION = 1
LANGUAGE_VERSION = "0.22.0"

FLAG_ASYNC = 0x01
FLAG_VARIADIC = 0x02
FLAG_METHOD = 0x04
FLAG_STATIC = 0x08

CONSTANT_KINDS: tuple[str, ...] = (
    "nova",
    "bool",
    "int",
    "bigint",
    "num",
    "str",
    "char",
    "ast",
    "call",
    "pattern",
    "spec",
    "type",
    "trait",
    "function",
    "extern",
    "descriptor",
    "tuple",
)

_CONSTANT_TAGS: dict[str, int] = {kind: index for index, kind in enumerate(CONSTANT_KINDS)}
_CONSTANT_BY_TAG: dict[int, str] = {index: kind for kind, index in _CONSTANT_TAGS.items()}

TABLE_NAMES: tuple[str, ...] = (
    "meta",
    "modules",
    "types",
    "traits",
    "functions",
    "constants",
    "call_sites",
    "patterns",
    "type_specs",
    "sources",
    "global_names",
    "strings",
    "debug_lines",
    "codes",
)


@dataclass(frozen=True)
class SourceSpan:
    """One source range attached to an instruction."""

    file_id: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class ExceptionEntry:
    """One protected range in a code object."""

    start_ip: int
    end_ip: int
    catch_ip: int
    finally_ip: int
    resume_ip: int
    stack_depth: int
    local_watermark: int
    kind: str


@dataclass(frozen=True)
class Constant:
    """One constant pool entry."""

    kind: str
    value: Any


@dataclass
class CodeObject:
    """One executable code object."""

    name: str
    qualname: str = ""
    source_file: int = 0
    parameter_count: int = 0
    local_count: int = 0
    capture_count: int = 0
    max_stack: int = 0
    max_frame_depth: int = 1
    bytecode: bytes = b""
    constant_indices: tuple[int, ...] = ()
    constants: tuple[Constant, ...] = ()
    spans: tuple[SourceSpan, ...] = ()
    span_table: tuple[int, ...] = ()
    exception_table: tuple[ExceptionEntry, ...] = ()
    local_names: tuple[str, ...] = ()
    parameter_names: tuple[str, ...] = ()
    return_spec: int = -1
    flags: int = 0
    trait_name: str | None = None
    operator_trait: str | None = None
    fallback_ast: Any = None

    @property
    def is_async(self) -> bool:
        return bool(self.flags & FLAG_ASYNC)

    @property
    def is_variadic(self) -> bool:
        return bool(self.flags & FLAG_VARIADIC)

    @property
    def is_method(self) -> bool:
        return bool(self.flags & FLAG_METHOD)

    @property
    def is_static(self) -> bool:
        return bool(self.flags & FLAG_STATIC)


@dataclass
class CallSite:
    """One call descriptor referenced by a call instruction."""

    dispatch: str = "call"
    name: str = ""
    module: str | None = None
    type_name: str | None = None
    trait_name: str | None = None
    operator_trait: str | None = None
    native_type: str | None = None
    positional_count: int = 0
    argument_kinds: tuple[str, ...] = ()
    argument_names: tuple[str, ...] = ()
    type_argument_count: int = 0
    return_spec: int = -1
    is_async: bool = False
    callee_ast: Any = None
    method_ast: Any = None


@dataclass
class PatternDescriptor:
    """One match pattern descriptor."""

    kind: str = "wildcard"
    literal: Any = None
    bindings: tuple[tuple[str, int], ...] = ()
    nested: tuple["PatternDescriptor", ...] = ()
    type_name: str | None = None
    fields: tuple[tuple[str, "PatternDescriptor"], ...] = ()
    rest_slot: int = -1
    start_ast: Any = None
    end_ast: Any = None


@dataclass
class TypeInfo:
    """One declared object or enum type."""

    name: str = ""
    kind: str = "object"
    type_parameters: tuple[str, ...] = ()
    properties: tuple[tuple[bool, str, int, str | None], ...] = ()
    methods: tuple[tuple[bool, str, int, str | None, bool], ...] = ()
    variants: tuple[str, ...] = ()


@dataclass
class TraitInfo:
    """One declared trait."""

    name: str = ""
    properties: tuple[str, ...] = ()
    methods: tuple[tuple[str, int, bool], ...] = ()


@dataclass
class FunctionInfo:
    """One declared function signature."""

    name: str = ""
    code_index: int = 0
    args: Any = None
    min_argc: int = 0
    return_node: Any = None
    flags: dict[str, Any] = field(default_factory=dict)
    body: Any = None


@dataclass
class ModuleInfo:
    """One module in the image."""

    name: str = ""
    path: str = ""
    code_index: int = 0
    imports: tuple[Any, ...] = ()
    exports: tuple[tuple[str, str], ...] = ()


@dataclass
class ProgramImage:
    """A complete program image."""

    format_version: int = FORMAT_VERSION
    language_version: str = LANGUAGE_VERSION
    flags: int = 0
    entry_module: int = 0
    entry_code: int = 0
    modules: list[ModuleInfo] = field(default_factory=list)
    types: list[TypeInfo] = field(default_factory=list)
    traits: list[TraitInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    constants: list[Constant] = field(default_factory=list)
    call_sites: list[CallSite] = field(default_factory=list)
    patterns: list[PatternDescriptor] = field(default_factory=list)
    type_specs: list[Any] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    global_names: list[str] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)
    debug_lines: list[Any] = field(default_factory=list)
    codes: list[CodeObject] = field(default_factory=list)

    def code(self, index: int) -> CodeObject:
        return _at(self.codes, index, "code")

    def constant(self, index: int) -> Constant:
        return _at(self.constants, index, "constant")

    def call_site(self, index: int) -> CallSite:
        return _at(self.call_sites, index, "call site")

    def pattern(self, index: int) -> PatternDescriptor:
        return _at(self.patterns, index, "pattern")

    def type_info(self, index: int) -> TypeInfo:
        return _at(self.types, index, "type")

    def trait_info(self, index: int) -> TraitInfo:
        return _at(self.traits, index, "trait")

    def function_info(self, index: int) -> FunctionInfo:
        return _at(self.functions, index, "function")

    def module_info(self, index: int) -> ModuleInfo:
        return _at(self.modules, index, "module")

    def to_bytes(self) -> bytes:
        return _write_image(self)

    @classmethod
    def from_bytes(cls, data: bytes) -> "ProgramImage":
        return _read_image(data)


def _at(values: list[Any], index: int, kind: str) -> Any:
    try:
        return values[index]
    except IndexError as exc:
        raise IndexError(f"{kind} index out of range: {index}") from exc


# ---------------------------------------------------------------------------
# Primitive writers and readers.


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def take(self, count: int, what: str = "data") -> bytes:
        if count < 0 or self.offset + count > len(self.data):
            raise ValueError(f"truncated image while reading {what} at offset {self.offset}")
        chunk = self.data[self.offset : self.offset + count]
        self.offset += count
        return chunk

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def u8(self, what: str = "u8") -> int:
        return struct.unpack("<B", self.take(1, what))[0]

    def u16(self, what: str = "u16") -> int:
        return struct.unpack("<H", self.take(2, what))[0]

    def u32(self, what: str = "u32") -> int:
        return struct.unpack("<I", self.take(4, what))[0]

    def i32(self, what: str = "i32") -> int:
        return struct.unpack("<i", self.take(4, what))[0]

    def i64(self, what: str = "i64") -> int:
        return struct.unpack("<q", self.take(8, what))[0]

    def f64(self, what: str = "f64") -> float:
        return struct.unpack("<d", self.take(8, what))[0]

    def string(self, what: str = "string") -> str:
        length = self.u32(f"{what} length")
        raw = self.take(length, what)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"invalid UTF-8 in {what}: {exc}") from exc


def _u8(out: bytearray, value: int) -> None:
    out += struct.pack("<B", value)


def _u16(out: bytearray, value: int) -> None:
    out += struct.pack("<H", value)


def _u32(out: bytearray, value: int) -> None:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"value out of range for u32: {value}")
    out += struct.pack("<I", value)


def _signed_index(value: int) -> int:
    """Decode the 0xFFFFFFFF absent marker back to -1."""
    return -1 if value == 0xFFFFFFFF else value


def _i32(out: bytearray, value: int) -> None:
    out += struct.pack("<i", value)


def _i64(out: bytearray, value: int) -> None:
    try:
        out += struct.pack("<q", value)
    except struct.error as exc:
        raise ValueError(f"value out of range for i64: {value}") from exc


def _f64(out: bytearray, value: float) -> None:
    out += struct.pack("<d", value)


def _string(out: bytearray, text: str) -> None:
    raw = text.encode("utf-8")
    if len(raw) > 0xFFFFFFFF:
        raise ValueError("string is too long to encode")
    _u32(out, len(raw))
    out += raw


def _optional_string(out: bytearray, text: str | None) -> None:
    if text is None:
        _u8(out, 0)
        return
    _u8(out, 1)
    _string(out, text)


def _json(out: bytearray, value: Any) -> None:
    _string(out, encode_constant_json(value))


def _read_optional_string(reader: _Reader, what: str = "string") -> str | None:
    present = reader.u8(f"{what} presence")
    if not present:
        return None
    return reader.string(what)


def _read_json(reader: _Reader, what: str = "json") -> Any:
    return decode_constant_json(reader.string(what))


# ---------------------------------------------------------------------------
# Constant codec.


def _write_constant(out: bytearray, constant: Constant) -> None:
    if not isinstance(constant, Constant):
        raise ValueError(f"expected Constant, got {type(constant).__name__}")
    tag = _CONSTANT_TAGS.get(constant.kind)
    if tag is None:
        raise ValueError(f"unknown constant kind: {constant.kind}")
    _u8(out, tag)
    kind = constant.kind
    value = constant.value
    if kind == "nova":
        return
    if kind == "bool":
        _u8(out, 1 if value else 0)
        return
    if kind == "int":
        _i64(out, int(value))
        return
    if kind == "bigint":
        _string(out, str(int(value)))
        return
    if kind == "num":
        _f64(out, float(value))
        return
    if kind == "str":
        _string(out, str(value))
        return
    if kind == "char":
        code = ord(value) if isinstance(value, str) else int(value)
        _u32(out, code)
        return
    if kind in {"ast", "descriptor", "spec", "extern"}:
        _json(out, value)
        return
    if kind in {"call", "pattern", "type", "trait", "function"}:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"constant {kind} must hold an index, got {value!r}")
        _u32(out, value)
        return
    if kind == "tuple":
        if not isinstance(value, (tuple, list)):
            raise ValueError(f"constant tuple must hold a sequence, got {value!r}")
        _u32(out, len(value))
        for item in value:
            _write_constant(out, item)
        return
    raise ValueError(f"unknown constant kind: {kind}")


def _read_constant(reader: _Reader) -> Constant:
    tag = reader.u8("constant tag")
    kind = _CONSTANT_BY_TAG.get(tag)
    if kind is None:
        raise ValueError(f"unknown constant tag: {tag}")
    if kind == "nova":
        return Constant("nova", None)
    if kind == "bool":
        return Constant("bool", bool(reader.u8("bool constant")))
    if kind == "int":
        return Constant("int", reader.i64("int constant"))
    if kind == "bigint":
        return Constant("bigint", int(reader.string("bigint constant")))
    if kind == "num":
        return Constant("num", reader.f64("num constant"))
    if kind == "str":
        return Constant("str", reader.string("str constant"))
    if kind == "char":
        return Constant("char", reader.u32("char constant"))
    if kind in {"ast", "descriptor", "spec", "extern"}:
        return Constant(kind, _read_json(reader, f"{kind} constant"))
    if kind in {"call", "pattern", "type", "trait", "function"}:
        return Constant(kind, reader.u32(f"{kind} constant"))
    if kind == "tuple":
        count = reader.u32("tuple constant count")
        return Constant("tuple", tuple(_read_constant(reader) for _ in range(count)))
    raise ValueError(f"unknown constant kind: {kind}")


# ---------------------------------------------------------------------------
# Table codecs.


def _write_source_span(out: bytearray, span: SourceSpan) -> None:
    _u32(out, span.file_id)
    _u32(out, span.start_line)
    _u32(out, span.start_column)
    _u32(out, span.end_line)
    _u32(out, span.end_column)


def _read_source_span(reader: _Reader) -> SourceSpan:
    return SourceSpan(
        reader.u32("span file"),
        reader.u32("span start line"),
        reader.u32("span start column"),
        reader.u32("span end line"),
        reader.u32("span end column"),
    )


def _write_exception_entry(out: bytearray, entry: ExceptionEntry) -> None:
    _i32(out, entry.start_ip)
    _i32(out, entry.end_ip)
    _i32(out, entry.catch_ip)
    _i32(out, entry.finally_ip)
    _i32(out, entry.resume_ip)
    _u32(out, entry.stack_depth)
    _u32(out, entry.local_watermark)
    if entry.kind == "catch":
        _u8(out, 0)
    elif entry.kind == "finally":
        _u8(out, 1)
    else:
        raise ValueError(f"unknown exception entry kind: {entry.kind}")


def _read_exception_entry(reader: _Reader) -> ExceptionEntry:
    start_ip = reader.i32("exception start")
    end_ip = reader.i32("exception end")
    catch_ip = reader.i32("exception catch")
    finally_ip = reader.i32("exception finally")
    resume_ip = reader.i32("exception resume")
    stack_depth = reader.u32("exception stack depth")
    local_watermark = reader.u32("exception local watermark")
    kind_code = reader.u8("exception kind")
    kind = {0: "catch", 1: "finally"}.get(kind_code)
    if kind is None:
        raise ValueError(f"unknown exception kind tag: {kind_code}")
    return ExceptionEntry(
        start_ip=start_ip,
        end_ip=end_ip,
        catch_ip=catch_ip,
        finally_ip=finally_ip,
        resume_ip=resume_ip,
        stack_depth=stack_depth,
        local_watermark=local_watermark,
        kind=kind,
    )


def _write_code(out: bytearray, code: CodeObject) -> None:
    _string(out, code.name)
    _string(out, code.qualname)
    _u32(out, code.source_file)
    _u32(out, code.parameter_count)
    _u32(out, code.local_count)
    _u32(out, code.capture_count)
    _u32(out, code.max_stack)
    _u32(out, code.max_frame_depth)
    _u32(out, len(code.bytecode))
    out += code.bytecode
    _u32(out, len(code.constant_indices))
    for index in code.constant_indices:
        _u32(out, index)
    _u32(out, len(code.constants))
    for constant in code.constants:
        _write_constant(out, constant)
    _u32(out, len(code.spans))
    for span in code.spans:
        _write_source_span(out, span)
    _u32(out, len(code.span_table))
    for index in code.span_table:
        _u32(out, index)
    _u32(out, len(code.exception_table))
    for entry in code.exception_table:
        _write_exception_entry(out, entry)
    _u32(out, len(code.local_names))
    for name in code.local_names:
        _string(out, name)
    _u32(out, len(code.parameter_names))
    for name in code.parameter_names:
        _string(out, name)
    _i32(out, code.return_spec)
    _u32(out, code.flags)
    _optional_string(out, code.trait_name)
    _optional_string(out, code.operator_trait)
    _json(out, code.fallback_ast)


def _read_code(reader: _Reader) -> CodeObject:
    name = reader.string("code name")
    qualname = reader.string("code qualname")
    source_file = reader.u32("code source file")
    parameter_count = reader.u32("code parameter count")
    local_count = reader.u32("code local count")
    capture_count = reader.u32("code capture count")
    max_stack = reader.u32("code max stack")
    max_frame_depth = reader.u32("code max frame depth")
    bytecode = reader.take(reader.u32("code bytecode length"), "code bytecode")
    constant_indices = tuple(
        reader.u32("code constant index") for _ in range(reader.u32("code constant count"))
    )
    constants = tuple(
        _read_constant(reader) for _ in range(reader.u32("code constant count"))
    )
    spans = tuple(_read_source_span(reader) for _ in range(reader.u32("code span count")))
    span_table = tuple(reader.u32("code span index") for _ in range(reader.u32("code span table count")))
    exception_table = tuple(
        _read_exception_entry(reader)
        for _ in range(reader.u32("code exception count"))
    )
    local_names = tuple(
        reader.string("code local name")
        for _ in range(reader.u32("code local name count"))
    )
    parameter_names = tuple(
        reader.string("code parameter name")
        for _ in range(reader.u32("code parameter name count"))
    )
    return_spec = reader.i32("code return spec")
    flags = reader.u32("code flags")
    trait_name = _read_optional_string(reader, "code trait name")
    operator_trait = _read_optional_string(reader, "code operator trait")
    fallback_ast = _read_json(reader, "code fallback ast")
    return CodeObject(
        name=name,
        qualname=qualname,
        source_file=source_file,
        parameter_count=parameter_count,
        local_count=local_count,
        capture_count=capture_count,
        max_stack=max_stack,
        max_frame_depth=max_frame_depth,
        bytecode=bytecode,
        constant_indices=constant_indices,
        constants=constants,
        spans=spans,
        span_table=span_table,
        exception_table=exception_table,
        local_names=local_names,
        parameter_names=parameter_names,
        return_spec=return_spec,
        flags=flags,
        trait_name=trait_name,
        operator_trait=operator_trait,
        fallback_ast=fallback_ast,
    )


def _write_module(out: bytearray, module: ModuleInfo) -> None:
    _string(out, module.name)
    _string(out, module.path)
    _u32(out, module.code_index)
    _u32(out, len(module.imports))
    for item in module.imports:
        _json(out, item)
    _u32(out, len(module.exports))
    for name, target in module.exports:
        _string(out, name)
        _string(out, target)


def _read_module(reader: _Reader) -> ModuleInfo:
    name = reader.string("module name")
    path = reader.string("module path")
    code_index = reader.u32("module code index")
    imports = tuple(
        _read_json(reader, "module import")
        for _ in range(reader.u32("module import count"))
    )
    exports = tuple(
        (reader.string("module export name"), reader.string("module export target"))
        for _ in range(reader.u32("module export count"))
    )
    return ModuleInfo(name, path, code_index, imports, exports)


def _write_type(out: bytearray, info: TypeInfo) -> None:
    _string(out, info.name)
    _string(out, info.kind)
    _u32(out, len(info.type_parameters))
    for name in info.type_parameters:
        _string(out, name)
    _u32(out, len(info.properties))
    for is_private, name, index, type_name in info.properties:
        _u8(out, 1 if is_private else 0)
        _string(out, name)
        _u32(out, index)
        _optional_string(out, type_name)
    _u32(out, len(info.methods))
    for is_private, name, index, type_name, is_static in info.methods:
        _u8(out, 1 if is_private else 0)
        _string(out, name)
        _u32(out, index if index >= 0 else 0xFFFFFFFF)
        _optional_string(out, type_name)
        _u8(out, 1 if is_static else 0)
    _u32(out, len(info.variants))
    for name in info.variants:
        _string(out, name)


def _read_type(reader: _Reader) -> TypeInfo:
    name = reader.string("type name")
    kind = reader.string("type kind")
    type_parameters = tuple(
        reader.string("type parameter")
        for _ in range(reader.u32("type parameter count"))
    )
    properties = tuple(
        (
            bool(reader.u8("property private")),
            reader.string("property name"),
            reader.u32("property index"),
            _read_optional_string(reader, "property type name"),
        )
        for _ in range(reader.u32("property count"))
    )
    methods = tuple(
        (
            bool(reader.u8("method private")),
            reader.string("method name"),
            _signed_index(reader.u32("method index")),
            _read_optional_string(reader, "method type name"),
            bool(reader.u8("method static")),
        )
        for _ in range(reader.u32("method count"))
    )
    variants = tuple(
        reader.string("type variant") for _ in range(reader.u32("type variant count"))
    )
    return TypeInfo(name, kind, type_parameters, properties, methods, variants)


def _write_trait(out: bytearray, info: TraitInfo) -> None:
    _string(out, info.name)
    _u32(out, len(info.properties))
    for name in info.properties:
        _string(out, name)
    _u32(out, len(info.methods))
    for name, index, is_static in info.methods:
        _string(out, name)
        _u32(out, index if index >= 0 else 0xFFFFFFFF)
        _u8(out, 1 if is_static else 0)


def _read_trait(reader: _Reader) -> TraitInfo:
    name = reader.string("trait name")
    properties = tuple(
        reader.string("trait property") for _ in range(reader.u32("trait property count"))
    )
    methods = tuple(
        (
            reader.string("trait method name"),
            _signed_index(reader.u32("trait method index")),
            bool(reader.u8("trait method static")),
        )
        for _ in range(reader.u32("trait method count"))
    )
    return TraitInfo(name, properties, methods)


def _write_function(out: bytearray, info: FunctionInfo) -> None:
    _string(out, info.name)
    _u32(out, info.code_index)
    _json(out, info.args)
    _u32(out, info.min_argc)
    _json(out, info.return_node)
    _json(out, info.flags)
    _json(out, info.body)


def _read_function(reader: _Reader) -> FunctionInfo:
    name = reader.string("function name")
    code_index = reader.u32("function code index")
    args = _read_json(reader, "function args")
    min_argc = reader.u32("function min argc")
    return_node = _read_json(reader, "function return node")
    flags = _read_json(reader, "function flags")
    body = _read_json(reader, "function body")
    return FunctionInfo(name, code_index, args, min_argc, return_node, flags, body)


def _write_call_site(out: bytearray, site: CallSite) -> None:
    _string(out, site.dispatch)
    _string(out, site.name)
    _optional_string(out, site.module)
    _optional_string(out, site.type_name)
    _optional_string(out, site.trait_name)
    _optional_string(out, site.operator_trait)
    _optional_string(out, site.native_type)
    _u32(out, site.positional_count)
    _u32(out, len(site.argument_kinds))
    for kind in site.argument_kinds:
        _string(out, kind)
    _u32(out, len(site.argument_names))
    for name in site.argument_names:
        _string(out, name)
    _u32(out, site.type_argument_count)
    _i32(out, site.return_spec)
    _u8(out, 1 if site.is_async else 0)
    _json(out, site.callee_ast)
    _json(out, site.method_ast)


def _read_call_site(reader: _Reader) -> CallSite:
    dispatch = reader.string("call dispatch")
    name = reader.string("call name")
    module = _read_optional_string(reader, "call module")
    type_name = _read_optional_string(reader, "call type name")
    trait_name = _read_optional_string(reader, "call trait name")
    operator_trait = _read_optional_string(reader, "call operator trait")
    native_type = _read_optional_string(reader, "call native type")
    positional_count = reader.u32("call positional count")
    argument_kinds = tuple(
        reader.string("call argument kind")
        for _ in range(reader.u32("call argument kind count"))
    )
    argument_names = tuple(
        reader.string("call argument name")
        for _ in range(reader.u32("call argument name count"))
    )
    type_argument_count = reader.u32("call type argument count")
    return_spec = reader.i32("call return spec")
    is_async = bool(reader.u8("call async"))
    callee_ast = _read_json(reader, "call callee ast")
    method_ast = _read_json(reader, "call method ast")
    return CallSite(
        dispatch=dispatch,
        name=name,
        module=module,
        type_name=type_name,
        trait_name=trait_name,
        operator_trait=operator_trait,
        native_type=native_type,
        positional_count=positional_count,
        argument_kinds=argument_kinds,
        argument_names=argument_names,
        type_argument_count=type_argument_count,
        return_spec=return_spec,
        is_async=is_async,
        callee_ast=callee_ast,
        method_ast=method_ast,
    )


def _write_pattern(out: bytearray, pattern: PatternDescriptor) -> None:
    _string(out, pattern.kind)
    _json(out, pattern.literal)
    _u32(out, len(pattern.bindings))
    for name, slot in pattern.bindings:
        _string(out, name)
        _u32(out, slot)
    _u32(out, len(pattern.nested))
    for child in pattern.nested:
        _write_pattern(out, child)
    _optional_string(out, pattern.type_name)
    _u32(out, len(pattern.fields))
    for name, child in pattern.fields:
        _string(out, name)
        _write_pattern(out, child)
    _i32(out, pattern.rest_slot)
    _json(out, pattern.start_ast)
    _json(out, pattern.end_ast)


def _read_pattern(reader: _Reader) -> PatternDescriptor:
    kind = reader.string("pattern kind")
    literal = _read_json(reader, "pattern literal")
    bindings = tuple(
        (reader.string("pattern binding name"), reader.u32("pattern binding slot"))
        for _ in range(reader.u32("pattern binding count"))
    )
    nested = tuple(
        _read_pattern(reader) for _ in range(reader.u32("pattern nested count"))
    )
    type_name = _read_optional_string(reader, "pattern type name")
    fields = tuple(
        (reader.string("pattern field name"), _read_pattern(reader))
        for _ in range(reader.u32("pattern field count"))
    )
    rest_slot = reader.i32("pattern rest slot")
    start_ast = _read_json(reader, "pattern start ast")
    end_ast = _read_json(reader, "pattern end ast")
    return PatternDescriptor(kind, literal, bindings, nested, type_name, fields, rest_slot, start_ast, end_ast)


# ---------------------------------------------------------------------------
# Table writers.


def _encode_meta(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, image.entry_module)
    _u32(out, image.entry_code)
    return bytes(out)


def _encode_modules(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.modules))
    for module in image.modules:
        _write_module(out, module)
    return bytes(out)


def _encode_types(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.types))
    for info in image.types:
        _write_type(out, info)
    return bytes(out)


def _encode_traits(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.traits))
    for info in image.traits:
        _write_trait(out, info)
    return bytes(out)


def _encode_functions(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.functions))
    for info in image.functions:
        _write_function(out, info)
    return bytes(out)


def _encode_constants(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.constants))
    for constant in image.constants:
        _write_constant(out, constant)
    return bytes(out)


def _encode_call_sites(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.call_sites))
    for site in image.call_sites:
        _write_call_site(out, site)
    return bytes(out)


def _encode_patterns(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.patterns))
    for pattern in image.patterns:
        _write_pattern(out, pattern)
    return bytes(out)


def _encode_type_specs(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.type_specs))
    for spec in image.type_specs:
        _json(out, spec)
    return bytes(out)


def _encode_sources(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.sources))
    for source in image.sources:
        _string(out, source)
    return bytes(out)


def _encode_global_names(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.global_names))
    for name in image.global_names:
        _string(out, name)
    return bytes(out)


def _encode_strings(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.strings))
    for text in image.strings:
        _string(out, text)
    return bytes(out)


def _encode_debug_lines(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.debug_lines))
    for line in image.debug_lines:
        _json(out, line)
    return bytes(out)


def _encode_codes(image: ProgramImage) -> bytes:
    out = bytearray()
    _u32(out, len(image.codes))
    for code in image.codes:
        _write_code(out, code)
    return bytes(out)


# ---------------------------------------------------------------------------
# Table readers.


def _decode_meta(reader: _Reader) -> tuple[int, int]:
    return reader.u32("entry module"), reader.u32("entry code")


def _decode_modules(reader: _Reader) -> list[ModuleInfo]:
    return [_read_module(reader) for _ in range(reader.u32("module count"))]


def _decode_types(reader: _Reader) -> list[TypeInfo]:
    return [_read_type(reader) for _ in range(reader.u32("type count"))]


def _decode_traits(reader: _Reader) -> list[TraitInfo]:
    return [_read_trait(reader) for _ in range(reader.u32("trait count"))]


def _decode_functions(reader: _Reader) -> list[FunctionInfo]:
    return [_read_function(reader) for _ in range(reader.u32("function count"))]


def _decode_constants(reader: _Reader) -> list[Constant]:
    return [_read_constant(reader) for _ in range(reader.u32("constant count"))]


def _decode_call_sites(reader: _Reader) -> list[CallSite]:
    return [_read_call_site(reader) for _ in range(reader.u32("call site count"))]


def _decode_patterns(reader: _Reader) -> list[PatternDescriptor]:
    return [_read_pattern(reader) for _ in range(reader.u32("pattern count"))]


def _decode_type_specs(reader: _Reader) -> list[Any]:
    return [_read_json(reader, "type spec") for _ in range(reader.u32("type spec count"))]


def _decode_sources(reader: _Reader) -> list[str]:
    return [reader.string("source") for _ in range(reader.u32("source count"))]


def _decode_global_names(reader: _Reader) -> list[str]:
    return [reader.string("global name") for _ in range(reader.u32("global name count"))]


def _decode_strings(reader: _Reader) -> list[str]:
    return [reader.string("string") for _ in range(reader.u32("string count"))]


def _decode_debug_lines(reader: _Reader) -> list[Any]:
    return [_read_json(reader, "debug line") for _ in range(reader.u32("debug line count"))]


def _decode_codes(reader: _Reader) -> list[CodeObject]:
    return [_read_code(reader) for _ in range(reader.u32("code count"))]


def _finish(reader: _Reader, table: str) -> None:
    if reader.remaining() != 0:
        raise ValueError(f"trailing bytes in image table {table}: {reader.remaining()}")


# ---------------------------------------------------------------------------
# Container.


def _write_image(image: ProgramImage) -> bytes:
    if image.format_version != FORMAT_VERSION:
        raise ValueError(
            f"unsupported format version {image.format_version}, expected {FORMAT_VERSION}"
        )
    if image.flags < 0 or image.flags > 0xFFFF:
        raise ValueError(f"image flags out of range: {image.flags}")
    tables = [
        _encode_meta(image),
        _encode_modules(image),
        _encode_types(image),
        _encode_traits(image),
        _encode_functions(image),
        _encode_constants(image),
        _encode_call_sites(image),
        _encode_patterns(image),
        _encode_type_specs(image),
        _encode_sources(image),
        _encode_global_names(image),
        _encode_strings(image),
        _encode_debug_lines(image),
        _encode_codes(image),
    ]
    language = image.language_version.encode("utf-8")
    if len(language) > 0xFFFF:
        raise ValueError("language version string is too long")
    out = bytearray()
    out += FORMAT_MAGIC
    out += struct.pack("<H", FORMAT_VERSION)
    out += struct.pack("<H", image.flags)
    out += struct.pack("<H", len(language))
    out += language
    _u32(out, len(tables))
    for table in tables:
        _u32(out, len(table))
        out += table
    crc = zlib.crc32(bytes(out)) & 0xFFFFFFFF
    _u32(out, crc)
    return bytes(out)


def _read_image(data: bytes) -> ProgramImage:
    reader = _Reader(data)
    magic = reader.take(4, "magic")
    if magic != FORMAT_MAGIC:
        raise ValueError(f"invalid image magic: {magic!r}")
    version = reader.u16("format version")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported image format version: {version}")
    flags = reader.u16("image flags")
    language_length = reader.u16("language version length")
    language_raw = reader.take(language_length, "language version")
    try:
        language = language_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid UTF-8 in language version: {exc}") from exc
    table_count = reader.u32("table count")
    if table_count != len(TABLE_NAMES):
        raise ValueError(
            f"image has {table_count} tables but {len(TABLE_NAMES)} are expected"
        )
    tables: list[bytes] = []
    for name in TABLE_NAMES:
        length = reader.u32(f"{name} table length")
        tables.append(reader.take(length, f"{name} table"))
    if reader.remaining() != 4:
        raise ValueError(
            f"image has {reader.remaining()} trailing bytes before the checksum"
        )
    expected_crc = reader.u32("checksum")
    actual_crc = zlib.crc32(data[:-4]) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        raise ValueError(
            f"image checksum mismatch: expected 0x{expected_crc:08x} "
            f"but computed 0x{actual_crc:08x}"
        )

    readers = [_Reader(table) for table in tables]
    entry_module, entry_code = _decode_meta(readers[0])
    _finish(readers[0], "meta")
    modules = _decode_modules(readers[1])
    _finish(readers[1], "modules")
    types = _decode_types(readers[2])
    _finish(readers[2], "types")
    traits = _decode_traits(readers[3])
    _finish(readers[3], "traits")
    functions = _decode_functions(readers[4])
    _finish(readers[4], "functions")
    constants = _decode_constants(readers[5])
    _finish(readers[5], "constants")
    call_sites = _decode_call_sites(readers[6])
    _finish(readers[6], "call_sites")
    patterns = _decode_patterns(readers[7])
    _finish(readers[7], "patterns")
    type_specs = _decode_type_specs(readers[8])
    _finish(readers[8], "type_specs")
    sources = _decode_sources(readers[9])
    _finish(readers[9], "sources")
    global_names = _decode_global_names(readers[10])
    _finish(readers[10], "global_names")
    strings = _decode_strings(readers[11])
    _finish(readers[11], "strings")
    debug_lines = _decode_debug_lines(readers[12])
    _finish(readers[12], "debug_lines")
    codes = _decode_codes(readers[13])
    _finish(readers[13], "codes")

    return ProgramImage(
        format_version=version,
        language_version=language,
        flags=flags,
        entry_module=entry_module,
        entry_code=entry_code,
        modules=modules,
        types=types,
        traits=traits,
        functions=functions,
        constants=constants,
        call_sites=call_sites,
        patterns=patterns,
        type_specs=type_specs,
        sources=sources,
        global_names=global_names,
        strings=strings,
        debug_lines=debug_lines,
        codes=codes,
    )


def write_image(image: ProgramImage, path: str | Path) -> None:
    """Write `image` to `path` as a deterministic `PWB1` container."""
    Path(path).write_bytes(image.to_bytes())


def read_image(path: str | Path) -> ProgramImage:
    """Read and validate a `PWB1` container from `path`."""
    return ProgramImage.from_bytes(Path(path).read_bytes())
