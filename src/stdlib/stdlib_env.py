"""Environment and script-argument helpers for Powang.

``env.get`` returns ``None`` when the variable is unset; the runtime maps that
to a value-less ``nova``. ``env.get_or`` returns a caller-supplied default.
``env.has`` reports presence, including variables whose value is the empty
string (``os.environ`` cannot distinguish those from missing names on every
platform, but it does on Windows and POSIX shells).

The ``args`` module reuses these helpers. ``argv`` returns the arguments
passed to the interpreter after the input file; ``argv_get`` and
``argv_count`` index that list. The interpreter publishes them through
``set_argv``; no other module reads ``sys.argv`` for this purpose.
"""

import os
from typing import Any, Optional

from ..state import get_state


def _require_text(value: Any, argument: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{argument} must be a string, got {type(value).__name__}")
    return value


def get(name: str) -> Optional[str]:
    """Return the environment variable, or ``None`` when it is unset."""
    return os.environ.get(_require_text(name, "name"))


def get_or(name: str, default: str) -> str:
    """Return the environment variable, or ``default`` when it is unset."""
    return os.environ.get(
        _require_text(name, "name"),
        _require_text(default, "default"),
    )


def has(name: str) -> bool:
    """Report whether the environment variable is set."""
    return _require_text(name, "name") in os.environ


def set_argv(values: list[str]) -> None:
    """Replace the active state's script arguments."""
    arguments = get_state().script_argv
    arguments.clear()
    arguments.extend(str(value) for value in values)


def argv() -> list[str]:
    """Return the script arguments (everything after the input file)."""
    return list(get_state().script_argv)


def argv_get(index: int) -> Optional[str]:
    """Return one script argument by index, or ``None`` when out of range."""
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError(f"index must be an integer, got {type(index).__name__}")
    arguments = argv()
    if index < 0:
        index += len(arguments)
    if 0 <= index < len(arguments):
        return arguments[index]
    return None


def argv_count() -> int:
    """Return the number of script arguments."""
    return len(argv())
