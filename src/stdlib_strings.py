"""String helpers exposed to Powang through the ``strings`` module.

Every function takes and returns plain Python values. The extern call site in
:mod:`src.runtime` converts Powang values on the way in and out, and wraps any
exception into a catchable ``[EXTERN ERROR]``. Invalid input therefore raises
``ValueError`` with a short, actionable message.

Unicode note: Powang strings are Python ``str`` values, so ``size``,
``char_code``, ``from_char_code`` and slicing operate on Unicode code points,
not UTF-8 bytes.
"""

from typing import Any


def _require_text(value: Any, argument: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{argument} must be a string, got {type(value).__name__}")
    return value


def _require_int(value: Any, argument: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{argument} must be an integer, got {type(value).__name__}")
    return value


def trim(text: str) -> str:
    """Strip leading and trailing whitespace."""
    return _require_text(text, "text").strip()


def upper(text: str) -> str:
    """Return the text in upper case."""
    return _require_text(text, "text").upper()


def lower(text: str) -> str:
    """Return the text in lower case."""
    return _require_text(text, "text").lower()


def replace(text: str, old: str, new: str) -> str:
    """Replace every occurrence of ``old`` with ``new``."""
    return _require_text(text, "text").replace(
        _require_text(old, "old"),
        _require_text(new, "new"),
    )


def contains(text: str, sub: str) -> bool:
    """Report whether ``sub`` occurs in ``text``."""
    return _require_text(sub, "sub") in _require_text(text, "text")


def starts_with(text: str, prefix: str) -> bool:
    """Report whether ``text`` starts with ``prefix``."""
    return _require_text(text, "text").startswith(_require_text(prefix, "prefix"))


def ends_with(text: str, suffix: str) -> bool:
    """Report whether ``text`` ends with ``suffix``."""
    return _require_text(text, "text").endswith(_require_text(suffix, "suffix"))


def slice(text: str, start: int, end: int) -> str:
    """Return ``text[start:end]`` with Python-style negative indices.

    Both bounds are clamped to the string length. An inverted range yields the
    empty string instead of raising.
    """
    text = _require_text(text, "text")
    start = _require_int(start, "start")
    end = _require_int(end, "end")
    length = len(text)
    if start < 0:
        start = max(length + start, 0)
    else:
        start = min(start, length)
    if end < 0:
        end = max(length + end, 0)
    else:
        end = min(end, length)
    if end < start:
        end = start
    return text[start:end]


def split(text: str, sep: str) -> list[str]:
    """Split ``text`` on ``sep`` and return the parts.

    An empty separator raises ``ValueError``; Python's own behaviour of
    splitting into single characters is surprising for a string module.
    """
    text = _require_text(text, "text")
    sep = _require_text(sep, "sep")
    if sep == "":
        raise ValueError("sep must not be empty")
    return text.split(sep)


def join(items: list, sep: str) -> str:
    """Join an array of strings with ``sep``."""
    if not isinstance(items, (list, tuple)):
        raise ValueError(f"items must be an array, got {type(items).__name__}")
    sep = _require_text(sep, "sep")
    parts: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise ValueError(
                f"items[{index}] must be a string, got {type(item).__name__}"
            )
        parts.append(item)
    return sep.join(parts)


def repeat(text: str, count: int) -> str:
    """Repeat ``text`` ``count`` times. ``count`` must not be negative."""
    text = _require_text(text, "text")
    count = _require_int(count, "count")
    if count < 0:
        raise ValueError(f"count must not be negative, got {count}")
    return text * count


def _require_fill(fill: str) -> str:
    fill = _require_text(fill, "fill")
    if len(fill) != 1:
        raise ValueError(f"fill must be exactly one character, got {len(fill)}")
    return fill


def pad_left(text: str, width: int, fill: str = " ") -> str:
    """Pad ``text`` on the left up to ``width`` characters."""
    return _require_text(text, "text").rjust(
        _require_int(width, "width"),
        _require_fill(fill),
    )


def pad_right(text: str, width: int, fill: str = " ") -> str:
    """Pad ``text`` on the right up to ``width`` characters."""
    return _require_text(text, "text").ljust(
        _require_int(width, "width"),
        _require_fill(fill),
    )


def char_code(char: str) -> int:
    """Return the Unicode code point of a single-character string."""
    char = _require_text(char, "char")
    if len(char) != 1:
        raise ValueError(f"char must be exactly one character, got {len(char)}")
    return ord(char)


def from_char_code(code: int) -> str:
    """Return the character for a Unicode code point."""
    code = _require_int(code, "code")
    try:
        return chr(code)
    except (ValueError, OverflowError):
        raise ValueError(f"code is not a valid Unicode code point: {code}") from None


def parse_int(text: str) -> int:
    """Parse a base-10 integer, raising ``ValueError`` on garbage."""
    text = _require_text(text, "text")
    try:
        return int(text.strip(), 10)
    except ValueError:
        raise ValueError(f"not a valid integer: {text!r}") from None


def parse_number(text: str) -> float:
    """Parse a floating-point number, raising ``ValueError`` on garbage."""
    text = _require_text(text, "text")
    try:
        return float(text.strip())
    except ValueError:
        raise ValueError(f"not a valid number: {text!r}") from None


def format_number(value: float, decimals: int) -> str:
    """Format ``value`` with a fixed number of decimal places."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"value must be a number, got {type(value).__name__}")
    decimals = _require_int(decimals, "decimals")
    if decimals < 0:
        raise ValueError(f"decimals must not be negative, got {decimals}")
    return f"{float(value):.{decimals}f}"
