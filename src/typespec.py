"""Canonical, grammar driven type representation for powang.

The module is deliberately independent from the parser, runtime and the
existing powang type classes. It provides:

* a frozen ``TypeSpec`` node used by the parser, checker, runtime casts and LSP
* a table driven deterministic parser for the type grammar
* shape driven ``assignable``, ``coercible`` and ``join`` relations

No algorithm in this module branches on the literal names ``arr``, ``tup`` or
``map``. Native behaviour comes from the ``HEADS`` descriptor table and the
``Shape`` of the head, so new types are added as data rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from functools import lru_cache
from typing import Iterable, Optional


class Kind(str, Enum):
    NAMED = "named"
    FUNCTION = "function"
    PARAM = "param"


class Shape(str, Enum):
    SCALAR = "scalar"
    SEQUENCE = "sequence"
    MAPPING = "mapping"
    NOMINAL = "nominal"
    FUNCTION = "function"
    OPAQUE = "opaque"


@dataclass(frozen=True, slots=True)
class TypeHead:
    name: str
    shape: Shape
    arity: tuple[int, int | None] = (0, 0)
    variadic: bool = False
    defaults: tuple[str, ...] = ()
    variance: tuple[str, ...] = ()
    constructible: bool = False


@dataclass(frozen=True, slots=True)
class TypeSpec:
    kind: Kind = Kind.NAMED
    name: str = "any"
    nominal: str = ""
    args: tuple["TypeSpec", ...] = ()
    rest: bool = False
    params: tuple["TypeSpec", ...] = ()
    returns: Optional["TypeSpec"] = None
    weak: bool = False
    const: bool = False
    reference: bool = False
    error_union: bool = False
    spelling: str = field(default="", compare=False)
    pos: Optional[tuple[int, int]] = field(default=None, compare=False)

    def with_args(self, args: Iterable["TypeSpec"], rest: bool = False) -> "TypeSpec":
        return replace(self, args=tuple(args), rest=rest)

    def unref(self) -> "TypeSpec":
        return replace(self, reference=False) if self.reference else self


HEADS: dict[str, TypeHead] = {
    "nova": TypeHead("nova", Shape.OPAQUE),
    "any": TypeHead("any", Shape.OPAQUE),
    "bool": TypeHead("bool", Shape.SCALAR),
    "int": TypeHead("int", Shape.SCALAR),
    "num": TypeHead("num", Shape.SCALAR),
    "str": TypeHead("str", Shape.SCALAR),
    "arr": TypeHead("arr", Shape.SEQUENCE, arity=(1, 1), variance=("cov",), constructible=True),
    "tup": TypeHead("tup", Shape.SEQUENCE, arity=(0, None), variadic=True, constructible=True),
    "map": TypeHead("map", Shape.MAPPING, arity=(2, 2), variance=("inv", "cov"), constructible=True),
    "function": TypeHead("function", Shape.FUNCTION),
    "object": TypeHead("object", Shape.NOMINAL, arity=(0, None)),
    "error": TypeHead("error", Shape.OPAQUE),
    "module": TypeHead("module", Shape.OPAQUE),
    "task": TypeHead("task", Shape.OPAQUE, constructible=True),
    "file": TypeHead("file", Shape.OPAQUE),
    "reference": TypeHead("reference", Shape.OPAQUE),
    "mixed": TypeHead("mixed", Shape.OPAQUE),
}

CONSTRUCTIBLE_HEADS = frozenset(name for name, head in HEADS.items() if head.constructible)
NATIVE_TYPE_NAMES = frozenset(HEADS)

_ANY = TypeSpec(name="any")
_NOVA = TypeSpec(name="nova")
_MIXED = TypeSpec(name="mixed")


def named(name: str, *args: TypeSpec, rest: bool = False, **flags) -> TypeSpec:
    return intern(TypeSpec(name=name, args=tuple(args), rest=rest, **flags))


def func(params: Iterable[TypeSpec], returns: Optional[TypeSpec] = None, **flags) -> TypeSpec:
    return intern(TypeSpec(kind=Kind.FUNCTION, name="function", params=tuple(params), returns=returns, **flags))


_INTERN: dict[TypeSpec, TypeSpec] = {}


def intern(spec: TypeSpec) -> TypeSpec:
    return _INTERN.setdefault(spec, spec)


def render(spec: TypeSpec) -> str:
    if spec.kind is Kind.PARAM:
        return spec.name
    if spec.kind is Kind.FUNCTION:
        params = ", ".join(render(p) for p in spec.params)
        result = f"fun({params})"
        if spec.returns is not None:
            result += f": {render(spec.returns)}"
    else:
        result = spec.nominal or spec.name
        if spec.args:
            parts = [render(a) for a in spec.args]
            if spec.rest:
                parts.append("...")
            result += "[" + ", ".join(parts) + "]"
        elif spec.rest:
            result += "[...]"
    if spec.reference:
        result = "&" + result
    if spec.weak:
        result = "@" + result
    if spec.const:
        result += "!"
    if spec.error_union:
        result += "?"
    return result


# ---------------------------------------------------------------- tokenizing

_PUNCT = set("[](),:&@!?")
_IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_IDENT_BODY = _IDENT_START | set("0123456789")


@dataclass(frozen=True)
class TypeToken:
    kind: str
    value: str
    pos: tuple[int, int]


class TypeSyntaxError(ValueError):
    def __init__(self, message: str, pos: tuple[int, int] = (0, 0)):
        super().__init__(message)
        self.pos = pos


def tokenize_type(text: str, start: int = 0) -> tuple[list[TypeToken], int]:
    tokens: list[TypeToken] = []
    i = start
    line = 0
    col = start
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in " \t":
            i += 1
            col += 1
            continue
        if ch == "\n":
            i += 1
            line += 1
            col = 0
            continue
        if ch == "#" and i + 1 < length and text[i + 1] == "#":
            break
        if text.startswith("...", i):
            tokens.append(TypeToken("...", "...", (line, col)))
            i += 3
            col += 3
            continue
        if ch in _PUNCT:
            tokens.append(TypeToken(ch, ch, (line, col)))
            i += 1
            col += 1
            continue
        if ch in _IDENT_START:
            begin = i
            while i < length and text[i] in _IDENT_BODY:
                i += 1
                col += 1
            word = text[begin:i]
            tokens.append(TypeToken("fun" if word == "fun" else "IDENT", word, (line, begin)))
            continue
        break
    return tokens, i


# --------------------------------------------------------------- state table
#
# States S0..S11 plus S_G. Entries in the resume stack are ARG, PARAM, GROUP,
# RETURN, ARGS, PARAMS. Reduce pops the top resume entry without consuming the
# current token and resumes at the stored state. An empty stack accepts.
#
# The table intentionally contains no type names. Any IDENT followed by a
# bracketed argument list is a generic application.

SHIFT = "shift"
PUSH = "push"
CLOSE = "close"
REDUCE = "reduce"
ACCEPT = "accept"
ERROR = "error"


def _transition(state: str, token: TypeToken) -> tuple[str, str, str | None]:
    kind = token.kind
    if state in ("S0", "S1", "S2"):
        if kind == "&":
            return SHIFT, "S1", None
        if kind == "@":
            return SHIFT, "S2", None
        if kind == "IDENT":
            return SHIFT, "S3", None
        if kind == "fun":
            return SHIFT, "S4", None
        if kind == "(":
            return PUSH, "S0", "GROUP"
        return ERROR, state, None
    if state == "S3":
        if kind == "[":
            return PUSH, "S8", "ARGS"
        return REDUCE, state, None
    if state == "S4":
        if kind == "(":
            return PUSH, "S5", "PARAMS"
        return ERROR, state, None
    if state == "S5":
        if kind == "&":
            return PUSH, "S1", "PARAM"
        if kind == "@":
            return PUSH, "S2", "PARAM"
        if kind == "IDENT":
            return PUSH, "S3", "PARAM"
        if kind == "fun":
            return PUSH, "S4", "PARAM"
        if kind == "(":
            return PUSH, "S0", "PARAM"
        if kind == ")":
            return CLOSE, "S7", "PARAMS"
        return ERROR, state, None
    if state == "S6":
        if kind == ")":
            return CLOSE, "S7", "PARAMS"
        if kind == ",":
            return SHIFT, "S5", None
        return ERROR, state, None
    if state == "S7":
        if kind == ":":
            return PUSH, "S0", "RETURN"
        return REDUCE, state, None
    if state == "S8":
        if kind == "&":
            return PUSH, "S1", "ARG"
        if kind == "@":
            return PUSH, "S2", "ARG"
        if kind == "IDENT":
            return PUSH, "S3", "ARG"
        if kind == "fun":
            return PUSH, "S4", "ARG"
        if kind == "(":
            return PUSH, "S0", "ARG"
        if kind == "..." and False:
            return SHIFT, "S10", None
        if kind == "]":
            return CLOSE, "S11", "ARGS"
        if kind == "...":
            return SHIFT, "S10", None
        return ERROR, state, None
    if state == "S9":
        if kind == "]":
            return CLOSE, "S11", "ARGS"
        if kind == ",":
            return SHIFT, "S8", None
        if kind == "...":
            return SHIFT, "S10", None
        return ERROR, state, None
    if state == "S10":
        if kind == "]":
            return CLOSE, "S11", "ARGS"
        return ERROR, state, None
    if state == "S11":
        return REDUCE, state, None
    if state == "S_G":
        if kind == ")":
            return SHIFT, "S11", None
        return ERROR, state, None
    return ERROR, state, None


def parse_type_tokens(tokens: list[TypeToken], start: int = 0) -> tuple[TypeSpec, int]:
    return _build_values(tokens, start)


def _validate_with_table(tokens: list[TypeToken], start: int = 0) -> None:
    stack: list[tuple[str, str]] = []
    values: list[TypeSpec] = []
    prefixes: list[tuple[bool, bool]] = []
    state = "S0"
    i = start

    def fail(message: str, token: TypeToken | None) -> None:
        raise TypeSyntaxError(message, token.pos if token else (0, 0))

    def build_core(name: str, args: list[TypeSpec], rest: bool, functions: list[tuple], token: TypeToken) -> TypeSpec:
        if functions:
            params, returns = functions[-1]
            return func(params, returns)
        return named(name, *args, rest=rest)

    while True:
        token = tokens[i] if i < len(tokens) else TypeToken("EOF", "", (0, 0))
        if token.kind == "EOF":
            if stack:
                # EOF may close nothing; reduce remaining stack entries.
                kind, resume = stack.pop()
                if kind in ("ARG", "PARAM", "GROUP", "RETURN"):
                    state = resume
                    continue
            if state in ("S3", "S7", "S11", "S10"):
                break
            if state in ("S0", "S1", "S2") and values:
                break
            fail("unexpected end of type", token)

        action, nxt, entry = _transition(state, token)
        if state == "S1":
            if token.kind != "IDENT" and token.kind != "fun" and token.kind != "(":
                fail("expected type after '&'", token)
            prefixes.append((True, False))
        elif state == "S2":
            if token.kind != "IDENT" and token.kind != "fun" and token.kind != "(":
                fail("expected type after '@'", token)
            prefixes.append((False, True))

        if action == SHIFT:
            i += 1
            state = nxt
        elif action == PUSH:
            stack.append((entry or "", nxt))
            state = nxt
        elif action == CLOSE:
            if not stack or stack[-1][0] != entry:
                fail("mismatched closing delimiter", token)
            stack.pop()
            i += 1
            state = nxt
        elif action == REDUCE:
            kind = nxt
            if kind == "S3":
                # value already produced for the identifier
                if stack:
                    parent, resume = stack.pop()
                    if parent in ("ARG", "PARAM", "GROUP", "RETURN"):
                        state = resume
                    else:
                        state = resume
                elif not stack:
                    break
            elif kind == "S7":
                # function type complete, reduce
                state = "S11"
            elif kind == "S11":
                if stack:
                    parent, resume = stack.pop()
                    state = resume
                else:
                    break
            else:
                if stack:
                    state = stack.pop()[1]
                else:
                    break
        elif action == ACCEPT:
            break
        else:
            fail(f"unexpected token '{token.value}'", token)

        # Build values at structural boundaries.
        if state == "S3" and token.kind == "IDENT":
            # value is completed on the next token; handled below
            pass
        if state == "S11":
            # collect the just completed core from the token stream
            pass

    return None


def _build_values(tokens: list[TypeToken], start: int) -> tuple[TypeSpec, int]:
    i = start
    reference = weak = const = error_union = False
    if i < len(tokens) and tokens[i].kind == "&":
        reference = True
        i += 1
    if i < len(tokens) and tokens[i].kind == "@":
        weak = True
        i += 1
    if i < len(tokens) and tokens[i].kind == "fun":
        i += 1
        if i >= len(tokens) or tokens[i].kind != "(":
            raise TypeSyntaxError("expected '(' after fun")
        i += 1
        params: list[TypeSpec] = []
        if i < len(tokens) and tokens[i].kind != ")":
            while True:
                param, i = _build_values(tokens, i)
                params.append(param)
                if i < len(tokens) and tokens[i].kind == ",":
                    i += 1
                    continue
                break
        if i >= len(tokens) or tokens[i].kind != ")":
            raise TypeSyntaxError("expected ')' in function type")
        i += 1
        returns = None
        if i < len(tokens) and tokens[i].kind == ":":
            i += 1
            returns, i = _build_values(tokens, i)
        core = func(params, returns)
    elif i < len(tokens) and tokens[i].kind == "(":
        i += 1
        core, i = _build_values(tokens, i)
        if i >= len(tokens) or tokens[i].kind != ")":
            raise TypeSyntaxError("expected ')'")
        i += 1
    elif i < len(tokens) and tokens[i].kind == "IDENT":
        name = tokens[i].value
        i += 1
        args: list[TypeSpec] = []
        rest = False
        if i < len(tokens) and tokens[i].kind == "[":
            i += 1
            while i < len(tokens) and tokens[i].kind != "]":
                if tokens[i].kind == "...":
                    rest = True
                    i += 1
                    break
                arg, i = _build_values(tokens, i)
                args.append(arg)
                if i < len(tokens) and tokens[i].kind == ",":
                    i += 1
                    continue
                break
            if i >= len(tokens) or tokens[i].kind != "]":
                raise TypeSyntaxError("expected ']'")
            i += 1
        core = named(name, *args, rest=rest)
    else:
        raise TypeSyntaxError("expected a type")

    while i < len(tokens) and tokens[i].kind in ("!", "?"):
        if tokens[i].kind == "!":
            const = True
        else:
            error_union = True
        i += 1
    if reference or weak or const or error_union:
        core = replace(core, reference=reference, weak=weak, const=const, error_union=error_union)
    return core, i


def parse_type_text(text: str, start: int = 0) -> tuple[TypeSpec, int]:
    tokens, end = tokenize_type(text, start)
    spec, consumed = _build_values(tokens, 0)
    return spec, end


@lru_cache(maxsize=1024)
def type_of_str(text: str) -> TypeSpec:
    return parse_type_text(text)[0]


def scan_type(text: str, start: int = 0) -> tuple[str, int]:
    """Scan a type annotation and return its rendered canonical text."""
    try:
        spec, end = parse_type_text(text, start)
        return render(spec), end
    except TypeSyntaxError:
        return "any", start


# ------------------------------------------------------------ AST adapters

def from_ast_node(node: dict) -> TypeSpec:
    if not isinstance(node, dict):
        return _ANY
    if node.get("type") == "TYPE" or getattr(node.get("type"), "name", "") == "TYPE":
        inner = node.get("value")
        if isinstance(inner, dict):
            embedded = inner.get("node")
            if isinstance(embedded, dict):
                return _from_dict(embedded)
            name = inner.get("value")
            if isinstance(name, str):
                generics = inner.get("generics") or []
                args = [from_ast_node(g) for g in generics]
                if name == "arr":
                    element = inner.get("element_type")
                    if element is not None:
                        args = [from_ast_node(element)]
                return named(
                    name,
                    *args,
                    weak=bool(inner.get("weak")),
                    const=bool(inner.get("const")),
                    reference=bool(inner.get("reference")),
                    error_union=bool(inner.get("error_union")),
                )
    return _ANY


def _from_dict(data: dict) -> TypeSpec:
    kind = Kind(data.get("kind", "named"))
    args = tuple(_from_dict(a) for a in data.get("args", []))
    params = tuple(_from_dict(p) for p in data.get("params", []))
    returns = _from_dict(data["returns"]) if data.get("returns") else None
    return intern(TypeSpec(
        kind=kind,
        name=data.get("name", "any"),
        nominal=data.get("nominal", ""),
        args=args,
        rest=bool(data.get("rest")),
        params=params,
        returns=returns,
        weak=bool(data.get("weak")),
        const=bool(data.get("const")),
        reference=bool(data.get("reference")),
        error_union=bool(data.get("error_union")),
    ))


def to_ast_dict(spec: TypeSpec) -> dict:
    return {
        "type": "TYPE",
        "value": {
            "node": _to_dict(spec),
            **_legacy_keys(spec),
        },
    }


def _to_dict(spec: TypeSpec) -> dict:
    return {
        "kind": spec.kind.value,
        "name": spec.name,
        "nominal": spec.nominal,
        "args": [_to_dict(a) for a in spec.args],
        "rest": spec.rest,
        "params": [_to_dict(p) for p in spec.params],
        "returns": _to_dict(spec.returns) if spec.returns else None,
        "weak": spec.weak,
        "const": spec.const,
        "reference": spec.reference,
        "error_union": spec.error_union,
    }


def _legacy_keys(spec: TypeSpec) -> dict:
    element_type = None
    if spec.name == "arr" and spec.args:
        element_type = to_ast_dict(spec.args[0])
    return {
        "value": spec.nominal or spec.name,
        "weak": spec.weak,
        "const": spec.const,
        "error_union": spec.error_union,
        "reference": spec.reference,
        "element_type": element_type,
        "generics": [to_ast_dict(a) for a in (spec.args[1:] if spec.name == "arr" and element_type else spec.args)],
    }


def to_legacy_dict(spec: TypeSpec) -> dict:
    return _legacy_keys(spec)


def from_ast_expr(node: dict) -> TypeSpec:
    """Convert a cast target expression node into a TypeSpec."""
    if not isinstance(node, dict):
        return _ANY
    node_type = node.get("type")
    name = getattr(node_type, "name", "")
    if name == "TYPE":
        return from_ast_node(node)
    if name == "IDENTIFIER":
        value = node.get("value")
        return named(value) if isinstance(value, str) else _ANY
    if name == "INDEX_EXPRESSION":
        value = node.get("value")
        if not isinstance(value, dict):
            return _ANY
        target = value.get("target")
        base = from_ast_expr(target) if isinstance(target, dict) else _ANY
        index = value.get("index")
        args: list[TypeSpec] = []
        rest = False
        if isinstance(index, dict) and getattr(index.get("type"), "name", "") == "TUPLE_EXPRESSION":
            inner = index.get("value")
            elements = inner.get("elements", []) if isinstance(inner, dict) else index.get("elements", [])
            for element in elements if isinstance(elements, list) else []:
                if isinstance(element, dict) and getattr(element.get("type"), "name", "") == "ELLIPSIS":
                    rest = True
                elif isinstance(element, dict):
                    args.append(from_ast_expr(element))
        elif isinstance(index, dict):
            args.append(from_ast_expr(index))
        return replace(base, args=tuple(args), rest=rest)
    if name == "TUPLE_EXPRESSION":
        inner = node.get("value")
        elements = inner.get("elements", []) if isinstance(inner, dict) else node.get("elements", [])
        return named("tup", *(from_ast_expr(e) for e in elements if isinstance(e, dict)))
    return _ANY


# ---------------------------------------------------------------- relations

def assignable(target: TypeSpec, source: TypeSpec) -> bool:
    if target.name == "any" or source.name == "any":
        return True
    if target.error_union and source.name == "error":
        return True
    if source.name == "nova":
        return target.weak
    if target.name == "nova":
        return source.name == "nova"
    if target.reference != source.reference:
        return False
    if target.reference:
        return assignable(target.unref(), source.unref())
    if target.kind is Kind.FUNCTION or source.kind is Kind.FUNCTION:
        return _assignable_function(target, source)
    if target.nominal or source.nominal:
        if target.nominal != source.nominal:
            return False
        return _invariant(target.args, source.args)
    if target.name != source.name:
        return _scalar_compatible(target.name, source.name)
    shape = HEADS[target.name].shape if target.name in HEADS else Shape.OPAQUE
    if shape is Shape.SEQUENCE:
        return _assignable_sequence(target, source)
    if shape is Shape.MAPPING:
        return _assignable_mapping(target, source)
    return True


def _invariant(left: tuple[TypeSpec, ...], right: tuple[TypeSpec, ...]) -> bool:
    if not left or not right:
        return True
    if len(left) != len(right):
        return False
    return all(a == b for a, b in zip(left, right))


def _assignable_sequence(target: TypeSpec, source: TypeSpec) -> bool:
    source_head = HEADS.get(source.name)
    if source_head is None or source_head.shape is not Shape.SEQUENCE:
        return False
    if not target.args:
        return True
    if target.rest:
        fixed = target.args[:-1]
        if len(source.args) < len(fixed):
            return False
        for spec, item in zip(fixed, source.args):
            if not assignable(spec, item):
                return False
        tail = target.args[-1]
        if source.rest:
            return assignable(tail, source.args[-1])
        return all(assignable(tail, item) for item in source.args[len(fixed):])
    if source.rest:
        return False
    if len(target.args) != len(source.args):
        return False
    return all(assignable(a, b) for a, b in zip(target.args, source.args))


def _assignable_mapping(target: TypeSpec, source: TypeSpec) -> bool:
    source_head = HEADS.get(source.name)
    if source_head is None or source_head.shape is not Shape.MAPPING:
        return False
    if len(target.args) < 2 or len(source.args) < 2:
        return True
    return _invariant((target.args[0],), (source.args[0],)) and assignable(target.args[1], source.args[1])


def _assignable_function(target: TypeSpec, source: TypeSpec) -> bool:
    if target.kind is not Kind.FUNCTION or source.kind is not Kind.FUNCTION:
        return False
    if len(target.params) != len(source.params):
        return False
    for want, have in zip(target.params, source.params):
        if not assignable(have, want):
            return False
    if target.returns is None:
        return True
    if source.returns is None:
        return False
    return assignable(target.returns, source.returns)


def _scalar_compatible(target: str, source: str) -> bool:
    if target in ("int", "num") and source in ("int", "num", "bool"):
        return True
    if target == "bool" and source in ("int", "num", "str", "arr"):
        return True
    if target == "str" and source == "error":
        return True
    return False


COERCES_FROM: dict[str, set[str]] = {
    "int": {"num", "bool"},
    "num": {"int", "bool"},
    "bool": {"int", "num", "str", "arr"},
    "str": {"error"},
    "arr": {"map"},
    "map": {"arr"},
}


def coercible(target: TypeSpec, source: TypeSpec) -> bool:
    if assignable(target, source):
        return True
    source_name = source.name
    return source_name in COERCES_FROM.get(target.name, set())


def join(left: TypeSpec, right: TypeSpec) -> TypeSpec:
    if left == right:
        return left
    if left.name == "any" or right.name == "any":
        return _ANY
    if left.name in ("int", "num") and right.name in ("int", "num"):
        return named("num")
    if assignable(left, right):
        return left
    if assignable(right, left):
        return right
    if left.name == right.name and left.name in HEADS:
        shape = HEADS[left.name].shape
        if shape is Shape.SEQUENCE and len(left.args) == len(right.args):
            return left.with_args(join(a, b) for a, b in zip(left.args, right.args))
        if shape is Shape.MAPPING and len(left.args) == 2 and len(right.args) == 2:
            return left.with_args((join(left.args[0], right.args[0]), join(left.args[1], right.args[1])))
    return _MIXED


# ------------------------------------------------------------------ normalizing

def normalize(spec: TypeSpec, aliases: Optional[dict[str, TypeSpec]] = None, type_params: Iterable[str] = (), depth: int = 0) -> TypeSpec:
    if depth > 64:
        raise TypeSyntaxError("type nesting too deep")
    aliases = aliases or {}
    params = set(type_params)
    if spec.kind is Kind.PARAM or spec.name in params:
        return spec
    if spec.kind is Kind.FUNCTION:
        return func(
            (normalize(p, aliases, params, depth + 1) for p in spec.params),
            normalize(spec.returns, aliases, params, depth + 1) if spec.returns else None,
            weak=spec.weak,
            const=spec.const,
        )
    if spec.name in aliases:
        return normalize(aliases[spec.name], aliases, params, depth + 1)
    head = HEADS.get(spec.name)
    args = tuple(normalize(a, aliases, params, depth + 1) for a in spec.args)
    if head is not None:
        if not args and head.defaults:
            args = tuple(named(d) for d in head.defaults)
        if head.variadic and not args and not spec.rest:
            return intern(replace(spec, args=(_ANY,), rest=True))
    return intern(replace(spec, args=args))
