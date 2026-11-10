"""Value tags, constant conversion and deterministic JSON for the VM.

The VM reuses the existing `PowangAny` value model from `src.powang_types`.
This module provides the small amount of policy that sits between that model
and the bytecode format: the tag of a value, truthiness, constant conversion,
stable keys for constant deduplication and a deterministic JSON codec for AST
nodes and descriptor constants.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from ..error import (
    powang_error_type_match,
    powang_throw,
)
from ..lexer.token import LexerTokenType, ParserTokenType
from ..powang_types import (
    PowangAny,
    PowangAnyType,
    PowangArray,
    PowangBoolean,
    PowangChar,
    PowangCopyConstruct,
    PowangInteger,
    PowangMap,
    PowangNova,
    PowangNumber,
    PowangSet,
    PowangString,
    PowangTuple,
    PowangTypeBase,
    PowangUnwrapAny,
)


TAGS: dict[str, str] = {
    "nova": "nova",
    "undef": "undef",
    "bool": "bool",
    "int": "int",
    "num": "num",
    "char": "char",
    "str": "str",
    "arr": "arr",
    "tup": "tup",
    "map": "map",
    "set": "set",
    "function": "fun",
    "object": "object",
    "obj": "obj",
    "module": "module",
    "task": "task",
    "error": "error",
    "reference": "ref",
    "ref": "ref",
    "handle": "handle",
    "file": "handle",
    "Project": "project",
    "project": "project",
    "any": "any",
}

_ENUM_TYPES: dict[str, type[Enum]] = {
    LexerTokenType.__name__: LexerTokenType,
    ParserTokenType.__name__: ParserTokenType,
}


def tag_of(value: PowangAny) -> str:
    """Return the contract tag name for `value`."""
    if value.type == PowangAnyType.type and not getattr(value, "defined", True):
        return "undef"
    return TAGS.get(value.type, "any")


def truthy(value: PowangAny) -> bool:
    """Return the language truth value, using the existing cast rules."""
    return bool(PowangBoolean.cast(value).data)


def is_nova(value: PowangAny) -> bool:
    """Return true when `value` is the absence value."""
    return value.type == PowangNova.type


def is_defined(value: PowangAny) -> bool:
    """Return true when `value` is not the undefined marker."""
    return bool(getattr(value, "defined", True))


def is_weak(value: PowangAny) -> bool:
    """Return true when `value` carries the weak flag."""
    return bool(getattr(value, "weak", False))


def nova() -> PowangNova:
    """Create a fresh nova value."""
    return PowangNova()


def copy_value(value: PowangAny) -> PowangAny:
    """Apply the language copy constructor to `value`."""
    return PowangCopyConstruct(value)


def unwrap(value: PowangAny) -> PowangAny:
    """Return the concrete payload of a gradual or union `any` value."""
    return PowangUnwrapAny(value)


def _plain_to_value(value: Any) -> PowangAny:
    if isinstance(value, PowangTypeBase):
        return value
    if value is None:
        return PowangNova()
    if isinstance(value, bool):
        return PowangBoolean(value)
    if isinstance(value, int):
        return PowangInteger(value)
    if isinstance(value, float):
        return PowangNumber(value)
    if isinstance(value, str):
        return PowangString(value)
    if isinstance(value, (list, tuple)):
        return PowangTuple([_plain_to_value(item) for item in value])
    raise ValueError(f"unsupported constant value: {type(value).__name__}")


def constant_to_value(constant: Any) -> PowangAny:
    """Convert a `Constant` into a runtime value.

    Supported kinds are nova, bool, int, bigint, num, char, str and tuple of
    constants. Other kinds are the responsibility of the interpreter, so this
    helper raises `ValueError` for them.
    """
    kind = constant.kind
    value = constant.value
    if kind == "nova":
        return PowangNova()
    if kind == "bool":
        return PowangBoolean(bool(value))
    if kind in {"int", "bigint"}:
        return PowangInteger(int(value))
    if kind == "num":
        return PowangNumber(float(value))
    if kind == "char":
        if isinstance(value, str):
            return PowangChar(value)
        return PowangChar(chr(int(value)))
    if kind == "str":
        return PowangString(str(value))
    if kind == "tuple":
        items: list[PowangAny] = []
        for item in value:
            if hasattr(item, "kind") and hasattr(item, "value"):
                items.append(constant_to_value(item))
            else:
                items.append(_plain_to_value(item))
        return PowangTuple(items)
    raise ValueError(f"unsupported constant kind: {kind}")


def value_to_constant_kind(value: PowangAny) -> str | None:
    """Return the constant kind for `value` or `None` when it has none."""
    if value.type == PowangNova.type:
        return "nova"
    if value.type == PowangBoolean.type:
        return "bool"
    if value.type == PowangInteger.type:
        data = int(value.data)
        if -(1 << 63) <= data <= (1 << 63) - 1:
            return "int"
        return "bigint"
    if value.type == PowangNumber.type:
        return "num"
    if value.type == PowangChar.type:
        return "char"
    if value.type == PowangString.type:
        return "str"
    if value.type == PowangTuple.type:
        return "tuple"
    return None


def value_to_constant(value: PowangAny) -> Any:
    """Convert a runtime value into a `Constant`.

    Raises `ValueError` for values without a constant representation.
    """
    from .image import Constant

    kind = value_to_constant_kind(value)
    if kind is None:
        raise ValueError(f"value of type {value.type} has no constant form")
    if kind == "nova":
        return Constant("nova", None)
    if kind == "bool":
        return Constant("bool", bool(value.data))
    if kind in {"int", "bigint"}:
        return Constant(kind, int(value.data))
    if kind == "num":
        return Constant("num", float(value.data))
    if kind == "char":
        data = value.data
        if isinstance(data, str):
            return Constant("char", ord(data))
        return Constant("char", int(data))
    if kind == "str":
        return Constant("str", str(value.data))
    if kind == "tuple":
        return Constant("tuple", tuple(value_to_constant(item) for item in value.data))
    raise ValueError(f"value of type {value.type} has no constant form")


def _enum_text(value: Enum) -> str:
    return f"{type(value).__name__}.{value.name}"


def _resolve_enum(text: str) -> Enum:
    if "." not in text:
        raise ValueError(f"invalid enum reference: {text}")
    type_name, member_name = text.split(".", 1)
    enum_type = _ENUM_TYPES.get(type_name)
    if enum_type is None:
        raise ValueError(f"unknown enum type in constant JSON: {type_name}")
    try:
        return enum_type[member_name]
    except KeyError as exc:
        raise ValueError(f"unknown enum member in constant JSON: {text}") from exc


def _encode_powang(value: PowangTypeBase) -> Any:
    tag = tag_of(value)  # type: ignore[arg-type]
    if tag == "nova":
        return {"$powang": "nova"}
    if tag == "bool":
        return {"$powang": "bool", "value": bool(value.data)}
    if tag == "int":
        return {"$powang": "int", "value": int(value.data)}
    if tag == "num":
        return {"$powang": "num", "value": float(value.data)}
    if tag == "char":
        data = value.data
        return {"$powang": "char", "value": ord(data) if isinstance(data, str) else int(data)}
    if tag == "str":
        return {"$powang": "str", "value": str(value.data)}
    if tag in {"arr", "tup"}:
        return {"$powang": tag, "value": [_encode(item) for item in value.data]}
    if tag == "map":
        return {
            "$powang": "map",
            "value": [[_encode(key), _encode(item)] for key, item in value.data.items()],
        }
    if tag == "set":
        return {"$powang": "set", "value": [_encode(item) for item in value.data.keys()]}
    if tag == "any":
        data = value.data
        return {
            "$powang": "any",
            "value": _encode(data) if isinstance(data, PowangTypeBase) else data,
            "defined": bool(getattr(value, "defined", True)),
            "any": getattr(value, "any", ""),
        }
    raise TypeError(f"cannot encode value of type {value.type} as constant JSON")


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return {"$enum": _enum_text(value)}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: _encode(item) for key, item in value.items()}
        return {
            "$dict": [[_encode(key), _encode(item)] for key, item in value.items()],
        }
    if isinstance(value, PowangTypeBase):
        return _encode_powang(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, set):
        raise TypeError("sets are not supported in constant JSON")
    raise TypeError(f"cannot encode {type(value).__name__} as constant JSON")


def _decode_powang(value: dict[str, Any]) -> PowangAny:
    tag = value["$powang"]
    if tag == "nova":
        return PowangNova()
    if tag == "bool":
        return PowangBoolean(bool(value["value"]))
    if tag == "int":
        return PowangInteger(int(value["value"]))
    if tag == "num":
        return PowangNumber(float(value["value"]))
    if tag == "char":
        return PowangChar(chr(int(value["value"])))
    if tag == "str":
        return PowangString(str(value["value"]))
    if tag in {"arr", "tup"}:
        items = [_decode(item) for item in value["value"]]
        return PowangArray(items) if tag == "arr" else PowangTuple(items)
    if tag == "map":
        return PowangMap({_decode(key): _decode(item) for key, item in value["value"]})
    if tag == "set":
        return PowangSet([_decode(item) for item in value["value"]])
    if tag == "any":
        result = PowangAnyType(0)
        raw = value.get("value")
        result.data = _decode(raw) if isinstance(raw, (dict, list, tuple)) else raw
        result.defined = bool(value.get("defined", True))
        result.any = str(value.get("any", ""))
        return result
    raise ValueError(f"unknown powang constant kind: {tag}")


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        keys = set(value.keys())
        if keys == {"$enum"}:
            return _resolve_enum(str(value["$enum"]))
        if keys == {"$tuple"}:
            return tuple(_decode(item) for item in value["$tuple"])
        if keys == {"$set"}:
            return set(_decode(item) for item in value["$set"])
        if keys == {"$dict"}:
            return {
                _decode(key): _decode(item)
                for key, item in value["$dict"]
            }
        if keys == {"$powang"} or "$powang" in keys:
            return _decode_powang(value)
        return {key: _decode(item) for key, item in value.items()}
    return value


def encode_constant_json(value: Any) -> str:
    """Encode an AST node, type node or descriptor deterministically.

    Enum objects become `{"$enum": "Type.NAME"}`. Tuples become
    `{"$tuple": [...]}`. A dictionary with non-string keys, including enum
    keys, becomes `{"$dict": [[key, value], ...]}` so JSON object keys stay
    strings.
    """
    return json.dumps(
        _encode(value),
        ensure_ascii=True,
        allow_nan=True,
        separators=(",", ":"),
    )


def decode_constant_json(text: str) -> Any:
    """Decode text produced by `encode_constant_json`."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid constant JSON: {exc}") from exc
    return _decode(raw)


