"""Error value conversion and unwinding helpers for the VM.

The tree walker and the VM share `PowangError` and `PowangErrorValue`. These
helpers convert between them without inventing new diagnostic text and format
a frame list for diagnostics that travel through task or call boundaries.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, NoReturn

from ..error import PowangError, powang_error_from_exception
from ..powang_types import PowangErrorValue


def to_error_value(error: PowangError) -> PowangErrorValue:
    """Wrap a `PowangError` in a catchable language error value."""
    return PowangErrorValue.from_error(error)


def from_error_value(value: PowangErrorValue) -> PowangError:
    """Return the `PowangError` carried by a language error value."""
    error = getattr(value, "error", None)
    if isinstance(error, PowangError):
        return error
    if isinstance(error, BaseException):
        result = PowangError(
            kind=None,
            message=str(error),
            text=str(getattr(value, "data", "")),
        )
        value.error = result
        return result
    result = PowangError(kind=None, message="", text=str(getattr(value, "data", "")))
    value.error = result
    return result


def raise_error_value(value: PowangErrorValue) -> NoReturn:
    """Raise the error carried by a language error value."""
    error = getattr(value, "error", None)
    if isinstance(error, BaseException):
        raise error
    raise from_error_value(value)


def error_value_from_exception(exc: BaseException) -> PowangErrorValue | None:
    """Convert a Python exception carrying a language error, or return `None`."""
    error = powang_error_from_exception(exc)
    if error is None:
        return None
    return PowangErrorValue.from_error(error)


def format_frame(frame: Any) -> str:
    """Render one frame record as text."""
    render = getattr(frame, "render", None)
    if callable(render):
        return str(render())
    return str(frame)


def format_frames(frames: Iterable[Any] | None) -> str:
    """Render a frame list as one line per frame."""
    if frames is None:
        return ""
    return "\n".join(format_frame(frame) for frame in frames)


# Short aliases used by callers that prefer the value first naming.
error_to_value = to_error_value
value_to_error = from_error_value
raise_value = raise_error_value
