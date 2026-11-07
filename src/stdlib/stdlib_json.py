"""Minimal JSON support for Powang.

Values cross the extern boundary as plain Python objects: ``dict`` for maps,
``list`` for arrays, ``str``/``int``/``float``/``bool``/``None`` for scalars.
The runtime converts those to Powang maps, arrays and native types.

Policy:

* nesting deeper than :data:`MAX_DEPTH` is rejected on both parse and stringify
* map keys must be strings when stringifying
* invalid input raises ``ValueError`` (the runtime turns it into a catchable
  ``[EXTERN ERROR]``)
"""

import json
from typing import Any

MAX_DEPTH: int = 100


def _check_depth(value: Any, depth: int = 1) -> None:
    if depth > MAX_DEPTH:
        raise ValueError(f"JSON nesting exceeds the maximum depth of {MAX_DEPTH}")
    if isinstance(value, dict):
        for key, item in value.items():
            _check_depth(key, depth + 1)
            _check_depth(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _check_depth(item, depth + 1)


def _check_string_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"JSON object keys must be strings, got {type(key).__name__} "
                    f"at {path}"
                )
            _check_string_keys(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_string_keys(item, f"{path}[{index}]")


def parse(text: str) -> Any:
    """Parse a JSON document into a Powang value."""
    if not isinstance(text, str):
        raise ValueError(f"text must be a string, got {type(text).__name__}")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"invalid JSON: {error.msg} at line {error.lineno} column {error.colno}"
        ) from None
    except RecursionError:
        raise ValueError(
            f"invalid JSON: nesting exceeds the maximum depth of {MAX_DEPTH}"
        ) from None
    _check_depth(value)
    return value


def stringify(value: Any, indent: int = 0) -> str:
    """Serialize a Powang value to JSON text.

    ``indent`` of zero produces compact output. A positive value pretty-prints
    with that many spaces per level.
    """
    if isinstance(indent, bool) or not isinstance(indent, int):
        raise ValueError(f"indent must be an integer, got {type(indent).__name__}")
    if indent < 0:
        raise ValueError(f"indent must not be negative, got {indent}")
    _check_depth(value)
    _check_string_keys(value)
    try:
        return json.dumps(
            value,
            indent=indent if indent > 0 else None,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"cannot serialize value to JSON: {error}") from None
