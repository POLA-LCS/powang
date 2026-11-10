"""Stable text disassembler for the Phase 4B bytecode VM.

`disassemble_code` prints one code object and `disassemble_image` prints the
program image tables before each code object. Offsets are four digit decimal
numbers. Constant operands are rendered with the same deterministic JSON used
by the binary codec and truncated when they are long.
"""

from __future__ import annotations

from typing import Any

from .image import CodeObject, Constant, ProgramImage
from .opcodes import Operand, decode_instruction
from .values import encode_constant_json


def _short(text: str, limit: int = 60) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _constant_text(code: CodeObject, index: int) -> str:
    if index < 0 or index >= len(code.constants):
        return "<constant out of range>"
    constant: Constant = code.constants[index]
    return _short(encode_constant_json(constant.value))


def _image_string(image: ProgramImage | None, index: int, global_name: bool = False) -> str | None:
    if image is None or index < 0:
        return None
    values = image.global_names if global_name else image.strings
    if index < len(values):
        return values[index]
    if global_name and index < len(image.strings):
        return image.strings[index]
    return None


def _operand_text(
    code: CodeObject,
    image: ProgramImage | None,
    operand: Operand,
    value: int | float,
) -> str:
    kind = operand.kind
    integer = int(value)
    if kind == "const":
        return f"const={integer} {_constant_text(code, integer)}"
    if kind == "spec":
        text = f"spec={integer}"
        if 0 <= integer < len(code.constants):
            constant = code.constants[integer]
            if constant.kind == "spec":
                text += f" {_short(encode_constant_json(constant.value))}"
        return text
    if kind == "slot":
        return f"slot={integer}"
    if kind == "target":
        return f"target={integer}"
    if kind == "flags":
        return f"flags={integer}"
    if kind == "call":
        text = f"call={integer}"
        if image is not None and 0 <= integer < len(image.call_sites):
            site = image.call_sites[integer]
            text += f" {site.dispatch}:{site.name}"
        return text
    if kind == "pattern":
        text = f"pattern={integer}"
        if image is not None and 0 <= integer < len(image.patterns):
            text += f" {image.patterns[integer].kind}"
        return text
    if kind == "module":
        text = f"module={integer}"
        if image is not None and 0 <= integer < len(image.modules):
            text += f" {image.modules[integer].name}"
        return text
    if kind == "type":
        text = f"type={integer}"
        if image is not None and 0 <= integer < len(image.types):
            text += f" {image.types[integer].name}"
        return text
    if kind == "trait":
        text = f"trait={integer}"
        if image is not None and 0 <= integer < len(image.traits):
            text += f" {image.traits[integer].name}"
        return text
    if kind == "field":
        text = f"field={integer}"
        resolved = _image_string(image, integer, global_name=True)
        if resolved is not None:
            text += f" {resolved}"
        return text
    if kind == "name":
        text = f"name={integer}"
        resolved = _image_string(image, integer, global_name=True)
        if resolved is not None:
            text += f" {resolved}"
        return text
    if kind == "export":
        text = f"export={integer}"
        resolved = _image_string(image, integer)
        if resolved is not None:
            text += f" {resolved}"
        return text
    if kind == "host":
        text = f"host={integer}"
        resolved = _image_string(image, integer)
        if resolved is not None:
            text += f" {resolved}"
        return text
    if kind == "event":
        return f"event={integer}"
    if operand.name == "value":
        if isinstance(value, float):
            return repr(value)
        return str(integer)
    if isinstance(value, float):
        return f"{operand.name}={value!r}"
    return f"{operand.name}={integer}"


def _span_text(code: CodeObject, instruction_index: int) -> str:
    if not code.span_table or instruction_index >= len(code.span_table):
        return ""
    span_index = code.span_table[instruction_index]
    if not code.spans or span_index < 0 or span_index >= len(code.spans):
        return ""
    span = code.spans[span_index]
    return (
        f"; src={span.file_id}:{span.start_line}:{span.start_column}"
        f"-{span.end_line}:{span.end_column}"
    )


def _flags_text(flags: int) -> str:
    names: list[str] = []
    if flags & 0x01:
        names.append("async")
    if flags & 0x02:
        names.append("variadic")
    if flags & 0x04:
        names.append("method")
    if flags & 0x08:
        names.append("static")
    suffix = f"({','.join(names)})" if names else ""
    return f"0x{flags:04x}{suffix}"