def _canonical(value: Any) -> Any:
    import dataclasses

    from .image import Constant

    if isinstance(value, Constant):
        return {"$constant": value.kind, "value": _canonical(value.value)}
    if isinstance(value, Enum):
        return {"$enum": _enum_text(value)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {
            field.name: _canonical(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
        return {
            "$dataclass": type(value).__name__,
            "fields": fields,
        }
    if isinstance(value, tuple):
        return {"$tuple": [_canonical(item) for item in value]}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, dict):
        pairs = [[_canonical(key), _canonical(item)] for key, item in value.items()]
        pairs.sort(key=lambda pair: json.dumps(pair[0], sort_keys=True, separators=(",", ":")))
        return {"$dict": pairs}
    if isinstance(value, PowangTypeBase):
        return _canonical(_encode_powang(value))
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"cannot build a stable key for {type(value).__name__}")


def stable_key(value: Any) -> str:
    """Return a deterministic key for structural constant deduplication."""
    return json.dumps(
        _canonical(value),
        ensure_ascii=True,
        allow_nan=True,
        sort_keys=True,
        separators=(",", ":"),
    )


class SpreadValue:
    """A value marked for argument spreading by the call binder."""

    __slots__ = ("value",)

    def __init__(self, value: PowangAny) -> None:
        self.value = value

    def __repr__(self) -> str:
        return f"SpreadValue({self.value!r})"


def spread_values(value: PowangAny) -> list[PowangAny]:
    """Expand a spreadable value into its argument list.

    Strings expand to characters, maps expand to key-value tuples and arrays,
    tuples and sets expand to their members. Any other value raises the same
    language error the tree walker raises.
    """
    if isinstance(value, SpreadValue):
        value = value.value
    if value.type == PowangArray.type:
        return list(value.data)
    if value.type == PowangTuple.type:
        return list(value.data)
    if value.type == PowangSet.type:
        return list(value.data.keys())
    if value.type == PowangMap.type:
        return [PowangTuple([key, item]) for key, item in value.data.items()]
    if value.type == PowangString.type:
        return [PowangChar(character) for character in value.data]
    raise powang_throw(
        powang_error_type_match(
            "spread",
            f"{PowangArray.type}, {PowangTuple.type}, {PowangSet.type}, "
            f"{PowangMap.type} or {PowangString.type}",
            value.type,
        )
    )
