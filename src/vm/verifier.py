"""Bytecode verifier for the Phase 4B virtual machine.

The verifier decodes every instruction, checks operand ranges and control flow
targets, runs a stack height dataflow analysis over the reachable instruction
graph and validates cross table references in a `ProgramImage`. It never
executes user code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .image import CodeObject, Constant, ProgramImage
from .opcodes import OpcodeSpec, decode_instruction


class VerificationError(Exception):
    """Raised when a code object or program image violates the contract."""


@dataclass(frozen=True)
class _Instruction:
    offset: int
    spec: OpcodeSpec
    operands: dict[str, int | float]
    next_offset: int


_CONDITIONAL_JUMPS = {
    "JUMP_IF_FALSE",
    "JUMP_IF_TRUE",
    "JUMP_IF_FALSE_KEEP",
    "JUMP_IF_TRUE_KEEP",
    "JUMP_IF_NOVA",
    "JUMP_IF_NOT_NOVA",
}

_CALL_OPCODES = {
    "CALL",
    "CALL_VALUE",
    "CALL_METHOD",
    "CALL_STATIC",
    "CALL_MODULE",
    "CALL_NATIVE",
    "CALL_BUILTIN",
    "CALL_TRAIT",
    "CALL_OPERATOR",
    "CALL_EXTERN",
    "CALL_ASYNC",
    "CALL_ASYNC_METHOD",
    "SPAWN",
    "HOST_CALL",
}

_RECEIVER_CALLS = {
    "CALL_METHOD",
    "CALL_TRAIT",
    "CALL_OPERATOR",
    "CALL_MODULE",
    "CALL_VALUE",
}

_REFERENCE_STORES = {
    "STORE_LOCAL",
    "STORE_GLOBAL",
    "STORE_NAME",
    "STORE_FIELD",
    "STORE_REF",
    "INDEX_SET",
    "MAKE_ARRAY",
    "MAKE_ARRAY_TYPED",
    "MAKE_TUPLE",
    "MAKE_TUPLE_TYPED",
    "MAKE_MAP",
    "MAKE_MAP_TYPED",
    "MAKE_SET",
    "MAKE_SET_TYPED",
}

_REFERENCE_PRODUCERS = {"REF_LOCAL", "REF_GLOBAL", "REF_FIELD", "REF_INDEX"}


def _fail(code: CodeObject, message: str, offset: int | None = None, opcode: str | None = None) -> None:
    name = code.qualname or code.name
    location = name if offset is None else f"{name}@{offset}"
    if opcode:
        location += f" {opcode}"
    raise VerificationError(f"{location}: {message}")


def verify_code(
    code: CodeObject,
    image: ProgramImage | None = None,
    strict: bool = True,
) -> None:
    """Verify one code object.

    Raises `VerificationError` on the first violation. Strict mode additionally
    requires a `max_stack` that covers the computed peak and rejects reachable
    paths that fall off the end of the instruction stream.
    """
    _check_metadata(code, image)
    if not code.bytecode:
        if strict:
            _fail(code, "missing return: code object is empty")
        return
    instructions, starts = _decode_all(code)
    _check_spans(code, instructions)
    _check_exception_ranges(code, starts)
    _check_operands(code, instructions, starts, image)
    _check_reference_lifetime(code, instructions)
    peak = _analyze_stack(code, instructions, starts, image, strict)
    if strict and code.max_stack < peak:
        _fail(
            code,
            f"max_stack {code.max_stack} is smaller than the computed peak {peak}",
        )


def verify_image(image: ProgramImage, strict: bool = True) -> None:
    """Verify every code object and all cross table references."""
    if image.entry_module < 0 or image.entry_module >= len(image.modules):
        raise VerificationError(f"image: entry module index out of range: {image.entry_module}")
    if image.entry_code < 0 or image.entry_code >= len(image.codes):
        raise VerificationError(f"image: entry code index out of range: {image.entry_code}")
    for module in image.modules:
        if module.code_index < 0 or module.code_index >= len(image.codes):
            raise VerificationError(
                f"image: module {module.name!r} code index out of range: {module.code_index}"
            )
    for function in image.functions:
        if function.code_index < 0 or function.code_index >= len(image.codes):
            raise VerificationError(
                f"image: function {function.name!r} code index out of range: {function.code_index}"
            )
    for index, site in enumerate(image.call_sites):
        if site.return_spec >= len(image.type_specs):
            raise VerificationError(
                f"image: call site {index} return spec index out of range: {site.return_spec}"
            )
    for index, constant in enumerate(image.constants):
        _check_constant_references(image, constant, f"image constant {index}")
    for code in image.codes:
        verify_code(code, image, strict)
        if code.constant_indices:
            if not image.constants:
                _fail(code, "constant indices reference an empty image constant pool")
            if code.constants and len(code.constant_indices) != len(code.constants):
                _fail(
                    code,
                    f"constant index count {len(code.constant_indices)} does not match "
                    f"the inline constant count {len(code.constants)}",
                )
            for position, index in enumerate(code.constant_indices):
                if index < 0 or index >= len(image.constants):
                    _fail(code, f"constant index {index} is out of range")
                if position < len(code.constants) and image.constants[index] != code.constants[position]:
                    _fail(
                        code,
                        f"constant index {index} does not match inline constant {position}",
                    )
        for position, constant in enumerate(code.constants):
            _check_constant_references(image, constant, f"{code.name} constant {position}")


def _check_metadata(code: CodeObject, image: ProgramImage | None) -> None:
    for name in ("local_count", "capture_count", "parameter_count"):
        value = getattr(code, name)
        if value < 0:
            _fail(code, f"{name} must not be negative: {value}")
    if code.max_stack < 0:
        _fail(code, f"max_stack must not be negative: {code.max_stack}")
    if code.parameter_names and len(code.parameter_names) != code.parameter_count:
        _fail(
            code,
            f"parameter name count {len(code.parameter_names)} does not match "
            f"parameter_count {code.parameter_count}",
        )
    if code.return_spec >= 0 and image is not None and code.return_spec >= len(image.type_specs):
        _fail(code, f"return spec index out of range: {code.return_spec}")


def _decode_all(code: CodeObject) -> tuple[list[_Instruction], set[int]]:
    instructions: list[_Instruction] = []
    starts: set[int] = set()
    offset = 0
    while offset < len(code.bytecode):
        starts.add(offset)
        try:
            opcode_spec, operands, next_offset = decode_instruction(code.bytecode, offset)
        except ValueError as exc:
            _fail(code, str(exc), offset)
        if next_offset <= offset:
            _fail(code, "instruction did not advance", offset)
        instructions.append(_Instruction(offset, opcode_spec, operands, next_offset))
        offset = next_offset
    if offset != len(code.bytecode):
        _fail(code, "instruction stream ended in the middle of an instruction", offset)
    return instructions, starts


def _check_spans(code: CodeObject, instructions: list[_Instruction]) -> None:
    if code.span_table:
        if len(code.span_table) != len(instructions):
            _fail(
                code,
                f"span table length {len(code.span_table)} does not match "
                f"instruction count {len(instructions)}",
            )
        if code.spans:
            for index in code.span_table:
                if index < 0 or index >= len(code.spans):
                    _fail(code, f"span index out of range: {index}")


def _check_exception_ranges(code: CodeObject, starts: set[int]) -> None:
    end = len(code.bytecode)
    for entry in code.exception_table:
        if entry.start_ip < 0 or entry.end_ip < 0:
            _fail(code, "exception range offsets must not be negative")
        if entry.start_ip not in starts:
            _fail(code, f"exception start is not an instruction boundary: {entry.start_ip}")
        if entry.end_ip > end:
            _fail(code, f"exception end is outside the code object: {entry.end_ip}")
        if entry.end_ip != end and entry.end_ip not in starts:
            _fail(code, f"exception end is not an instruction boundary: {entry.end_ip}")
        if entry.start_ip >= entry.end_ip:
            _fail(code, "exception start must be smaller than exception end")
        if entry.catch_ip >= 0 and entry.catch_ip not in starts:
            _fail(code, f"exception catch target is not an instruction boundary: {entry.catch_ip}")
        if entry.finally_ip >= 0 and entry.finally_ip not in starts:
            _fail(code, f"exception finally target is not an instruction boundary: {entry.finally_ip}")
        if entry.resume_ip >= 0 and entry.resume_ip not in starts and entry.resume_ip != end:
            _fail(code, f"exception resume target is not an instruction boundary: {entry.resume_ip}")
        if entry.stack_depth < 0:
            _fail(code, "exception stack depth must not be negative")
        if entry.local_watermark < 0:
            _fail(code, "exception local watermark must not be negative")


def _check_operands(
    code: CodeObject,
    instructions: list[_Instruction],
    starts: set[int],
    image: ProgramImage | None,
) -> None:
    end = len(code.bytecode)
    for instruction in instructions:
        opcode_spec = instruction.spec
        name = opcode_spec.name
        for operand in opcode_spec.operands:
            value = instruction.operands[operand.name]
            kind = operand.kind
            if kind == "const":
                _check_constant_index(code, instruction, int(value))
            elif kind == "spec":
                _check_constant_index(code, instruction, int(value))
            elif kind == "slot":
                if value < 0 or value >= code.local_count:
                    _fail(
                        code,
                        f"slot {value} is outside local_count {code.local_count}",
                        instruction.offset,
                        name,
                    )
            elif kind == "target":
                _check_target(code, instruction, operand.name, int(value), starts, end)
            elif image is not None:
                _check_image_operand(code, instruction, operand.name, kind, int(value), image)
        if name == "LOAD_CAPTURE":
            index = int(instruction.operands["index"])
            if index < 0 or index >= code.capture_count:
                _fail(
                    code,
                    f"capture index {index} is outside capture_count {code.capture_count}",
                    instruction.offset,
                    name,
                )
        if name in {"DECLARE_FUNCTION", "MAKE_FUNCTION"} and image is not None:
            index = int(instruction.operands["function"])
            if index < 0 or index >= len(image.functions):
                _fail(code, f"function index out of range: {index}", instruction.offset, name)
        if name == "DECLARE_EXTERN":
            index = int(instruction.operands["extern"])
            if index < 0 or index >= len(code.constants):
                _fail(code, f"extern index out of range: {index}", instruction.offset, name)
        if name in {"NEW_ENUM", "LOAD_ENUM_MEMBER"} and image is not None:
            type_index = int(instruction.operands["enum"])
            variant = int(instruction.operands["variant"])
            if 0 <= type_index < len(image.types):
                variants = image.types[type_index].variants
                if variants and (variant < 0 or variant >= len(variants)):
                    _fail(
                        code,
                        f"enum variant index out of range: {variant}",
                        instruction.offset,
                        name,
                    )
        if name == "MATCH" and image is not None:
            pattern_index = int(instruction.operands["pattern"])
            if 0 <= pattern_index < len(image.patterns):
                _check_pattern_slots(
                    code, instruction, image.patterns[pattern_index],
                )
        if name == "LOAD_MODULE_MEMBER" and image is not None:
            module_index = int(instruction.operands["module"])
            export_index = int(instruction.operands["export"])
            if 0 <= module_index < len(image.modules):
                exports = image.modules[module_index].exports
                if export_index < 0 or export_index >= len(exports):
                    _fail(
                        code,
                        f"module export index out of range: {export_index}",
                        instruction.offset,
                        name,
                    )


def _check_pattern_slots(code: CodeObject, instruction: _Instruction,
                         pattern) -> None:
    for _name, slot in pattern.bindings:
        if slot < 0 or slot >= code.local_count:
            _fail(
                code,
                f"pattern binding slot {slot} is outside local_count {code.local_count}",
                instruction.offset,
                instruction.spec.name,
            )
    if pattern.rest_slot >= 0 and pattern.rest_slot >= code.local_count:
        _fail(
            code,
            f"pattern rest slot {pattern.rest_slot} is outside local_count {code.local_count}",
            instruction.offset,
            instruction.spec.name,
        )
    for nested in pattern.nested:
        _check_pattern_slots(code, instruction, nested)
    for _field, nested in pattern.fields:
        _check_pattern_slots(code, instruction, nested)


def _check_constant_index(code: CodeObject, instruction: _Instruction, index: int) -> None:
    if index < 0 or index >= len(code.constants):
        _fail(
            code,
            f"constant index {index} is out of range for {len(code.constants)} constants",
            instruction.offset,
            instruction.spec.name,
        )


def _check_target(
    code: CodeObject,
    instruction: _Instruction,
    operand_name: str,
    target: int,
    starts: set[int],
    end: int,
) -> None:
    if instruction.spec.name == "TRY_BEGIN":
        if target < 0:
            return
        if target not in starts:
            _fail(
                code,
                f"{operand_name} target is not an instruction boundary: {target}",
                instruction.offset,
                instruction.spec.name,
            )
        return
    if target < 0 or target >= end:
        _fail(
            code,
            f"jump target out of range: {target}",
            instruction.offset,
            instruction.spec.name,
        )
    if target not in starts:
        _fail(
            code,
            f"jump target is not an instruction boundary: {target}",
            instruction.offset,
            instruction.spec.name,
        )


def _check_image_operand(
    code: CodeObject,
    instruction: _Instruction,
    operand_name: str,
    kind: str,
    value: int,
    image: ProgramImage,
) -> None:
    if value < 0:
        _fail(
            code,
            f"{operand_name} index must not be negative: {value}",
            instruction.offset,
            instruction.spec.name,
        )
    limit: int | None = None
    if kind == "call":
        limit = len(image.call_sites)
    elif kind == "pattern":
        limit = len(image.patterns)
    elif kind == "module":
        limit = len(image.modules)
    elif kind == "type":
        limit = len(image.types)
    elif kind == "trait":
        limit = len(image.traits)
    elif kind == "field":
        limit = len(image.global_names)
    elif kind == "name":
        limit = len(image.global_names)
    elif kind == "export":
        limit = len(image.global_names)
    if limit is None:
        return
    if limit == 0:
        return
    if value >= limit:
        _fail(
            code,
            f"{operand_name} index out of range: {value}",
            instruction.offset,
            instruction.spec.name,
        )


def _check_reference_lifetime(code: CodeObject, instructions: list[_Instruction]) -> None:
    for index in range(1, len(instructions)):
        current = instructions[index]
        previous = instructions[index - 1]
        if current.spec.name in _REFERENCE_STORES:
            if previous.spec.name in _REFERENCE_PRODUCERS:
                _fail(
                    code,
                    f"{current.spec.name} cannot store a reference produced by "
                    f"{previous.spec.name}",
                    current.offset,
                    current.spec.name,
                )


def _analyze_stack(
    code: CodeObject,
    instructions: list[_Instruction],
    starts: set[int],
    image: ProgramImage | None,
    strict: bool,
) -> int:
    by_offset = {instruction.offset: instruction for instruction in instructions}
    end = len(code.bytecode)
    heights: dict[int, int] = {0: 0}
    worklist: list[int] = [0]
    peak = 0
    falls_off_end = False
    while worklist:
        worklist.sort()
        offset = worklist.pop(0)
        height = heights[offset]
        instruction = by_offset[offset]
        name = instruction.spec.name
        if name in _CONDITIONAL_JUMPS and height < 1:
            _fail(
                code,
                "conditional jump requires at least one stack value",
                offset,
                name,
            )
        stack_in, stack_out = _instruction_stack_effect(instruction, image, code)
        if height < stack_in:
            _fail(
                code,
                f"stack underflow: needs {stack_in} values but height is {height}",
                offset,
                name,
            )
        result_height = height - stack_in + stack_out
        peak = max(peak, height, result_height)
        for successor, successor_height in _successor_heights(
            instruction, end, height, result_height,
        ):
            if successor == end:
                falls_off_end = True
                continue
            if successor not in starts:
                _fail(
                    code,
                    f"jump target is not an instruction boundary: {successor}",
                    offset,
                    name,
                )
            if successor not in heights:
                heights[successor] = successor_height
                worklist.append(successor)
            elif heights[successor] != successor_height:
                _fail(
                    code,
                    f"merge mismatch at offset {successor}: incoming heights "
                    f"{heights[successor]} and {successor_height}",
                    successor,
                    by_offset[successor].spec.name,
                )
    if strict and falls_off_end:
        _fail(code, "missing return: a reachable path falls off the end")
    return peak


def _successors(instruction: _Instruction, end: int) -> list[int]:
    name = instruction.spec.name
    if name == "JUMP":
        return [int(instruction.operands["target"])]
    if name in _CONDITIONAL_JUMPS or name in {"MATCH", "ITER_NEXT", "JUMP_IF_TRANSFER"}:
        target = int(instruction.operands["target"])
        next_offset = instruction.next_offset
        if next_offset <= end and next_offset != target:
            return [target, next_offset]
        return [target]
    if name in {"RETURN", "THROW", "RETHROW"}:
        return []
    return [instruction.next_offset] if instruction.next_offset <= end else []


def _successor_heights(
    instruction: _Instruction,
    end: int,
    height: int,
    result_height: int,
) -> list[tuple[int, int]]:
    """Return the successor offsets paired with their incoming heights."""
    if instruction.spec.name == "ITER_NEXT":
        target = int(instruction.operands["target"])
        next_offset = instruction.next_offset
        pairs: list[tuple[int, int]] = [(target, max(0, height - 1))]
        if next_offset <= end and next_offset != target:
            pairs.append((next_offset, height + 1))
        return pairs
    return [(successor, result_height) for successor in _successors(instruction, end)]


def _instruction_stack_effect(
    instruction: _Instruction, image: ProgramImage | None,
    code: CodeObject | None = None,
) -> tuple[int, int]:
    opcode_spec = instruction.spec
    if opcode_spec.stack_in >= 0:
        return opcode_spec.stack_in, opcode_spec.stack_out
    name = opcode_spec.name
    if name == "ROT":
        count = _count_operand(instruction)
        return count, count
    if name in {
        "MAKE_ARRAY",
        "MAKE_ARRAY_TYPED",
        "MAKE_TUPLE",
        "MAKE_TUPLE_TYPED",
        "MAKE_MAP",
        "MAKE_MAP_TYPED",
        "MAKE_SET",
        "MAKE_SET_TYPED",
        "CONCAT_STR",
    }:
        return _count_operand(instruction), 1
    if name in _CALL_OPCODES:
        return _call_argument_count(instruction, image), 1
    if name == "CONSTRUCT":
        return _call_argument_count(instruction, image), 1
    if name == "MAKE_ERROR":
        count = 0
        if code is not None:
            index = int(instruction.operands.get("spec", -1))
            if 0 <= index < len(code.constants):
                descriptor = code.constants[index].value
                if isinstance(descriptor, dict):
                    count = int(descriptor.get("argument_count", 1))
        return count, 1
    return 0, opcode_spec.stack_out


def _count_operand(instruction: _Instruction) -> int:
    value = instruction.operands.get("count", 0)
    return max(0, int(value))


def _call_argument_count(
    instruction: _Instruction, image: ProgramImage | None
) -> int:
    if image is None:
        return 0
    index = int(instruction.operands.get("call", -1))
    if index < 0 or index >= len(image.call_sites):
        return 0
    site = image.call_sites[index]
    count = len(site.argument_kinds)
    if count == 0:
        count = site.positional_count
    if instruction.spec.name == "CALL_VALUE":
        count += 1
    elif instruction.spec.name in _RECEIVER_CALLS:
        count += 1
    elif instruction.spec.name == "SPAWN" and site.method_ast is not None \
            and site.dispatch != "spawn_static":
        count += 1
    elif instruction.spec.name == "CALL_ASYNC" and site.dispatch in {
        "method", "module", "value",
    }:
        count += 1
    elif instruction.spec.name == "CALL_ASYNC_METHOD" and site.dispatch == "method":
        count += 1
    return max(0, count)


def _check_constant_references(image: ProgramImage, constant: Constant, where: str) -> None:
    if constant.kind == "call":
        _check_constant_index_value(constant.value, len(image.call_sites), "call site", where)
    elif constant.kind == "pattern":
        _check_constant_index_value(constant.value, len(image.patterns), "pattern", where)
    elif constant.kind == "type":
        _check_constant_index_value(constant.value, len(image.types), "type", where)
    elif constant.kind == "trait":
        _check_constant_index_value(constant.value, len(image.traits), "trait", where)
    elif constant.kind == "function":
        _check_constant_index_value(constant.value, len(image.functions), "function", where)
    elif constant.kind == "tuple":
        for position, item in enumerate(constant.value):
            _check_constant_references(image, item, f"{where} tuple item {position}")


def _check_constant_index_value(value: Any, limit: int, kind: str, where: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise VerificationError(f"{where}: {kind} constant must hold an index")
    if value < 0 or value >= limit:
        raise VerificationError(f"{where}: {kind} index out of range: {value}")
