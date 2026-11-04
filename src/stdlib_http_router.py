"""Small path router for the in-process Powang HTTP server (ADR-0001 W29).

The router itself is a plain Powang map returned by :func:`new`. Routes and
middleware live in a process-wide registry keyed by an opaque owner token and a
per-state integer id, so two interpreter states never share a route table even
when both use id ``1``.

The map is deliberately not JSON-serializable: it carries a ``float('nan')``
marker value, which ``json.stringify`` rejects. That keeps a router from being
written to disk or sent through the HTTP client by accident.

Policy:

* supported methods are the ones the server understands
* a pattern must start with ``/`` and may contain ``:name`` segments
* literal routes win over parameter routes when both match a path
* a known path with the wrong method returns ``405``, an unknown path ``404``
* middleware runs in insertion order and may short-circuit with a response map
* handler and middleware errors propagate; the HTTP server turns them into a
  generic ``500`` and logs one diagnostic line
"""

from __future__ import annotations

import math
import threading
import urllib.parse
import uuid
import weakref
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .state import get_state
from .powang_types import PowangTypeBase

SUPPORTED_METHODS: frozenset[str] = frozenset({
    'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS',
})

ROUTER_MARKER: str = '__powang_http_router__'
OWNER_KEY: str = '__owner__'
ID_KEY: str = '__id__'

ROUTER_MARKER_VALUE: float = float('nan')

NOT_FOUND_BODY: str = 'not found'
METHOD_NOT_ALLOWED_BODY: str = 'method not allowed'


@dataclass(frozen=True)
class Route:
    method: str
    pattern: str
    segments: tuple[str, ...]
    param_names: tuple[str, ...]
    handler: Callable
    order: int


@dataclass
class RouterEntry:
    owner: str
    router_id: int
    routes: list[Route] = field(default_factory=list)
    middlewares: list[Callable] = field(default_factory=list)
    next_order: int = 0


_REGISTRY: dict[tuple[str, int], RouterEntry] = {}
_REGISTRY_LOCK = threading.RLock()
_STATE_TOKENS: 'weakref.WeakKeyDictionary[Any, str]' = weakref.WeakKeyDictionary()
_STATE_NEXT_IDS: 'weakref.WeakKeyDictionary[Any, int]' = weakref.WeakKeyDictionary()


# ------------------------------------------------------------------ validation
def _require_router(value: Any) -> RouterEntry:
    if not isinstance(value, dict):
        raise ValueError(
            "http_router: router must be a map created with http_router.new()"
        )
    marker = value.get(ROUTER_MARKER)
    if not isinstance(marker, float) or not math.isnan(marker):
        raise ValueError(
            "http_router: router must be a map created with http_router.new()"
        )
    owner = value.get(OWNER_KEY)
    router_id = value.get(ID_KEY)
    if not isinstance(owner, str) or isinstance(router_id, bool) \
            or not isinstance(router_id, int):
        raise ValueError(
            "http_router: router is missing its registry identity"
        )
    with _REGISTRY_LOCK:
        entry = _REGISTRY.get((owner, router_id))
    if entry is None:
        raise ValueError(
            "http_router: router is not registered in this process"
        )
    return entry


def _require_method(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"http_router: method must be a string, got {type(value).__name__}"
        )
    method = value.strip().upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError(
            f"http_router: unsupported method {value!r}; expected one of "
            f"{', '.join(sorted(SUPPORTED_METHODS))}"
        )
    return method


def _split_path(value: str) -> tuple[str, ...]:
    trimmed = value.strip('/')
    if not trimmed:
        return ()
    return tuple(trimmed.split('/'))


def _compile_pattern(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, str):
        raise ValueError(
            f"http_router: pattern must be a string, got {type(value).__name__}"
        )
    if not value.startswith('/'):
        raise ValueError(
            f"http_router: pattern must start with '/', got {value!r}"
        )
    segments = _split_path(value)
    param_names: list[str] = []
    for segment in segments:
        if segment.startswith(':'):
            name = segment[1:]
            if not name:
                raise ValueError(
                    f"http_router: empty parameter name in pattern {value!r}"
                )
            if name in param_names:
                raise ValueError(
                    f"http_router: duplicate parameter {name!r} in pattern "
                    f"{value!r}"
                )
            param_names.append(name)
    return segments, tuple(param_names)


def _require_callable(value: Any, argument: str) -> Callable:
    if not callable(value):
        raise ValueError(
            f"http_router: {argument} must be a function, got "
            f"{type(value).__name__}"
        )
    return value


def _require_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            f"http_router: request must be a map, got {type(value).__name__}"
        )
    return dict(value)


