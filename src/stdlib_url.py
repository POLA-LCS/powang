"""URL helpers for Powang.

Encoding follows the ``application/x-www-form-urlencoded`` convention used by
``urllib.parse.quote_plus`` / ``unquote_plus``: spaces become ``+`` and other
reserved characters are percent-encoded.
"""

from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlencode


def _require_text(value: Any, argument: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{argument} must be a string, got {type(value).__name__}")
    return value


def encode(text: str) -> str:
    """Percent-encode text for use in a query string (spaces become ``+``)."""
    return quote_plus(_require_text(text, "text"))


def decode(text: str) -> str:
    """Decode a percent-encoded query string (``+`` becomes a space)."""
    return unquote_plus(_require_text(text, "text"))


def parse_query(query: str) -> dict[str, Any]:
    """Parse a query string into a map.

    A key that appears once maps to its value. A key that appears several
    times maps to an array of its values, preserving order. Blank values are
    kept.
    """
    query = _require_text(query, "query")
    parsed = parse_qs(query, keep_blank_values=True)
    result: dict[str, Any] = {}
    for key, values in parsed.items():
        result[key] = values[0] if len(values) == 1 else list(values)
    return result


def _to_text(value: Any, key: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    raise ValueError(
        f"query value for {key!r} must be a string, number, boolean or nova, "
        f"got {type(value).__name__}"
    )


def query_build(mapping: dict) -> str:
    """Build a query string from a map. Array values become repeated keys."""
    if not isinstance(mapping, dict):
        raise ValueError(f"mapping must be a map, got {type(mapping).__name__}")
    normalized: dict[str, Any] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise ValueError(
                f"query keys must be strings, got {type(key).__name__}"
            )
        if isinstance(value, (list, tuple)):
            normalized[key] = [_to_text(item, key) for item in value]
        else:
            normalized[key] = _to_text(value, key)
    return urlencode(normalized, doseq=True)
