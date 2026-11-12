"""Generate the native C++ opcode table from the Python registry.

The generated header keeps the native decoder on the same opcode order,
operand widths and stack effects as `src/vm/opcodes.py`. Run it with
`python -m src.vm.native.gen_opcodes --write`. The `--check` mode exits 1 and
prints `stale` when the checked-in header does not match the registry.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from src.vm.image import FORMAT_VERSION, LANGUAGE_VERSION
from src.vm.opcodes import OPCODES


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HEADER_PATH = REPOSITORY_ROOT / "native" / "include" / "pwb" / "opcodes_generated.hpp"

_WIDTH_NAMES: dict[str, str] = {
    "u8": "Width::U8",
    "u16": "Width::U16",
    "u32": "Width::U32",
    "i32": "Width::I32",
    "i64": "Width::I64",
    "f64": "Width::F64",
}

_KIND_NAMES: dict[str, str] = {
    "value": "OperandKind::Value",
    "slot": "OperandKind::Slot",
    "target": "OperandKind::Target",
    "const": "OperandKind::Const",
    "spec": "OperandKind::Spec",
    "call": "OperandKind::Call",
    "pattern": "OperandKind::Pattern",
    "module": "OperandKind::Module",
    "type": "OperandKind::Type",
    "trait": "OperandKind::Trait",
    "field": "OperandKind::Field",
    "name": "OperandKind::Name",
    "export": "OperandKind::Export",
    "host": "OperandKind::Host",
    "event": "OperandKind::Event",
    "flags": "OperandKind::Flags",
}


def _c_string(value: str) -> str:
    body = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{body}"'


def render_header() -> str:
    """Render the complete generated header with LF newlines."""
    lines: list[str] = [
        "// Generated from src/vm/opcodes.py by src/vm/native/gen_opcodes.py.",
        "// Do not edit by hand.",
        "#pragma once",
        "",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        '#include "pwb/opcodes.hpp"',
        "",
        "namespace pwb {",
        "",
        "enum class Opcode : std::uint8_t {",
    ]
    for spec in OPCODES:
        lines.append(f"    {spec.name} = {spec.opcode},")
    lines.extend(["};", "", "namespace generated {", ""])

    for spec in OPCODES:
        if not spec.operands:
            continue
        lines.append(f"inline constexpr OperandSpec kOperands_{spec.name}[] = {{")
        for operand in spec.operands:
            width = _WIDTH_NAMES[operand.width]
            kind = _KIND_NAMES[operand.kind]
            lines.append(
                f"    {{{_c_string(operand.name)}, {width}, {kind}}},"
            )
        lines.extend(["};", ""])

    lines.append("inline constexpr OpcodeSpec kOpcodes[] = {")
    for spec in OPCODES:
        operands = f"kOperands_{spec.name}" if spec.operands else "nullptr"
        lines.append(
            "    {"
            f"{_c_string(spec.name)}, {spec.opcode}, {operands}, "
            f"{len(spec.operands)}, {spec.stack_in}, {spec.stack_out}, "
            f"{_c_string(spec.verifier)}"
            "},"
        )
    lines.extend(
        [
            "};",
            "",
            "inline constexpr std::size_t kOpcodeCount = "
            "sizeof(kOpcodes) / sizeof(kOpcodes[0]);",
            "",
            f"inline constexpr std::uint16_t kFormatVersion = {FORMAT_VERSION};",
            f"inline constexpr const char* kLanguageVersion = "
            f"{_c_string(LANGUAGE_VERSION)};",
            "",
            "} // namespace generated",
            "",
            "} // namespace pwb",
            "",
        ]
    )
    return "\n".join(lines)


def write_header() -> None:
    """Write the generated header with LF newlines."""
    HEADER_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEADER_PATH.write_text(render_header(), encoding="utf-8", newline="\n")


def header_is_current() -> bool:
    """Return true when the checked-in header matches the registry."""
    try:
        with HEADER_PATH.open("r", encoding="utf-8", newline="") as handle:
            existing = handle.read()
    except FileNotFoundError:
        return False
    return existing == render_header()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate native/include/pwb/opcodes_generated.hpp."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="rewrite the header")
    action.add_argument(
        "--check", action="store_true", help="exit 1 when the header is stale"
    )
    options = parser.parse_args(argv)
    if options.write:
        write_header()
        return 0
    if not header_is_current():
        print("stale")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
