"""Time helpers for Powang, all in UTC unless stated otherwise.

``sleep_ms`` blocks the interpreter thread. That is acceptable for the current
single-threaded runtime; an async-aware version belongs to the async wave.
"""

import time
from datetime import datetime, timezone
from typing import Any


def _require_text(value: Any, argument: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{argument} must be a string, got {type(value).__name__}")
    return value


def epoch() -> float:
    """Return the current Unix time in seconds (fractional)."""
    return time.time()


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in ``Z``."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def format_epoch(epoch: float, fmt: str) -> str:
    """Format Unix time ``epoch`` in UTC with a strftime pattern."""
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        raise ValueError(f"epoch must be a number, got {type(epoch).__name__}")
    fmt = _require_text(fmt, "fmt")
    try:
        moment = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise ValueError(f"epoch is out of range: {epoch}") from None
    return moment.strftime(fmt)


def sleep_ms(ms: int) -> None:
    """Block for ``ms`` milliseconds. Returns ``nova``."""
    if isinstance(ms, bool) or not isinstance(ms, int):
        raise ValueError(f"ms must be an integer, got {type(ms).__name__}")
    if ms < 0:
        raise ValueError(f"ms must not be negative, got {ms}")
    time.sleep(ms / 1000.0)
    return None
