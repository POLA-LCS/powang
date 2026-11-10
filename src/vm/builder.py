"""Label based instruction builder for the Phase 4B bytecode VM.

The compiler emits symbolic instructions and labels here. `finish` resolves
labels in two passes, encodes operands, builds the source span table and
produces a `CodeObject`. Labels are resolved once and `patch` is idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .image import (
    CodeObject,
    Constant,
    ExceptionEntry,
    SourceSpan,
)
from .opcodes import BY_NAME, OpcodeSpec, encode_operands, spec
from .values import stable_key


@dataclass(frozen=True)
class Label:
    """A symbolic instruction offset."""

    id: int


_INT_LIMITS: dict[str, tuple[int, int]] = {
    "u8": (0, 0xFF),
    "u16": (0, 0xFFFF),
    "u32": (0, 0xFFFFFFFF),
    "i32": (-0x80000000, 0x7FFFFFFF),
    "i64": (-0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
}


class Builder:
    """Builds one `CodeObject` from symbolic instructions."""

    def __init__(
        self,
        name: str,
        qualname: str | None = None,
        source_file: int = 0,
    ) -> None:
        self.name = name
        self.qualname = qualname if qualname is not None else name
        self.source_file = source_file
        self._instructions: list[tuple[str, tuple[Any, ...], int]] = []
        self._labels: dict[int, int | None] = {}
        self._duplicate_labels: set[int] = set()
        self._next_label = 0
        self._constants: list[Constant] = []
        self._constant_keys: dict[tuple[str, str], int] = {}
        self._spans: list[SourceSpan] = []
        self._span_keys: dict[SourceSpan, int] = {}
        self._local_names: list[str] = []
        self._parameter_names: list[str] = []
        self._patched = False

    def emit(self, opcode: str, *operands: int | float, span: int = 0) -> int:
        """Append one instruction and return its instruction index."""
        opcode_spec = spec(opcode)
        if len(operands) != len(opcode_spec.operands):
            raise ValueError(
                f"{opcode} expects {len(opcode_spec.operands)} operands "
                f"but {len(operands)} were given"
            )
        if not isinstance(span, int) or isinstance(span, bool) or span < 0:
            raise ValueError(f"span must be a non negative integer, got {span!r}")
        normalized: list[Any] = []
        for operand, value in zip(opcode_spec.operands, operands):
            if isinstance(value, Label):
                if operand.kind != "target":
                    raise ValueError(
                        f"{opcode}.{operand.name} does not accept a label"
                    )
                normalized.append(value)
                continue
            if operand.width == "f64":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError(f"{opcode}.{operand.name} must be a number")
                normalized.append(float(value))
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{opcode}.{operand.name} must be an integer")
            low, high = _INT_LIMITS[operand.width]
            if not low <= value <= high:
                raise ValueError(
                    f"{opcode}.{operand.name}={value} is out of range "
                    f"for {operand.width}"
                )
            normalized.append(int(value))
        self._instructions.append((opcode_spec.name, tuple(normalized), span))
        self._patched = False
        return len(self._instructions) - 1

    def emit_label(self, label: Label) -> None:
        """Place `label` at the current instruction offset."""
        if label.id not in self._labels:
            self._labels[label.id] = None
        if self._labels[label.id] is not None:
            self._duplicate_labels.add(label.id)
        else:
            self._labels[label.id] = len(self._instructions)
        self._patched = False

    def place(self, label: Label) -> None:
        """Place `label` at the current instruction offset."""
        self.emit_label(label)

    def new_label(self) -> Label:
        """Create a fresh unplaced label."""
        label = Label(self._next_label)
        self._next_label += 1
        self._labels[label.id] = None
        self._patched = False
        return label

    def patch(self) -> None:
        """Resolve every label operand. Calling it twice is a no-op."""
        if self._patched:
            return
        for label_id, offset in self._labels.items():
            if label_id in self._duplicate_labels:
                raise ValueError(f"label {label_id} was placed more than once")
            if offset is None:
                raise ValueError(f"label {label_id} was never placed")
        byte_offsets: list[int] = []
        offset = 0
        for opcode, _operands, _span in self._instructions:
            byte_offsets.append(offset)
            offset += BY_NAME[opcode].size
        byte_offsets.append(offset)
        label_offsets = {
            label_id: byte_offsets[index]
            for label_id, index in self._labels.items()
        }
        resolved_instructions: list[tuple[str, tuple[Any, ...], int]] = []
        for opcode, operands, span in self._instructions:
            opcode_spec = BY_NAME[opcode]
            resolved: list[Any] = []
            for operand, value in zip(opcode_spec.operands, operands):
                if isinstance(value, Label):
                    target = label_offsets.get(value.id)
                    if target is None:
                        raise ValueError(f"label {value.id} names no placed label")
                    resolved.append(target)
                else:
                    resolved.append(value)
            resolved_instructions.append((opcode, tuple(resolved), span))
        self._instructions = resolved_instructions
        self._label_offsets = label_offsets
        self._patched = True

    def label_offset(self, label: Label) -> int:
        """Return the byte offset of a placed label."""
        self.patch()
        offsets = getattr(self, "_label_offsets", {})
        if label.id not in offsets:
            raise ValueError(f"label {label.id} names no placed label")
        return offsets[label.id]

    def new_constant(self, kind: str, value: Any) -> int:
        """Add a constant to the local pool, deduplicating structurally."""
        key = (kind, stable_key(value))
        existing = self._constant_keys.get(key)
        if existing is not None:
            return existing
        index = len(self._constants)
        self._constants.append(Constant(kind, value))
        self._constant_keys[key] = index
        return index

    def add_span(self, span: SourceSpan) -> int:
        """Add a source span to the local table, deduplicating identical spans."""
        if not isinstance(span, SourceSpan):
            raise TypeError(f"expected SourceSpan, got {type(span).__name__}")
        existing = self._span_keys.get(span)
        if existing is not None:
            return existing
        index = len(self._spans)
        self._spans.append(span)
        self._span_keys[span] = index
        return index

    def declare_local(self, name: str) -> int:
        """Declare a named local and return its slot."""
        slot = len(self._local_names)
        self._local_names.append(name)
        return slot

    def reserve_local(self) -> int:
        """Reserve an unnamed local slot and return it."""
        slot = len(self._local_names)
        self._local_names.append("")
        return slot

    def set_parameter_names(self, names: Sequence[str]) -> None:
        """Set the parameter name metadata used by `finish`."""
        self._parameter_names = list(names)

    def stack_effect_bound(self) -> int:
        """Return a conservative operand stack bound for allocation.

        The walk is linear. Variable height opcodes use their count operand
        when the instruction has one and zero for calls, where the argument
        count lives in a call site constant. Underflow is clamped at zero.
        """
        depth = 0
        peak = 0
        for opcode, operands, _span in self._instructions:
            opcode_spec = BY_NAME[opcode]
            stack_in, stack_out = _stack_effect(opcode_spec, operands)
            depth = max(0, depth - stack_in) + stack_out
            peak = max(peak, depth)
        return peak

    def finish(
        self,
        *,
        local_count: int | None = None,
        capture_count: int = 0,
        flags: int = 0,
        return_spec: int = -1,
        trait_name: str | None = None,
        operator_trait: str | None = None,
        fallback_ast: Any = None,
        exception_table: Sequence[ExceptionEntry] = (),
    ) -> CodeObject:
        """Resolve labels and produce the final `CodeObject`."""
        self.patch()
        if local_count is None:
            local_count = len(self._local_names)
        if local_count < 0:
            raise ValueError(f"local_count must not be negative: {local_count}")
        if local_count < len(self._local_names):
            raise ValueError(
                f"local_count {local_count} is smaller than the {len(self._local_names)} "
                "declared local names"
            )
        if local_count < len(self._parameter_names):
            raise ValueError(
                f"local_count {local_count} is smaller than the "
                f"{len(self._parameter_names)} parameter names"
            )
        parts: list[bytes] = []
        span_table: list[int] = []
        for opcode, operands, span in self._instructions:
            opcode_spec = BY_NAME[opcode]
            parts.append(bytes([opcode_spec.opcode]))
            parts.append(encode_operands(opcode_spec, operands))
            span_table.append(span)
        constants = tuple(self._constants)
        return CodeObject(
            name=self.name,
            qualname=self.qualname,
            source_file=self.source_file,
            parameter_count=len(self._parameter_names),
            local_count=local_count,
            capture_count=capture_count,
            max_stack=self.stack_effect_bound() + 8,
            max_frame_depth=1,
            bytecode=b"".join(parts),
            constant_indices=tuple(range(len(constants))),
            constants=constants,
            spans=tuple(self._spans),
            span_table=tuple(span_table),
            exception_table=tuple(exception_table),
            local_names=tuple(self._local_names),
            parameter_names=tuple(self._parameter_names),
            return_spec=return_spec,
            flags=flags,
            trait_name=trait_name,
            operator_trait=operator_trait,
            fallback_ast=fallback_ast,
        )


def _stack_effect(opcode_spec: OpcodeSpec, operands: Sequence[Any]) -> tuple[int, int]:
    if opcode_spec.stack_in >= 0:
        return opcode_spec.stack_in, opcode_spec.stack_out
    if opcode_spec.name == "ROT":
        count = _count_operand(opcode_spec, operands)
        return count, count
    if opcode_spec.name in {
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
        return _count_operand(opcode_spec, operands), 1
    if opcode_spec.name == "MAKE_ERROR":
        return 0, 1
    return 0, opcode_spec.stack_out


def _count_operand(opcode_spec: OpcodeSpec, operands: Sequence[Any]) -> int:
    for operand, value in zip(opcode_spec.operands, operands):
        if operand.name == "count":
            return max(0, int(value))
    return 0