def disassemble_code(code: CodeObject, image: ProgramImage | None = None) -> str:
    """Render `code` as stable text."""
    name = code.qualname or code.name
    lines = [
        f"code {name} args={code.parameter_count} locals={code.local_count} "
        f"stack={code.max_stack} captures={code.capture_count} "
        f"flags={_flags_text(code.flags)}"
    ]
    offset = 0
    index = 0
    while offset < len(code.bytecode):
        try:
            opcode_spec, operands, next_offset = decode_instruction(code.bytecode, offset)
        except ValueError as exc:
            lines.append(f"{offset:04d}  <decode error: {exc}>")
            break
        parts = [
            _operand_text(code, image, operand, operands[operand.name])
            for operand in opcode_spec.operands
        ]
        operand_text = " ".join(parts)
        line = f"{offset:04d}  {opcode_spec.name}"
        if operand_text:
            line += f" {operand_text}"
        line += _span_text(code, index)
        lines.append(line)
        offset = next_offset
        index += 1
    if code.local_names:
        lines.append("locals: " + ", ".join(
            f"{slot}={name!r}" for slot, name in enumerate(code.local_names)
        ))
    if code.parameter_names:
        lines.append("parameters: " + ", ".join(repr(name) for name in code.parameter_names))
    if code.exception_table:
        lines.append("exceptions:")
        for entry in code.exception_table:
            lines.append(
                f"  start={entry.start_ip} end={entry.end_ip} "
                f"catch={entry.catch_ip} finally={entry.finally_ip} "
                f"resume={entry.resume_ip} depth={entry.stack_depth} "
                f"watermark={entry.local_watermark} kind={entry.kind}"
            )
    return "\n".join(lines) + "\n"


def _table_header(name: str, count: int) -> str:
    return f"{name}: {count}"


