"""Hashing and token helpers for Powang.

All inputs are UTF-8 encoded text, outputs are lowercase hex strings.
``constant_time_compare`` uses :func:`hmac.compare_digest` so it does not leak
the position of the first differing byte through timing.
"""

import hashlib
import hmac
import secrets
from typing import Any


def _require_text(value: Any, argument: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{argument} must be a string, got {type(value).__name__}")
    return value


def sha256(text: str) -> str:
    """Return the SHA-256 digest of the UTF-8 text, as lowercase hex."""
    return hashlib.sha256(_require_text(text, "text").encode("utf-8")).hexdigest()


def hmac_sha256(key: str, message: str) -> str:
    """Return the HMAC-SHA-256 of ``message`` under ``key``, as lowercase hex."""
    return hmac.new(
        _require_text(key, "key").encode("utf-8"),
        _require_text(message, "message").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def random_token(byte_length: int) -> str:
    """Return ``byte_length`` cryptographically secure random bytes as hex."""
    if isinstance(byte_length, bool) or not isinstance(byte_length, int):
        raise ValueError(
            f"byte_length must be an integer, got {type(byte_length).__name__}"
        )
    if byte_length <= 0:
        raise ValueError(f"byte_length must be positive, got {byte_length}")
    if byte_length > 4096:
        raise ValueError(f"byte_length must be at most 4096, got {byte_length}")
    return secrets.token_hex(byte_length)


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings without short-circuiting on the first difference."""
    return hmac.compare_digest(
        _require_text(a, "a").encode("utf-8"),
        _require_text(b, "b").encode("utf-8"),
    )
