"""Build the deterministic PWBM metadata block for a program image.

The PWBM block is a compact cache of shapes that already exist in the Python
``ProgramImage``. It is never a second source of truth. The builder reads
``ProgramImage.functions``, ``ProgramImage.type_specs`` and ``ProgramImage.codes``
directly and never parses image bytes or AST text.

Binary layout, all integers little endian:

* magic ``PWBM``
* u16 version, currently 1
* u16 flags, currently 0
* u32 function count
* u32 type spec count
* 32 raw bytes of SHA-256 over ``image.to_bytes()``
* the type specs, in table order
* the functions, in table order

Strings are a u32 byte length followed by UTF-8 bytes.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any

from ...typespec import Kind, TypeSpec, from_ast_node
from ..image import ProgramImage


MAGIC = b"PWBM"
VERSION = 1
FLAGS = 0
ABSENT_INDEX = 0xFFFFFFFF

KIND_NAMED = 0
KIND_UNION = 1
KIND_FUNCTION = 2
KIND_PARAM = 3

_KIND_CODES = {
    Kind.NAMED: KIND_NAMED,
    Kind.UNION: KIND_UNION,
    Kind.FUNCTION: KIND_FUNCTION,
    Kind.PARAM: KIND_PARAM,
}

_FUNCTION_FLAG_ASYNC = 1 << 0
_FUNCTION_FLAG_VARIADIC = 1 << 1
_FUNCTION_FLAG_LAMBDA = 1 << 2
_FUNCTION_FLAG_MUTABLE_CAPTURE = 1 << 3
_FUNCTION_FLAG_INSTANCE_METHOD = 1 << 4
_FUNCTION_FLAG_STATIC = 1 << 5
_FUNCTION_FLAG_SIGNATURE_ONLY = 1 << 6
_FUNCTION_FLAG_TRAIT_MEMBER = 1 << 7

_PARAMETER_FLAG_REFERENCE = 1 << 0
_PARAMETER_FLAG_WEAK = 1 << 1
_PARAMETER_FLAG_VARIADIC = 1 << 2
_PARAMETER_FLAG_HAS_DEFAULT = 1 << 3

_TYPE_FLAG_WEAK = 1 << 0
_TYPE_FLAG_CONST = 1 << 1
_TYPE_FLAG_REFERENCE = 1 << 2
_TYPE_FLAG_ERROR_UNION = 1 << 3
_TYPE_FLAG_REST = 1 << 4


@dataclass(frozen=True)
class MetaTypeSpec:
    """One parsed PWBM type spec record."""

    kind: int
    name: str
    nominal: str
    flags: int
    args: tuple[int, ...]
    params: tuple[int, ...]
    returns: int


@dataclass(frozen=True)
class MetaParameter:
    """One parsed PWBM parameter record."""

    name: str
    type_index: int
    flags: int
    default_index: int


@dataclass(frozen=True)
class MetaFunction:
    """One parsed PWBM function record."""

    name: str
    code_index: int
    min_argc: int
    flags: int
    variadic_index: int
    parameters: tuple[MetaParameter, ...]
    type_parameters: tuple[str, ...]
    function_type: str
    lambda_name: str | None
    defaults: tuple[int, ...]


@dataclass(frozen=True)
class MetaBlock:
    """A fully parsed PWBM block."""

    version: int
    flags: int
    image_hash: bytes
    types: tuple[MetaTypeSpec, ...]
    functions: tuple[MetaFunction, ...]


def _u8(out: bytearray, value: int) -> None:
    out += struct.pack("<B", value & 0xFF)


def _u16(out: bytearray, value: int) -> None:
    if value < 0 or value > 0xFFFF:
        raise ValueError(f"value out of range for u16: {value}")
    out += struct.pack("<H", value)


def _u32(out: bytearray, value: int) -> None:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"value out of range for u32: {value}")
    out += struct.pack("<I", value)


def _i32(out: bytearray, value: int) -> None:
    if value < -0x80000000 or value > 0x7FFFFFFF:
        raise ValueError(f"value out of range for i32: {value}")
    out += struct.pack("<i", value)


def _string(out: bytearray, text: str) -> None:
    raw = text.encode("utf-8")
    _u32(out, len(raw))
    out += raw


def _spec_key(spec: TypeSpec) -> tuple[Any, ...]:
    """Return a deterministic structural key for one type spec."""
    return (
        spec.kind.value,
        spec.name,
        spec.nominal,
        spec.weak,
        spec.const,
        spec.reference,
        spec.error_union,
        spec.rest,
        tuple(_spec_key(argument) for argument in spec.args),
        tuple(_spec_key(parameter) for parameter in spec.params),
        _spec_key(spec.returns) if spec.returns is not None else None,
    )


class _TypeTable:
    """Deduplicating table preserving first seen order."""

    def __init__(self) -> None:
        self.entries: list[tuple[TypeSpec, list[int], list[int], int]] = []
        self._indices: dict[tuple[Any, ...], int] = {}

    def add(self, spec: TypeSpec) -> int:
        key = _spec_key(spec)
        existing = self._indices.get(key)
        if existing is not None:
            return existing
        argument_indices = [self.add(argument) for argument in spec.args]
        parameter_indices = [self.add(parameter) for parameter in spec.params]
        return_index = (
            self.add(spec.returns) if spec.returns is not None else ABSENT_INDEX
        )
        index = len(self.entries)
        self._indices[key] = index
        self.entries.append(
            (spec, argument_indices, parameter_indices, return_index)
        )
        return index


def _type_flags(spec: TypeSpec) -> int:
    flags = 0
    if spec.weak:
        flags |= _TYPE_FLAG_WEAK
    if spec.const:
        flags |= _TYPE_FLAG_CONST
    if spec.reference:
        flags |= _TYPE_FLAG_REFERENCE
    if spec.error_union:
        flags |= _TYPE_FLAG_ERROR_UNION
    if spec.rest:
        flags |= _TYPE_FLAG_REST
    return flags


def _function_flags(flags: dict[str, Any]) -> int:
    bits = 0
    if flags.get("is_async"):
        bits |= _FUNCTION_FLAG_ASYNC
    if flags.get("variadic"):
        bits |= _FUNCTION_FLAG_VARIADIC
    if flags.get("is_lambda"):
        bits |= _FUNCTION_FLAG_LAMBDA
    if flags.get("mutable_capture"):
        bits |= _FUNCTION_FLAG_MUTABLE_CAPTURE
    if flags.get("instance_method"):
        bits |= _FUNCTION_FLAG_INSTANCE_METHOD
    if flags.get("is_static"):
        bits |= _FUNCTION_FLAG_STATIC
    if flags.get("signature_only"):
        bits |= _FUNCTION_FLAG_SIGNATURE_ONLY
    if flags.get("trait_member"):
        bits |= _FUNCTION_FLAG_TRAIT_MEMBER
    return bits


def _parameter_defaults(info_flags: dict[str, Any]) -> list[int]:
    defaults: list[int] = []
    for value in info_flags.get("defaults") or []:
        defaults.append(-1 if value is None else int(value))
    return defaults


def _build_parameter(
    argument: Any,
    position: int,
    defaults: list[int],
    table: _TypeTable,
) -> tuple[str, int, int, int]:
    if not isinstance(argument, dict):
        raise ValueError(
            f"function parameter {position} is not a declaration node"
        )
    value = argument.get("value")
    if not isinstance(value, dict):
        raise ValueError(
            f"function parameter {position} has no declaration value"
        )
    identifier = value.get("identifier")
    if not isinstance(identifier, dict):
        raise ValueError(f"function parameter {position} has no identifier")
    name = identifier.get("value")
    if not isinstance(name, str):
        raise ValueError(f"function parameter {position} has no name")
    spec = from_ast_node(value.get("type"))
    type_index = table.add(spec)
    variadic = bool(value.get("variadic"))
    default_index = defaults[position] if position < len(defaults) else -1
    if default_index is None:
        default_index = -1
    default_index = int(default_index)
    flags = 0
    if spec.reference:
        flags |= _PARAMETER_FLAG_REFERENCE
    if spec.weak:
        flags |= _PARAMETER_FLAG_WEAK
    if variadic:
        flags |= _PARAMETER_FLAG_VARIADIC
    if default_index >= 0:
        flags |= _PARAMETER_FLAG_HAS_DEFAULT
    return name, type_index, flags, default_index


def _write_type_specs(out: bytearray, table: _TypeTable) -> None:
    for spec, argument_indices, parameter_indices, return_index in table.entries:
        _u8(out, _KIND_CODES[spec.kind])
        _string(out, spec.name)
        _string(out, spec.nominal)
        _u8(out, _type_flags(spec))
        _u32(out, len(argument_indices))
        for index in argument_indices:
            _u32(out, index)
        _u32(out, len(parameter_indices))
        for index in parameter_indices:
            _u32(out, index)
        _u32(out, return_index)


def _write_function(
    out: bytearray,
    info: Any,
    flags: dict[str, Any],
    defaults: list[int],
    parameters: list[tuple[str, int, int, int]],
) -> None:
    variadic_value = flags.get("variadic_index")
    variadic_index = -1 if variadic_value is None else int(variadic_value)
    type_parameters = [str(item) for item in (flags.get("type_parameters") or [])]
    function_type = flags.get("function_type") or ""
    if not isinstance(function_type, str):
        function_type = str(function_type)
    lambda_name = flags.get("lambda_name")
    if lambda_name is not None and not isinstance(lambda_name, str):
        lambda_name = str(lambda_name)

    _string(out, str(info.name))
    _u32(out, int(info.code_index))
    _u32(out, int(info.min_argc))
    _u32(out, _function_flags(flags))
    _i32(out, variadic_index)

    _u32(out, len(parameters))
    for name, type_index, parameter_flags, default_index in parameters:
        _string(out, name)
        _u32(out, type_index)
        _u8(out, parameter_flags)
        _i32(out, default_index)

    _u32(out, len(type_parameters))
    for name in type_parameters:
        _string(out, name)

    _string(out, function_type)

    if lambda_name is None:
        _u8(out, 0)
    else:
        _u8(out, 1)
        _string(out, lambda_name)

    _u32(out, len(defaults))
    for index in defaults:
        _i32(out, index)


def build_meta(image: ProgramImage) -> bytes:
    """Return the deterministic PWBM block for ``image``."""
    table = _TypeTable()
    for node in image.type_specs:
        table.add(from_ast_node(node))

    records: list[
        tuple[Any, dict[str, Any], list[int], list[tuple[str, int, int, int]]]
    ] = []
    for info in image.functions:
        flags = info.flags if isinstance(info.flags, dict) else {}
        defaults = _parameter_defaults(flags)
        arguments = list(info.args or [])
        parameters = [
            _build_parameter(argument, position, defaults, table)
            for position, argument in enumerate(arguments)
        ]
        records.append((info, flags, defaults, parameters))

    body = bytearray()
    _write_type_specs(body, table)

    functions = bytearray()
    for info, flags, defaults, parameters in records:
        _write_function(functions, info, flags, defaults, parameters)

    out = bytearray()
    out += MAGIC
    _u16(out, VERSION)
    _u16(out, FLAGS)
    _u32(out, len(image.functions))
    _u32(out, len(table.entries))
    out += hashlib.sha256(image.to_bytes()).digest()
    out += body
    out += functions
    return bytes(out)


class _MetaReader:
    """Bounds checked reader used by :func:`parse_meta`."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, count: int, what: str) -> bytes:
        if count < 0 or self.offset + count > len(self.data):
            raise ValueError(
                f"truncated PWBM metadata while reading {what} "
                f"at offset {self.offset}"
            )
        chunk = self.data[self.offset : self.offset + count]
        self.offset += count
        return chunk

    def u8(self, what: str) -> int:
        return struct.unpack("<B", self.take(1, what))[0]

    def u16(self, what: str) -> int:
        return struct.unpack("<H", self.take(2, what))[0]

    def u32(self, what: str) -> int:
        return struct.unpack("<I", self.take(4, what))[0]

    def i32(self, what: str) -> int:
        return struct.unpack("<i", self.take(4, what))[0]

    def string(self, what: str) -> str:
        length = self.u32(f"{what} length")
        raw = self.take(length, what)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"invalid UTF-8 in {what}: {error}") from error

    def remaining(self) -> int:
        return len(self.data) - self.offset


