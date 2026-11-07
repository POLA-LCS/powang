"""Structured logging for powang programs (ADR-0001 W37).

Everything is written to stderr so program output on stdout stays clean.
The minimum level is per interpreter state, seeded from POWANG_LOG_LEVEL.
"""

from __future__ import annotations

import datetime
import json
import sys

LEVELS: dict[str, int] = {
    "debug": 10,
    "info": 20,
    "warn": 30,
    "error": 40,
}


def _state():
    ## Imported lazily to avoid a cycle with state -> powang_types.
    from ..state import get_state
    return get_state()


def _timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(level: str, message: str, fields: object = None) -> None:
    state = _state()
    minimum = LEVELS.get(getattr(state, "log_level", "info"), LEVELS["info"])
    if LEVELS.get(level, LEVELS["info"]) < minimum:
        return
    line = f"{_timestamp()} {level.upper()} {message}"
    if isinstance(fields, dict) and fields:
        try:
            line += " " + json.dumps(fields, default=repr, ensure_ascii=False)
        except (TypeError, ValueError):
            line += " " + repr(fields)
    print(line, file=sys.stderr, flush=True)


def debug(message: str) -> None:
    _emit("debug", str(message))


def info(message: str) -> None:
    _emit("info", str(message))


def warn(message: str) -> None:
    _emit("warn", str(message))


def error(message: str) -> None:
    _emit("error", str(message))


def with_fields(level: str, message: str, fields: object) -> None:
    _emit(str(level).lower(), str(message), fields)


def set_level(level: str) -> None:
    name = str(level).lower()
    if name not in LEVELS:
        raise ValueError(f"unknown log level: {level!r}; expected debug, info, warn or error")
    _state().log_level = name


def is_enabled(level: str) -> bool:
    state = _state()
    minimum = LEVELS.get(getattr(state, "log_level", "info"), LEVELS["info"])
    return LEVELS.get(str(level).lower(), LEVELS["info"]) >= minimum


def access(request_id: int, method: str, path: str, status: int, elapsed_ms: float) -> None:
    """One access-log record. Never includes headers or bodies."""
    _emit("info", "request", {
        "request_id": request_id,
        "method": method,
        "path": path,
        "status": status,
        "elapsed_ms": round(float(elapsed_ms), 3),
    })
