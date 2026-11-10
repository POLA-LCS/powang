"""Opcode registry and operand codec for the Phase 4B bytecode VM.

Every instruction is declared once here. The compiler, verifier, interpreter,
disassembler and documentation tables all read this registry, so an opcode is
never introduced in two places. Operand widths and stack effects are binding
and follow `docs/phase-4b-bytecode-vm/implementation/00-contracts.md`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Sequence


WIDTHS: dict[str, int] = {
    "u8": 1,
    "u16": 2,
    "u32": 4,
    "i32": 4,
    "i64": 8,
    "f64": 8,
}

_STRUCT_FORMATS: dict[str, str] = {
    "u8": "<B",
    "u16": "<H",
    "u32": "<I",
    "i32": "<i",
    "i64": "<q",
    "f64": "<d",
}

_INT_LIMITS: dict[str, tuple[int, int]] = {
    "u8": (0, 0xFF),
    "u16": (0, 0xFFFF),
    "u32": (0, 0xFFFFFFFF),
    "i32": (-0x80000000, 0x7FFFFFFF),
    "i64": (-0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
}


@dataclass(frozen=True)
class Operand:
    """One fixed width operand of an instruction."""

    name: str
    width: str
    kind: str = "value"


@dataclass(frozen=True)
class OpcodeSpec:
    """The single declaration of one opcode."""

    name: str
    opcode: int
    operands: tuple[Operand, ...]
    stack_in: int
    stack_out: int
    verifier: str
    handler: str
    doc: str = ""

    @property
    def size(self) -> int:
        """Encoded size in bytes, including the opcode byte."""
        return 1 + sum(WIDTHS[operand.width] for operand in self.operands)


def _op(name: str, width: str, kind: str = "value") -> Operand:
    return Operand(name, width, kind)


def _specs() -> list[tuple[str, tuple[Operand, ...], int, int, str]]:
    """Return the ordered opcode table.

    The order is fixed. New opcodes may only be appended.
    """
    return [
        # Core and stack.
        ("NOP", (), 0, 0, "stack"),
        ("POP", (), 1, 0, "stack"),
        ("DUP", (), 1, 2, "stack"),
        ("DUP2", (), 2, 4, "stack"),
        ("SWAP", (), 2, 2, "stack"),
        ("ROT3", (), 3, 3, "stack"),
        ("ROT", (_op("count", "u16"),), -1, -1, "stack"),
        # Literals.
        ("LOAD_NOVA", (), 0, 1, "literal"),
        ("LOAD_UNDEF", (), 0, 1, "literal"),
        ("LOAD_TRUE", (), 0, 1, "literal"),
        ("LOAD_FALSE", (), 0, 1, "literal"),
        ("LOAD_INT", (_op("value", "i64"),), 0, 1, "literal"),
        ("LOAD_BIGINT", (_op("const", "u32", "const"),), 0, 1, "literal"),
        ("LOAD_NUM", (_op("value", "f64"),), 0, 1, "literal"),
        ("LOAD_CHAR", (_op("value", "u32"),), 0, 1, "literal"),
        ("LOAD_STR", (_op("const", "u32", "const"),), 0, 1, "literal"),
        ("LOAD_CONST", (_op("const", "u32", "const"),), 0, 1, "literal"),
        # Declarations.
        (
            "DECLARE_LOCAL",
            (_op("slot", "u16", "slot"), _op("spec", "u32", "spec"), _op("flags", "u8", "flags")),
            0,
            1,
            "declare",
        ),
        (
            "DECLARE_GLOBAL",
            (_op("name", "u32", "name"), _op("spec", "u32", "spec"), _op("flags", "u8", "flags")),
            0,
            1,
            "declare",
        ),
        (
            "DECLARE_TYPED",
            (_op("slot", "u16", "slot"), _op("spec", "u32", "spec")),
            1,
            1,
            "declare",
        ),
        ("DECLARE_INFER", (_op("slot", "u16", "slot"),), 1, 1, "declare"),
        (
            "DECLARE_TYPED_GLOBAL",
            (_op("name", "u32", "name"), _op("spec", "u32", "spec")),
            1,
            1,
            "declare",
        ),
        ("DECLARE_INFER_GLOBAL", (_op("name", "u32", "name"),), 1, 1, "declare"),
        (
            "DECLARE_UNDEFINED_GLOBAL",
            (_op("name", "u32", "name"), _op("spec", "u32", "spec"), _op("flags", "u8", "flags")),
            0,
            1,
            "declare",
        ),
        (
            "DESTRUCTURE",
            (_op("descriptor", "u32", "const"), _op("source_slot", "u16", "slot")),
            0,
            1,
            "declare",
        ),
        ("DECLARE_FUNCTION", (_op("function", "u32"),), 0, 1, "declare"),
        ("DECLARE_TYPE", (_op("type", "u32", "type"),), 0, 1, "declare"),
        ("DECLARE_TRAIT", (_op("trait", "u32", "trait"),), 0, 1, "declare"),
        ("DECLARE_EXTERN", (_op("extern", "u32"),), 0, 0, "declare"),
        # Variables and slots.
        ("LOAD_LOCAL", (_op("slot", "u16", "slot"),), 0, 1, "variable"),
        ("STORE_LOCAL", (_op("slot", "u16", "slot"),), 1, 0, "variable"),
        ("LOAD_GLOBAL", (_op("name", "u32", "name"),), 0, 1, "variable"),
        ("STORE_GLOBAL", (_op("name", "u32", "name"),), 1, 0, "variable"),
        ("LOAD_NAME", (_op("name", "u32", "name"),), 0, 1, "variable"),
        ("STORE_NAME", (_op("name", "u32", "name"),), 1, 0, "variable"),
        ("LOAD_CAPTURE", (_op("index", "u16"),), 0, 1, "variable"),
        ("MAKE_CAPTURE", (_op("slot", "u16", "slot"),), 0, 0, "variable"),
        ("LOAD_THIS", (), 0, 1, "variable"),
        ("COPY", (), 1, 1, "variable"),
        ("CAST_ASSIGN", (_op("spec", "u32", "spec"),), 1, 1, "variable"),
        ("CAST_RETURN", (_op("spec", "u32", "spec"),), 1, 1, "variable"),
        ("BOX_ANY", (_op("spec", "u32", "spec"),), 1, 1, "variable"),
        ("UNBOX_ANY", (), 1, 1, "variable"),
        # Containers.
        ("MAKE_ARRAY", (_op("count", "u16"),), -1, 1, "container"),
        (
            "MAKE_ARRAY_TYPED",
            (_op("spec", "u32", "spec"), _op("count", "u16")),
            -1,
            1,
            "container",
        ),
        ("MAKE_TUPLE", (_op("count", "u16"),), -1, 1, "container"),
        (
            "MAKE_TUPLE_TYPED",
            (_op("spec", "u32", "spec"), _op("count", "u16")),
            -1,
            1,
            "container",
        ),
        ("MAKE_MAP", (_op("count", "u16"),), -1, 1, "container"),
        (
            "MAKE_MAP_TYPED",
            (_op("spec", "u32", "spec"), _op("count", "u16")),
            -1,
            1,
            "container",
        ),
        ("MAKE_SET", (_op("count", "u16"),), -1, 1, "container"),
        (
            "MAKE_SET_TYPED",
            (_op("spec", "u32", "spec"), _op("count", "u16")),
            -1,
            1,
            "container",
        ),
        ("MAKE_EMPTY_MAP", (), 0, 1, "container"),
        ("MAKE_EMPTY_SET", (), 0, 1, "container"),
        ("INDEX_GET", (), 2, 1, "container"),
        ("INDEX_SET", (), 3, 1, "container"),
        ("SLICE", (), 3, 1, "container"),
        ("SIZE", (), 1, 1, "container"),
        ("ITER_NEW", (), 1, 1, "container"),
        ("ITER_NEXT", (_op("target", "i32", "target"),), 1, 1, "container"),
        # Arithmetic, conversion and comparison.
        ("ADD", (), 2, 1, "arithmetic"),
        ("SUB", (), 2, 1, "arithmetic"),
        ("MUL", (), 2, 1, "arithmetic"),
        ("DIV", (), 2, 1, "arithmetic"),
        ("MOD", (), 2, 1, "arithmetic"),
        ("NEG", (), 1, 1, "arithmetic"),
        ("NOT", (), 1, 1, "arithmetic"),
        ("EQ", (), 2, 1, "arithmetic"),
        ("NEQ", (), 2, 1, "arithmetic"),
        ("LT", (), 2, 1, "arithmetic"),
        ("LE", (), 2, 1, "arithmetic"),
        ("GT", (), 2, 1, "arithmetic"),
        ("GE", (), 2, 1, "arithmetic"),
        ("EQ_TYPED", (), 2, 1, "arithmetic"),
        ("NEQ_TYPED", (), 2, 1, "arithmetic"),
        ("LT_TYPED", (), 2, 1, "arithmetic"),
        ("LE_TYPED", (), 2, 1, "arithmetic"),
        ("GT_TYPED", (), 2, 1, "arithmetic"),
        ("GE_TYPED", (), 2, 1, "arithmetic"),
        ("CONCAT_STR", (_op("count", "u16"),), -1, 1, "arithmetic"),
        ("TO_STRING", (), 1, 1, "arithmetic"),
        ("TO_BOOL", (), 1, 1, "arithmetic"),
        ("REVERSE", (), 1, 1, "arithmetic"),
        ("CAST", (_op("spec", "u32", "spec"),), 1, 1, "arithmetic"),
        ("TYPE_CHECK", (_op("spec", "u32", "spec"),), 1, 1, "arithmetic"),
        ("TYPE_CHECK_NOT", (_op("spec", "u32", "spec"),), 1, 1, "arithmetic"),
        ("TYPE_CHECK_VALUE", (), 2, 1, "arithmetic"),
        ("IS_NOVA", (), 1, 1, "arithmetic"),
        ("IS_DEFINED", (), 1, 1, "arithmetic"),
        ("IS_WEAK", (), 1, 1, "arithmetic"),
        # Control flow.
        ("JUMP", (_op("target", "i32", "target"),), 0, 0, "control"),
        ("JUMP_IF_FALSE", (_op("target", "i32", "target"),), 1, 0, "control"),
        ("JUMP_IF_TRUE", (_op("target", "i32", "target"),), 1, 0, "control"),
        ("JUMP_IF_FALSE_KEEP", (_op("target", "i32", "target"),), 1, 1, "control"),
        ("JUMP_IF_TRUE_KEEP", (_op("target", "i32", "target"),), 1, 1, "control"),
        ("JUMP_IF_NOVA", (_op("target", "i32", "target"),), 1, 0, "control"),
        ("JUMP_IF_NOT_NOVA", (_op("target", "i32", "target"),), 1, 0, "control"),
        (
            "MATCH",
            (_op("pattern", "u32", "pattern"), _op("target", "i32", "target")),
            1,
            0,
            "control",
        ),
        ("RETURN", (), 1, 0, "control"),
        ("CHECK_CANCEL", (), 0, 0, "control"),
        # Calls.
        ("CALL", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_VALUE", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_METHOD", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_STATIC", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_MODULE", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_NATIVE", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_BUILTIN", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_TRAIT", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_OPERATOR", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_EXTERN", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_ASYNC", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("CALL_ASYNC_METHOD", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("SPAWN", (_op("call", "u32", "call"),), -1, 1, "call"),
        ("AWAIT", (), 1, 1, "call"),
        # Objects, enums and fields.
        (
            "CONSTRUCT",
            (_op("type", "u32", "type"), _op("call", "u32", "call")),
            -1,
            1,
            "object",
        ),
        ("NEW_ENUM", (_op("enum", "u32", "type"), _op("variant", "u16")), 0, 1, "object"),
        ("LOAD_FIELD", (_op("field", "u32", "field"),), 1, 1, "object"),
        ("STORE_FIELD", (_op("field", "u32", "field"),), 2, 0, "object"),
        ("LOAD_MEMBER", (_op("name", "u32", "name"),), 1, 1, "object"),
        ("STORE_MEMBER", (_op("name", "u32", "name"),), 2, 1, "object"),
        ("LOAD_MEMBER_SAFE", (_op("name", "u32", "name"),), 1, 1, "object"),
        (
            "LOAD_ENUM_MEMBER",
            (_op("enum", "u32", "type"), _op("variant", "u16")),
            0,
            1,
            "object",
        ),
        ("SET_LOCKS", (_op("flags", "u8", "flags"),), 1, 0, "object"),
        # Traits.
        ("CHECK_TRAIT", (_op("trait", "u32", "trait"),), 1, 1, "trait"),
        ("TRAIT_CAST", (_op("trait", "u32", "trait"),), 1, 1, "trait"),
        # Errors.
        ("MAKE_ERROR", (_op("spec", "u32", "spec"),), -1, 1, "error"),
        ("ERROR_PROPERTY", (_op("property", "u8"),), 1, 1, "error"),
        ("THROW", (), 1, 0, "error"),
        ("PROPAGATE", (), 1, 1, "error"),
        ("TRY_BEGIN", (_op("catch", "i32", "target"), _op("finally", "i32", "target")), 0, 0, "error"),
        ("TRY_END", (), 0, 0, "error"),
        ("FINALLY_END", (), 0, 0, "error"),
        ("RETHROW", (), 1, 0, "error"),
        # References.
        ("REF_LOCAL", (_op("slot", "u16", "slot"),), 0, 1, "reference"),
        ("REF_GLOBAL", (_op("name", "u32", "name"),), 0, 1, "reference"),
        ("REF_FIELD", (_op("field", "u32", "field"),), 1, 1, "reference"),
        ("REF_INDEX", (), 2, 1, "reference"),
        ("LOAD_REF", (), 1, 1, "reference"),
        ("STORE_REF", (), 2, 0, "reference"),
        # Modules and project.
        (
            "IMPORT",
            (_op("module", "u32", "module"), _op("slot", "u16", "slot")),
            0,
            0,
            "module",
        ),
        ("IMPORT_WILDCARD", (_op("module", "u32", "module"),), 0, 0, "module"),
        (
            "LOAD_MODULE_MEMBER",
            (_op("module", "u32", "module"), _op("export", "u32", "export")),
            0,
            1,
            "module",
        ),
        ("LOAD_PROJECT", (), 0, 1, "module"),
        ("EXPORT", (_op("name", "u32", "name"),), 1, 0, "module"),
        # Debug and host.
        ("TRACE_EVENT", (_op("event", "u16", "event"),), 0, 0, "debug"),
        ("HOST_CALL", (_op("host", "u32", "host"),), -1, 1, "debug"),
        ("ASSIGN_LOCAL", (_op("slot", "u16", "slot"),), 1, 0, "slot"),
        ("ASSIGN_NAME", (_op("name", "u32", "name"),), 1, 0, "slot"),
        ("MAKE_FUNCTION", (_op("function", "u32", "value"),), 0, 1, "function"),
        ("MAKE_SPREAD", (), 1, 1, "stack"),
        ("LOAD_RAW", (_op("slot", "u16", "slot"),), 0, 1, "slot"),
        ("STORE_RAW", (_op("slot", "u16", "slot"),), 1, 0, "slot"),
        ("ADD_TYPED", (), 2, 1, "arithmetic"),
        ("SUB_TYPED", (), 2, 1, "arithmetic"),
        ("MUL_TYPED", (), 2, 1, "arithmetic"),
        ("DIV_TYPED", (), 2, 1, "arithmetic"),
        ("MOD_TYPED", (), 2, 1, "arithmetic"),
        ("SET_RETURN", (), 1, 0, "control"),
        ("SET_TRANSFER", (_op("kind", "u8", "value"), _op("target", "i32", "target")), 0, 0, "control"),
        ("JUMP_IF_TRANSFER", (_op("target", "i32", "target"),), 0, 0, "control"),
        ("APPLY_TRANSFER", (), 0, 0, "control"),
        ("ABANDON_FINALLY", (), 0, 0, "control"),
        ("LOAD_FREE", (_op("name", "u32", "name"),), 0, 1, "slot"),
        ("SCOPE_PUSH", (), 0, 0, "control"),
        ("SCOPE_POP", (), 0, 0, "control"),
    ]


OPCODES: tuple[OpcodeSpec, ...] = tuple(
    OpcodeSpec(
        name=name,
        opcode=index,
        operands=operands,
        stack_in=stack_in,
        stack_out=stack_out,
        verifier=verifier,
        handler=name.lower(),
    )
    for index, (name, operands, stack_in, stack_out, verifier) in enumerate(_specs())
)

BY_NAME: dict[str, OpcodeSpec] = {item.name: item for item in OPCODES}
BY_OPCODE: dict[int, OpcodeSpec] = {item.opcode: item for item in OPCODES}


def spec(name: str) -> OpcodeSpec:
    """Return the opcode declaration for `name`.

    Raises `KeyError` when the name is not registered.
    """
    return BY_NAME[name]


def encode_operands(opcode_spec: OpcodeSpec, values: Sequence[int | float]) -> bytes:
    """Encode the operands of one instruction without the opcode byte."""
    if len(values) != len(opcode_spec.operands):
        raise ValueError(
            f"{opcode_spec.name} expects {len(opcode_spec.operands)} operands "
            f"but {len(values)} were given"
        )
    parts: list[bytes] = []
    for operand, value in zip(opcode_spec.operands, values):
        width = operand.width
        if width == "f64":
            if not isinstance(value, (int, float)):
                raise ValueError(f"{opcode_spec.name}.{operand.name} must be a number")
            parts.append(struct.pack("<d", float(value)))
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{opcode_spec.name}.{operand.name} must be an integer")
        low, high = _INT_LIMITS[width]
        if not low <= value <= high:
            raise ValueError(
                f"{opcode_spec.name}.{operand.name}={value} is out of range for {width}"
            )
        parts.append(struct.pack(_STRUCT_FORMATS[width], value))
    return b"".join(parts)


def decode_operands(
    opcode_spec: OpcodeSpec, data: bytes, offset: int
) -> tuple[dict[str, int | float], int]:
    """Decode operands at `offset` and return them with the next offset."""
    values: dict[str, int | float] = {}
    position = offset
    for operand in opcode_spec.operands:
        width = WIDTHS[operand.width]
        if position + width > len(data):
            raise ValueError(
                f"truncated instruction {opcode_spec.name} at offset {offset}: "
                f"missing {operand.name}"
            )
        value = struct.unpack_from(_STRUCT_FORMATS[operand.width], data, position)[0]
        values[operand.name] = value
        position += width
    return values, position


def decode_instruction(
    data: bytes, offset: int
) -> tuple[OpcodeSpec, dict[str, int | float], int]:
    """Decode one instruction at `offset` and return the next offset."""
    if offset < 0 or offset >= len(data):
        raise ValueError(f"truncated instruction: no opcode at offset {offset}")
    opcode = data[offset]
    opcode_spec = BY_OPCODE.get(opcode)
    if opcode_spec is None:
        raise ValueError(f"unknown opcode 0x{opcode:02x} at offset {offset}")
    operands, next_offset = decode_operands(opcode_spec, data, offset + 1)
    return opcode_spec, operands, next_offset