# ----------------------------------------------------------------------- public
def new() -> dict[str, Any]:
    """Create a router owned by the active interpreter state."""
    state = get_state()
    with _REGISTRY_LOCK:
        owner = _STATE_TOKENS.get(state)
        if owner is None:
            owner = uuid.uuid4().hex
            _STATE_TOKENS[state] = owner
            _STATE_NEXT_IDS[state] = 1
        router_id = _STATE_NEXT_IDS.get(state, 1)
        _STATE_NEXT_IDS[state] = router_id + 1
        entry = RouterEntry(owner=owner, router_id=router_id)
        _REGISTRY[(owner, router_id)] = entry
    return {
        ROUTER_MARKER: ROUTER_MARKER_VALUE,
        OWNER_KEY: owner,
        ID_KEY: router_id,
    }


def add(router: dict, method: str, pattern: str, handler: Any) -> None:
    """Register one handler for a method and path pattern."""
    entry = _require_router(router)
    normalized_method = _require_method(method)
    segments, param_names = _compile_pattern(pattern)
    handler_callable = _require_callable(handler, 'handler')

    with _REGISTRY_LOCK:
        route = Route(
            method=normalized_method,
            pattern=pattern,
            segments=segments,
            param_names=param_names,
            handler=handler_callable,
            order=entry.next_order,
        )
        entry.next_order += 1
        entry.routes.append(route)


def middleware(router: dict, handler: Any) -> None:
    """Append middleware. A middleware returns a response map or ``nova``."""
    entry = _require_router(router)
    middleware_callable = _require_callable(handler, 'middleware')
    with _REGISTRY_LOCK:
        entry.middlewares.append(middleware_callable)


def dispatch(router: dict, request: dict) -> dict:
    """Route one server request map to a handler and return a response map."""
    entry = _require_router(router)
    request_map = _require_request(request)

    raw_method = request_map.get('method', 'GET')
    if not isinstance(raw_method, str):
        raise ValueError(
            f"http_router: request method must be a string, got "
            f"{type(raw_method).__name__}"
        )
    method = raw_method.strip().upper()

    raw_path = request_map.get('path', '/')
    if not isinstance(raw_path, str):
        raise ValueError(
            f"http_router: request path must be a string, got "
            f"{type(raw_path).__name__}"
        )
    path_segments = tuple(
        urllib.parse.unquote(segment)
        for segment in _split_path(raw_path)
    )

    with _REGISTRY_LOCK:
        routes = list(entry.routes)
        middlewares = list(entry.middlewares)

    best_path: Optional[tuple[Route, dict[str, str], tuple]] = None
    best_method: Optional[tuple[Route, dict[str, str], tuple]] = None
    allowed: list[str] = []
    for route in routes:
        params = _match_segments(route.segments, path_segments)
        if params is None:
            continue
        priority = (
            -(len(route.segments) - len(route.param_names)),
            len(route.param_names),
            route.order,
        )
        candidate = (route, params, priority)
        if best_path is None or priority < best_path[2]:
            best_path = candidate
        if route.method not in allowed:
            allowed.append(route.method)
        if route.method == method:
            if best_method is None or priority < best_method[2]:
                best_method = candidate

    selected = best_method if best_method is not None else best_path
    request_for_handlers = dict(request_map)
    request_for_handlers['params'] = dict(selected[1]) if selected else {}

    for middleware_callable in middlewares:
        middleware_result = middleware_callable(request_for_handlers)
        if middleware_result is None:
            continue
        if isinstance(middleware_result, dict):
            return _to_plain(middleware_result)
        raise ValueError(
            "http_router: middleware must return a response map or nova, got "
            f"{type(middleware_result).__name__}"
        )

    if best_method is not None:
        route, params, _priority = best_method
        request_for_handlers['params'] = dict(params)
        return _to_plain(route.handler(request_for_handlers))

    if best_path is not None:
        headers = {
            'content-type': 'text/plain',
            'allow': ', '.join(sorted(allowed)),
        }
        return {
            'status': 405,
            'headers': headers,
            'body': METHOD_NOT_ALLOWED_BODY,
        }

    return {
        'status': 404,
        'headers': {'content-type': 'text/plain'},
        'body': NOT_FOUND_BODY,
    }


def _match_segments(
    pattern_segments: tuple[str, ...],
    path_segments: tuple[str, ...],
) -> Optional[dict[str, str]]:
    if len(pattern_segments) != len(path_segments):
        return None
    params: dict[str, str] = {}
    for pattern_segment, path_segment in zip(pattern_segments, path_segments):
        if pattern_segment.startswith(':'):
            params[pattern_segment[1:]] = path_segment
        elif pattern_segment != path_segment:
            return None
    return params


def _to_plain(value: Any) -> Any:
    """Unwrap Powang values a callback may return.

    A Powang function declared to return ``some`` reaches Python as the raw
    payload of the ``some`` wrapper. Its nested map keys are still Powang
    string objects, so converting them here keeps middleware that returns a
    response map (or nova to continue) usable without changing the shared
    extern bridge.
    """
    if isinstance(value, PowangTypeBase):
        return _to_plain(value.data)
    if isinstance(value, dict):
        return {_to_plain(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value
