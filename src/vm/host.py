"""Host access helpers for the VM.

The host boundary stays narrow. Builtins, native methods, externs and project
values are reached through the existing shared tables. This module only holds
the small glue that the interpreter needs for host facing opcodes.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..powang_types import PowangAny, PowangNova, PowangProject
from ..state import get_state


class HostRegistry:
    """Named host callables addressable by a HOST_CALL index."""

    def __init__(self):
        self.callables: list[Callable[[], PowangAny]] = []

    def register(self, function: Callable[[], PowangAny]) -> int:
        self.callables.append(function)
        return len(self.callables) - 1

    def call(self, index: int) -> PowangAny:
        if index < 0 or index >= len(self.callables):
            raise IndexError(f"host callable {index} is not registered")
        return self.callables[index]()


def load_project() -> PowangAny:
    project = getattr(get_state(), 'project_value', None)
    return project if project is not None else PowangNova()


def project_field(project: PowangProject, name: str) -> Optional[PowangAny]:
    return project.getProperty(name)
