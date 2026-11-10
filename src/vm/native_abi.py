"""Native VM ABI description generated from the opcode registry.

The native VM is a separate implementation target. This module exposes the
stable parts of the bytecode contract in forms a native project can consume:
a C header with the opcode, tag and operand kind enums, and a JSON contract
with the full opcode table. The values come from the same registry that drives
the Python compiler, verifier, interpreter and disassembler, so a native VM
cannot drift from the reference engine.
"""

from __future__ import annotations

import json
from typing import Any

from .image import FORMAT_VERSION, LANGUAGE_VERSION
from .opcodes import OPCODES, WIDTHS



_TAG_ORDER: tuple[str, ...] = (
    "nova", "undef", "bool", "int", "num", "char", "str", "arr", "tup",
    "map", "set", "fun", "obj", "module", "task", "error", "ref",
    "handle", "project", "any",
)


def tag_table() -> list[dict[str, Any]]:
    """Return the canonical value tags with stable numeric values."""
    return [
        {"name": name, "value": index}
        for index, name in enumerate(_TAG_ORDER)
    ]


def abi_document() -> dict[str, Any]:
    """Return the opcode, tag and operand contract as plain data."""
    return {
        "magic": "PWB1",
        "format_version": FORMAT_VERSION,
        "language_version": LANGUAGE_VERSION,
        "widths": dict(sorted(WIDTHS.items())),
        "tags": tag_table(),
        "opcodes": [
            {
                "name": opcode.name,
                "opcode": opcode.opcode,
                "operands": [
                    {
                        "name": operand.name,
                        "width": operand.width,
                        "kind": operand.kind,
                        "size": WIDTHS[operand.width],
                    }
                    for operand in opcode.operands
                ],
                "stack_in": opcode.stack_in,
                "stack_out": opcode.stack_out,
                "verifier": opcode.verifier,
                "handler": opcode.handler,
                "size": opcode.size,
            }
            for opcode in OPCODES
        ],
    }


def render_json_contract() -> str:
    """Return the native contract as deterministic JSON."""
    return json.dumps(
        abi_document(), ensure_ascii=False, indent=2, sort_keys=True,
    ) + "\n"


def _c_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_c_header() -> str:
    """Return a C header with the native ABI enums and opcode table."""
    lines: list[str] = [
        "/* Generated from src/vm/opcodes.py. Do not edit by hand. */",
        "#ifndef POWANG_BYTECODE_ABI_H",
        "#define POWANG_BYTECODE_ABI_H",
        "",
        "#include <stdint.h>",
        "",
        f"#define PWB_FORMAT_VERSION {FORMAT_VERSION}",
        f"#define PWB_LANGUAGE_VERSION {_c_string(LANGUAGE_VERSION)}",
        "",
        "typedef enum PwbOpcode {",
    ]
    for opcode in OPCODES:
        lines.append(f"    PWB_OP_{opcode.name} = {opcode.opcode},")
    lines.extend([
        "} PwbOpcode;",
        "",
        "typedef enum PwbTag {",
    ])
    for entry in tag_table():
        lines.append(f"    PWB_TAG_{entry['name'].upper()} = {entry['value']},")
    lines.extend([
        "} PwbTag;",
        "",
        "typedef enum PwbOperandKind {",
        "    PWB_OPERAND_VALUE = 0,",
        "    PWB_OPERAND_SLOT = 1,",
        "    PWB_OPERAND_TARGET = 2,",
        "    PWB_OPERAND_CONST = 3,",
        "    PWB_OPERAND_SPEC = 4,",
        "    PWB_OPERAND_CALL = 5,",
        "    PWB_OPERAND_PATTERN = 6,",
        "    PWB_OPERAND_MODULE = 7,",
        "    PWB_OPERAND_TYPE = 8,",
        "    PWB_OPERAND_TRAIT = 9,",
        "    PWB_OPERAND_FIELD = 10,",
        "    PWB_OPERAND_NAME = 11,",
        "    PWB_OPERAND_EXPORT = 12,",
        "    PWB_OPERAND_HOST = 13,",
        "    PWB_OPERAND_EVENT = 14,",
        "    PWB_OPERAND_FLAGS = 15,",
        "} PwbOperandKind;",
        "",
        "typedef struct PwbOpcodeInfo {",
        "    uint8_t opcode;",
        "    int32_t stack_in;",
        "    int32_t stack_out;",
        "} PwbOpcodeInfo;",
        "",
        f"#define PWB_OPCODE_COUNT {len(OPCODES)}",
        "",
        "extern const PwbOpcodeInfo PWB_OPCODE_INFO[PWB_OPCODE_COUNT];",
        "",
        "#endif",
    ])
    return "\n".join(lines) + "\n"