def disassemble_image_json(image: ProgramImage) -> str:
    """Render every image table and code object as deterministic JSON."""
    import json

    def code_entry(code: CodeObject) -> dict:
        instructions = []
        offset = 0
        index = 0
        while offset < len(code.bytecode):
            opcode_spec, operands, next_offset = decode_instruction(
                code.bytecode, offset,
            )
            instructions.append({
                "offset": offset,
                "opcode": opcode_spec.name,
                "operands": operands,
                "span": code.span_table[index] if index < len(code.span_table) else 0,
            })
            offset = next_offset
            index += 1
        return {
            "name": code.name,
            "qualname": code.qualname,
            "source_file": code.source_file,
            "parameter_count": code.parameter_count,
            "local_count": code.local_count,
            "capture_count": code.capture_count,
            "max_stack": code.max_stack,
            "flags": code.flags,
            "local_names": list(code.local_names),
            "parameter_names": list(code.parameter_names),
            "return_spec": code.return_spec,
            "instructions": instructions,
            "spans": [
                {
                    "file_id": span.file_id,
                    "start_line": span.start_line,
                    "start_column": span.start_column,
                    "end_line": span.end_line,
                    "end_column": span.end_column,
                }
                for span in code.spans
            ],
            "exceptions": [
                {
                    "start_ip": entry.start_ip,
                    "end_ip": entry.end_ip,
                    "catch_ip": entry.catch_ip,
                    "finally_ip": entry.finally_ip,
                    "resume_ip": entry.resume_ip,
                    "stack_depth": entry.stack_depth,
                    "local_watermark": entry.local_watermark,
                    "kind": entry.kind,
                }
                for entry in code.exception_table
            ],
        }

    payload = {
        "format": image.format_version,
        "language": image.language_version,
        "entry_module": image.entry_module,
        "entry_code": image.entry_code,
        "modules": [
            {
                "name": module.name,
                "path": module.path,
                "code_index": module.code_index,
                "exports": [list(item) for item in module.exports],
            }
            for module in image.modules
        ],
        "types": [
            {
                "name": info.name,
                "kind": info.kind,
                "variants": list(info.variants),
                "properties": [list(item) for item in info.properties],
                "methods": [list(item) for item in info.methods],
            }
            for info in image.types
        ],
        "traits": [
            {
                "name": info.name,
                "properties": list(info.properties),
                "methods": [list(item) for item in info.methods],
            }
            for info in image.traits
        ],
        "functions": [
            {
                "name": info.name,
                "code_index": info.code_index,
                "min_argc": info.min_argc,
            }
            for info in image.functions
        ],
        "constants": [
            {"kind": constant.kind, "value": encode_constant_json(constant.value)}
            for constant in image.constants
        ],
        "call_sites": [
            {
                "dispatch": site.dispatch,
                "name": site.name,
                "positional_count": site.positional_count,
                "argument_kinds": list(site.argument_kinds),
                "argument_names": list(site.argument_names),
                "type_argument_count": site.type_argument_count,
                "is_async": site.is_async,
            }
            for site in image.call_sites
        ],
        "patterns": [
            {
                "kind": pattern.kind,
                "type_name": pattern.type_name,
                "bindings": [list(item) for item in pattern.bindings],
                "rest_slot": pattern.rest_slot,
            }
            for pattern in image.patterns
        ],
        "type_specs": [
            encode_constant_json(spec_value) for spec_value in image.type_specs
        ],
        "sources": list(image.sources),
        "global_names": list(image.global_names),
        "strings": list(image.strings),
        "debug_lines": [
            encode_constant_json(value) for value in image.debug_lines
        ],
        "codes": [code_entry(code) for code in image.codes],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def disassemble_image(image: ProgramImage) -> str:
    """Render every program image table and code object as stable text."""
    lines = [
        f"image format={image.format_version} language={image.language_version} "
        f"flags={_flags_text(image.flags)} entry_module={image.entry_module} "
        f"entry_code={image.entry_code}"
    ]
    lines.append(_table_header("modules", len(image.modules)))
    for index, module in enumerate(image.modules):
        lines.append(
            f"module {index} name={module.name!r} path={module.path!r} "
            f"code={module.code_index} imports={len(module.imports)} "
            f"exports={len(module.exports)}"
        )
    lines.append(_table_header("types", len(image.types)))
    for index, info in enumerate(image.types):
        lines.append(
            f"type {index} name={info.name!r} kind={info.kind} "
            f"params={len(info.type_parameters)} properties={len(info.properties)} "
            f"methods={len(info.methods)} variants={len(info.variants)}"
        )
    lines.append(_table_header("traits", len(image.traits)))
    for index, info in enumerate(image.traits):
        lines.append(
            f"trait {index} name={info.name!r} properties={len(info.properties)} "
            f"methods={len(info.methods)}"
        )
    lines.append(_table_header("functions", len(image.functions)))
    for index, info in enumerate(image.functions):
        lines.append(
            f"function {index} name={info.name!r} code={info.code_index} "
            f"min_argc={info.min_argc} flags={_short(encode_constant_json(info.flags))}"
        )
    lines.append(_table_header("constants", len(image.constants)))
    for index, constant in enumerate(image.constants):
        lines.append(
            f"constant {index} kind={constant.kind} "
            f"value={_short(encode_constant_json(constant.value))}"
        )
    lines.append(_table_header("call_sites", len(image.call_sites)))
    for index, site in enumerate(image.call_sites):
        lines.append(
            f"call_site {index} dispatch={site.dispatch} name={site.name!r} "
            f"module={site.module!r} positional={site.positional_count} "
            f"args={len(site.argument_kinds)} types={site.type_argument_count} "
            f"async={site.is_async}"
        )
    lines.append(_table_header("patterns", len(image.patterns)))
    for index, pattern in enumerate(image.patterns):
        lines.append(
            f"pattern {index} kind={pattern.kind} type={pattern.type_name!r} "
            f"bindings={len(pattern.bindings)} nested={len(pattern.nested)} "
            f"fields={len(pattern.fields)} rest={pattern.rest_slot}"
        )
    lines.append(_table_header("type_specs", len(image.type_specs)))
    for index, spec_value in enumerate(image.type_specs):
        lines.append(
            f"type_spec {index} {_short(encode_constant_json(spec_value))}"
        )
    lines.append(_table_header("sources", len(image.sources)))
    for index, source in enumerate(image.sources):
        lines.append(f"source {index} {source!r}")
    lines.append(_table_header("global_names", len(image.global_names)))
    for index, name in enumerate(image.global_names):
        lines.append(f"global_name {index} {name!r}")
    lines.append(_table_header("strings", len(image.strings)))
    for index, value in enumerate(image.strings):
        lines.append(f"string {index} {value!r}")
    lines.append(_table_header("debug_lines", len(image.debug_lines)))
    for index, value in enumerate(image.debug_lines):
        lines.append(f"debug_line {index} {_short(encode_constant_json(value))}")
    for code in image.codes:
        lines.append("")
        lines.extend(disassemble_code(code, image).rstrip("\n").splitlines())
    return "\n".join(lines) + "\n"
