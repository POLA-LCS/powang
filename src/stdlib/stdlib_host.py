"""Generic host callback bridge for powang programs."""

from __future__ import annotations

from typing import Any

_callbacks: dict[str, Any] = {}


def register(name: str, callback: Any) -> None:
    _callbacks[name] = callback


def unregister(name: str) -> None:
    _callbacks.pop(name, None)


def call(name: str, arguments: Any) -> Any:
    callback = _callbacks.get(name)
    if callback is None:
        raise RuntimeError(f"unknown host callback: {name}")
    if isinstance(arguments, (list, tuple)):
        return callback(*arguments)
    return callback(arguments)
