"""Frame and local storage structures for the Phase 4B bytecode VM.

`LocalStore` gives the interpreter a dictionary shaped view over a contiguous
slot array while keeping slot indices stable. `VMFrame` owns the operand stack,
the instruction pointer, the active exception handlers and the module scope of
one call.
"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..error import powang_error_development, powang_throw
from ..powang_types import (
    PowangAny,
    PowangAnyType,
    PowangFunction,
    PowangObjectType,
    PowangTask,
)
from .image import CodeObject

if TYPE_CHECKING:
    from .modules import ModuleScope


_ABSENT = object()


def _undefined() -> PowangAny:
    value = PowangAnyType(0)
    value.defined = False
    value.any = "nova"
    return value


class LocalStore(MutableMapping[str, PowangAny]):
    """Name view over a contiguous slot array plus per frame tables.

    Slots are never renumbered while a frame runs. Deleting a name marks its
    slot absent with a sentinel, reads raise `KeyError`, and iteration walks
    the remaining declared names in slot order.
    """

    def __init__(self, names: Sequence[str], values: list[PowangAny] | None = None):
        self._names: list[str] = list(names)
        self._values: list[Any] = (
            list(values) if values is not None else [_undefined() for _ in self._names]
        )
        if len(self._values) < len(self._names):
            self._values.extend(_undefined() for _ in range(len(self._names) - len(self._values)))
        self._slots: dict[str, int] = {}
        for slot, name in enumerate(self._names):
            if name:
                self._slots[name] = slot

    def slot(self, name: str) -> int | None:
        """Return the slot bound to `name` or `None`."""
        slot = self._slots.get(name)
        if slot is None:
            return None
        if slot >= len(self._values) or self._values[slot] is _ABSENT:
            return None
        return slot

    def bind_slot(self, slot: int, name: str) -> None:
        """Bind `name` to an existing or newly extended slot."""
        if slot < 0:
            raise IndexError(f"negative local slot: {slot}")
        if slot >= len(self._values):
            self._values.extend(_ABSENT for _ in range(slot + 1 - len(self._values)))
        if slot >= len(self._names):
            self._names.extend("" for _ in range(slot + 1 - len(self._names)))
        old_name = self._names[slot]
        if old_name and self._slots.get(old_name) == slot:
            del self._slots[old_name]
        self._names[slot] = name
        self._slots[name] = slot
        if self._values[slot] is _ABSENT:
            self._values[slot] = _undefined()

    def add_slot(self, name: str) -> int:
        """Append a slot named `name` and return its index."""
        slot = len(self._names)
        self._names.append(name)
        self._values.append(_undefined())
        self._slots[name] = slot
        return slot

    def value_at(self, slot: int) -> PowangAny:
        """Return the value in `slot`, raising `KeyError` when absent."""
        if slot < 0 or slot >= len(self._values):
            raise IndexError(f"local slot out of range: {slot}")
        value = self._values[slot]
        if value is _ABSENT:
            name = self._names[slot] if slot < len(self._names) else str(slot)
            raise KeyError(name)
        return value

    def set_at(self, slot: int, value: PowangAny) -> None:
        """Write `value` into `slot`."""
        if slot < 0:
            raise IndexError(f"negative local slot: {slot}")
        if slot >= len(self._values):
            self._values.extend(_ABSENT for _ in range(slot + 1 - len(self._values)))
        if slot >= len(self._names):
            self._names.extend("" for _ in range(slot + 1 - len(self._names)))
        self._values[slot] = value

    def __getitem__(self, name: str) -> PowangAny:
        slot = self.slot(name)
        if slot is None:
            raise KeyError(name)
        return self.value_at(slot)

    def __setitem__(self, name: str, value: PowangAny) -> None:
        slot = self.slot(name)
        if slot is None:
            raise KeyError(name)
        self._values[slot] = value

    def __delitem__(self, name: str) -> None:
        slot = self.slot(name)
        if slot is None:
            raise KeyError(name)
        self._values[slot] = _ABSENT
        self._slots.pop(name, None)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for slot, name in enumerate(self._names):
            if not name or name in seen:
                continue
            if slot >= len(self._values) or self._values[slot] is _ABSENT:
                continue
            seen.add(name)
            yield name

    def __len__(self) -> int:
        count = 0
        for _ in self:
            count += 1
        return count

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return self.slot(name) is not None

    def setdefault(self, name: str, default: PowangAny | None = None) -> PowangAny:
        """Return `name` or add a slot with `default`, like a dictionary."""
        slot = self.slot(name)
        if slot is not None:
            return self.value_at(slot)
        value = _undefined() if default is None else default
        self.add_slot(name)
        self._values[self._slots[name]] = value
        return value

    def __repr__(self) -> str:
        return repr({name: self[name] for name in self})


@dataclass
class HandlerEntry:
    """One active exception handler in a frame."""

    start_ip: int
    end_ip: int
    catch_ip: int
    finally_ip: int
    resume_ip: int
    stack_depth: int
    local_watermark: int
    kind: str
    pending_error: BaseException | None = None
    pending_return: PowangAny | None = None
    state: str = "active"


class VMFrame:
    """One VM call frame."""

    def __init__(
        self,
        code: CodeObject,
        locals: LocalStore,
        functions: dict[str, list[PowangFunction]],
        types: dict[str, PowangObjectType],
        wildcards: dict[str, str],
        module_scope: "ModuleScope",
        receiver: PowangObjectType | None = None,
        closure: Any = None,
        task: PowangTask | None = None,
        is_function: bool = True,
    ) -> None:
        self.code = code
        self.locals = locals
        self.functions = functions
        self.types = types
        self.wildcards = wildcards
        self.module_scope = module_scope
        self.receiver = receiver
        self.closure = closure
        self.task = task
        self.is_function = is_function
        self.stack: list[PowangAny] = []
        self.ip: int = 0
        self.handlers: list[HandlerEntry] = []
        self.span_index: int = 0
        # Unwinding state used by the interpreter. It is not part of the
        # binding frame API but keeps transfer and finally handling local to
        # one frame.
        self.pending_error: BaseException | None = None
        self.pending_return: PowangAny | None = None
        self.transfer: tuple[str, int] | None = None
        self.name: str = code.name
        self.pending_error: BaseException | None = None
        self.pending_return: PowangAny | None = None
        self.transfer: tuple[str, int] | None = None
        self.captures: list[PowangAny] = []

    def push(self, value: PowangAny) -> None:
        """Push one value on the operand stack."""
        self.stack.append(value)

    def pop(self) -> PowangAny:
        """Pop one value from the operand stack."""
        return self.stack.pop()

    def peek(self) -> PowangAny:
        """Return the top of the operand stack without popping it."""
        return self.stack[-1]

    def require_stack(self, count: int, opname: str) -> None:
        """Raise a language development error when the stack is too short."""
        if count < 0:
            raise ValueError(f"negative stack requirement: {count}")
        if len(self.stack) < count:
            powang_throw(
                powang_error_development(
                    "vm",
                    f"{opname} requires {count} stack values but only "
                    f"{len(self.stack)} are available",
                )
            )

    def scope_variables(self) -> LocalStore:
        """Return the name view used by shared runtime helpers."""
        return self.locals
