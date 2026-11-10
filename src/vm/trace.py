"""Trace events and text sinks for the Phase 4B bytecode VM.

Tracing is deliberately small. The interpreter builds a `TraceEvent` for an
instruction, a call, a return, an error or a task transition, and a sink
decides where the event goes. `TextTraceSink` writes one compact line per
event.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Protocol, TextIO


TRACE_KINDS: tuple[str, ...] = ("instruction", "call", "return", "error", "task")


@dataclass
class TraceEvent:
    """One trace record emitted by the VM."""

    kind: str
    frame_name: str = ""
    ip: int = 0
    opcode: str = ""
    stack_depth: int = 0
    line: int | None = None
    column: int | None = None
    detail: Any = None


class TraceSink(Protocol):
    """Protocol implemented by every trace destination."""

    def emit(self, event: TraceEvent) -> None:
        """Write one event."""


class TextTraceSink:
    """Write compact single line events to a text stream."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream: TextIO = stream if stream is not None else sys.stdout

    def emit(self, event: TraceEvent) -> None:
        parts = [
            event.kind,
            event.frame_name,
            f"ip={event.ip}",
            f"opcode={event.opcode}",
            f"depth={event.stack_depth}",
        ]
        if event.line is not None:
            column = event.column if event.column is not None else 0
            parts.append(f"at={event.line}:{column}")
        if event.detail is not None and event.detail != "":
            parts.append(str(event.detail))
        self.stream.write(" ".join(parts) + "\n")
        self.stream.flush()