def parse_meta(data: bytes) -> MetaBlock:
    """Parse a PWBM block. This mirrors the C++ parser in ``meta.cpp``."""
    reader = _MetaReader(data)
    magic = reader.take(4, "magic")
    if magic != MAGIC:
        raise ValueError(f"invalid PWBM magic: {magic!r}")
    version = reader.u16("version")
    if version != VERSION:
        raise ValueError(f"unsupported PWBM version: {version}")
    flags = reader.u16("flags")
    function_count = reader.u32("function count")
    type_count = reader.u32("type spec count")
    image_hash = reader.take(32, "image hash")

    types: list[MetaTypeSpec] = []
    for index in range(type_count):
        kind = reader.u8(f"type spec {index} kind")
        if kind > KIND_PARAM:
            raise ValueError(f"unknown PWBM type spec kind: {kind}")
        name = reader.string(f"type spec {index} name")
        nominal = reader.string(f"type spec {index} nominal")
        type_flags = reader.u8(f"type spec {index} flags")
        argument_count = reader.u32(f"type spec {index} argument count")
        arguments = tuple(
            reader.u32(f"type spec {index} argument")
            for _ in range(argument_count)
        )
        parameter_count = reader.u32(f"type spec {index} parameter count")
        parameters = tuple(
            reader.u32(f"type spec {index} parameter")
            for _ in range(parameter_count)
        )
        returns = reader.u32(f"type spec {index} returns")
        types.append(MetaTypeSpec(
            kind=kind,
            name=name,
            nominal=nominal,
            flags=type_flags,
            args=arguments,
            params=parameters,
            returns=returns,
        ))

    functions: list[MetaFunction] = []
    for index in range(function_count):
        name = reader.string(f"function {index} name")
        code_index = reader.u32(f"function {index} code index")
        min_argc = reader.u32(f"function {index} min argc")
        function_flags = reader.u32(f"function {index} flags")
        variadic_index = reader.i32(f"function {index} variadic index")
        parameter_count = reader.u32(f"function {index} parameter count")
        parameters: list[MetaParameter] = []
        for position in range(parameter_count):
            parameter_name = reader.string(
                f"function {index} parameter {position} name"
            )
            type_index = reader.u32(
                f"function {index} parameter {position} type index"
            )
            parameter_flags = reader.u8(
                f"function {index} parameter {position} flags"
            )
            default_index = reader.i32(
                f"function {index} parameter {position} default index"
            )
            parameters.append(MetaParameter(
                name=parameter_name,
                type_index=type_index,
                flags=parameter_flags,
                default_index=default_index,
            ))
        type_parameter_count = reader.u32(
            f"function {index} type parameter count"
        )
        type_parameters = tuple(
            reader.string(f"function {index} type parameter")
            for _ in range(type_parameter_count)
        )
        function_type = reader.string(f"function {index} function type")
        has_lambda_name = reader.u8(f"function {index} lambda name presence")
        if has_lambda_name not in (0, 1):
            raise ValueError(
                f"invalid lambda name presence on function {index}: "
                f"{has_lambda_name}"
            )
        lambda_name = (
            reader.string(f"function {index} lambda name")
            if has_lambda_name
            else None
        )
        defaults_count = reader.u32(f"function {index} defaults count")
        defaults = tuple(
            reader.i32(f"function {index} default") for _ in range(defaults_count)
        )
        functions.append(MetaFunction(
            name=name,
            code_index=code_index,
            min_argc=min_argc,
            flags=function_flags,
            variadic_index=variadic_index,
            parameters=tuple(parameters),
            type_parameters=type_parameters,
            function_type=function_type,
            lambda_name=lambda_name,
            defaults=defaults,
        ))

    if reader.remaining() != 0:
        raise ValueError(
            f"trailing bytes in PWBM metadata: {reader.remaining()}"
        )
    return MetaBlock(
        version=version,
        flags=flags,
        image_hash=image_hash,
        types=tuple(types),
        functions=tuple(functions),
    )
