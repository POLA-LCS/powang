"""In-process HTTP server helpers for Powang (ADR-0001 W28).

The server is built on :class:`http.server.ThreadingHTTPServer` and calls a
Powang handler for every request. A handler crosses the extern boundary as a
real Python callable (see :func:`src.runtime.getPythonFromPowang`); every
invocation installs a cloned interpreter state in the serving thread, so
concurrent requests cannot corrupt each other's scopes.

Policy:

* request and response maps use plain Python values
* malformed requests are answered with 400, oversized bodies with 413 and
  header floods with 431 instead of raising
* a failing handler is logged as one ``[HTTP ERROR]`` line and answered with a
  generic 500; client responses never contain a stack trace
* servers live in the owning interpreter state's registry, keyed by a
  per-state integer id starting at 1
"""

from __future__ import annotations

import http.server
import itertools
import re
import socket
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .state import get_state

DEFAULT_WORKERS: int = 4
DEFAULT_MAX_BODY_BYTES: int = 1024 * 1024
DEFAULT_READ_TIMEOUT_MS: int = 10000
DEFAULT_HOST: str = '127.0.0.1'

MAX_HEADER_BYTES: int = 64 * 1024
MAX_HEADERS: int = 100
## Rejected requests are drained up to this many bytes before the error
## response. Beyond it the connection is closed and a reset is acceptable.
MAX_DRAIN_BYTES: int = 8 * 1024 * 1024

SHUTDOWN_TIMEOUT_SECONDS: float = 2.0
POLL_INTERVAL_SECONDS: float = 0.2

GENERIC_ERROR_BODY: str = 'internal server error'


def _response_status(response: Any) -> int:
    """Best-effort status extraction for the access log."""
    if isinstance(response, dict):
        raw = response.get('status', 200)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 500
    return 500


def _log_access(request_id: int, method: str, path: str, status: int, started_at: float) -> None:
    """Emit one access record; never blocks a response on a logging failure."""
    try:
        from .stdlib_log import access
        access(request_id, method, path, status, (time.perf_counter() - started_at) * 1000.0)
    except Exception:  # noqa: BLE001 - logging must never break a request
        pass

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

## Registry writes happen from any thread that starts or stops a server.
_REGISTRY_LOCK = threading.Lock()


class _BadResponse(ValueError):
    """A handler returned data that cannot be sent as an HTTP response."""


class _Rejected(Exception):
    """A request was rejected before the handler ran."""

    def __init__(self, status: int, body: str):
        super().__init__(body)
        self.status = status
        self.body = body


@dataclass(frozen=True)
class ServerOptions:
    workers: int = DEFAULT_WORKERS
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    read_timeout_ms: int = DEFAULT_READ_TIMEOUT_MS
    host: str = DEFAULT_HOST

    @property
    def read_timeout_seconds(self) -> float:
        return self.read_timeout_ms / 1000.0


class ServerHandle:
    """One running server and the thread that serves it."""

    def __init__(self, server_id: int, server: 'PowangHTTPServer',
                 options: ServerOptions):
        self.server_id: int = server_id
        self.server: PowangHTTPServer = server
        self.options: ServerOptions = options
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stopped: bool = False

    def stop(self) -> None:
        """Stop accepting work, wait for the loop, then release the port."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        self.server.shutdown()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(SHUTDOWN_TIMEOUT_SECONDS)
        self.server.server_close()


class PowangHTTPServer(http.server.ThreadingHTTPServer):
    """Threaded HTTP server carrying the Powang handler and its limits."""

    daemon_threads = True
    block_on_close = False
    ## Exclusive binding: a second listen on a busy port must fail instead of
    ## silently sharing the address (SO_REUSEADDR can do that on Windows).
    allow_reuse_address = False
    ## The stdlib default backlog is 5. A burst of browsers or load-test
    ## clients can overflow it, causing multi-second SYN retries.
    request_queue_size = 128

    def __init__(self, address, request_handler, handler, options):
        self.powang_handler = handler
        self.options = options
        self.worker_slots = threading.BoundedSemaphore(options.workers)
        self._request_ids = itertools.count(1)
        self._request_id_lock = threading.Lock()
        super().__init__(address, request_handler)

    def next_request_id(self) -> int:
        with self._request_id_lock:
            return next(self._request_ids)


class PowangRequestHandler(http.server.BaseHTTPRequestHandler):
    """Translate one HTTP request into a Powang handler call."""

    protocol_version = 'HTTP/1.1'
    server_version = 'PowangHTTP/1.0'
    sys_version = ''

    # -------------------------------------------------------------- transport
    def log_message(self, format, *args):  # noqa: A002 - base class signature
        ## The default access log would interleave with the single-line
        ## [HTTP ERROR] diagnostics. Keep stderr for handler failures only.
        return

    def handle_one_request(self):
        try:
            self.connection.settimeout(self.server.options.read_timeout_seconds)
        except OSError:
            pass
        super().handle_one_request()

    def do_GET(self):        self._dispatch()
    def do_HEAD(self):       self._dispatch()
    def do_POST(self):       self._dispatch()
    def do_PUT(self):        self._dispatch()
    def do_PATCH(self):      self._dispatch()
    def do_DELETE(self):     self._dispatch()
    def do_OPTIONS(self):    self._dispatch()

    def _dispatch(self):
        request_id = self.server.next_request_id()
        started_at = time.perf_counter()
        logged_status = 500
        self._request_body_remaining = 0
        self.server.worker_slots.acquire()
        try:
            request_map = self._read_request(request_id)
            response = self.server.powang_handler(request_map)
            logged_status = _response_status(response)
            self._send_handler_response(request_id, response)
        except _Rejected as rejected:
            logged_status = rejected.status
            self._send_error(rejected.status, rejected.body)
        except (socket.timeout, TimeoutError):
            logged_status = 408
            self._send_error(408, 'request timeout')
        except _BadResponse as bad_response:
            self._log_error(request_id, bad_response)
            self._send_error(500, GENERIC_ERROR_BODY)
        except Exception as error:  # noqa: BLE001 - host boundary
            self._log_error(request_id, error)
            self._send_error(500, GENERIC_ERROR_BODY)
        finally:
            self.server.worker_slots.release()
            _log_access(request_id, self.command or '?', self.path or '?', logged_status, started_at)

    # ---------------------------------------------------------------- request
    def _read_request(self, request_id: int) -> dict[str, Any]:
        self._check_header_limits()

        transfer_encoding = self.headers.get('transfer-encoding')
        if transfer_encoding is not None \
                and transfer_encoding.strip().lower() != 'identity':
            raise _Rejected(400, 'bad request')

        max_body_bytes = self.server.options.max_body_bytes
        length_header = self.headers.get('content-length')
        body = ''
        if length_header is not None:
            try:
                content_length = int(length_header)
            except (TypeError, ValueError):
                raise _Rejected(400, 'bad request') from None
            if content_length < 0:
                raise _Rejected(400, 'bad request')
            self._request_body_remaining = content_length
            if content_length > max_body_bytes:
                raise _Rejected(413, 'request body too large')
            raw_body = self.rfile.read(content_length)
            self._request_body_remaining = 0
            if len(raw_body) != content_length:
                raise _Rejected(400, 'bad request')
            body = raw_body.decode('utf-8', errors='replace')

        parts = urllib.parse.urlsplit(self.path)
        query: dict[str, Any] = {}
        for key, values in urllib.parse.parse_qs(
            parts.query, keep_blank_values=True,
        ).items():
            query[key] = values[0] if len(values) == 1 else values

        headers: dict[str, str] = {}
        for name, value in self.headers.items():
            lowered = name.lower()
            if lowered in headers:
                headers[lowered] = f"{headers[lowered]}, {value}"
            else:
                headers[lowered] = value

        return {
            'method': self.command,
            'path': parts.path or '/',
            'query': query,
            'headers': headers,
            'body': body,
            'remote_addr': self._remote_addr(),
            'request_id': request_id,
        }

    def _check_header_limits(self) -> None:
        items = list(self.headers.items())
        if len(items) > MAX_HEADERS:
            raise _Rejected(431, 'request headers too large')
        total = 0
        for name, value in items:
            total += len(name) + len(value) + 4
            if total > MAX_HEADER_BYTES:
                raise _Rejected(431, 'request headers too large')

    def _remote_addr(self) -> str:
        address = self.client_address
        if isinstance(address, tuple) and address:
            return str(address[0])
        return str(address)

    # --------------------------------------------------------------- response
    def _send_handler_response(self, request_id: int, response: Any) -> None:
        if not isinstance(response, dict):
            raise _BadResponse(
                f"handler returned {type(response).__name__}, expected a map"
            )

        status = response.get('status', 200)
        if isinstance(status, bool) or not isinstance(status, int) \
                or status < 100 or status > 599:
            raise _BadResponse(f"invalid response status: {status!r}")

        header_map = response.get('headers', {})
        if header_map is None:
            header_map = {}
        if not isinstance(header_map, dict):
            raise _BadResponse(
                f"response headers must be a map, got "
                f"{type(header_map).__name__}"
            )

        headers = self._normalize_response_headers(header_map)
        body_text = self._coerce_body(response.get('body', ''))
        body_bytes = body_text.encode('utf-8', errors='replace')

        self.send_response_only(status)
        self.send_header('Content-Length', str(len(body_bytes)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header('Connection', 'close')
        self.close_connection = True
        self.end_headers()

        if self.command != 'HEAD' and body_bytes:
            self.wfile.write(body_bytes)

    def _normalize_response_headers(self, header_map: dict) -> dict[str, str]:
        headers: dict[str, str] = {}
        for name, value in header_map.items():
            if not isinstance(name, str):
                raise _BadResponse('response header names must be strings')
            if not _HEADER_NAME.match(name):
                raise _BadResponse(f"invalid response header name: {name!r}")
            lowered = name.lower()
            if lowered in {'content-length', 'transfer-encoding', 'connection'}:
                ## Framing is owned by the server, never by the handler.
                continue
            if isinstance(value, str):
                text = value
            elif isinstance(value, bool):
                text = 'true' if value else 'false'
            elif isinstance(value, (int, float)):
                text = str(value)
            else:
                raise _BadResponse(
                    f"header {name!r} must be a string, number or bool"
                )
            if '\r' in text or '\n' in text:
                raise _BadResponse(f"header {name!r} contains a newline")
            headers[name] = text
        if not any(name.lower() == 'content-type' for name in headers):
            headers['content-type'] = 'text/plain'
        return headers

    @staticmethod
    def _coerce_body(value: Any) -> str:
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float)):
            return str(value)
        raise _BadResponse(
            f"response body must be a string, got {type(value).__name__}"
        )

    def _send_error(self, status: int, body: str) -> None:
        ## Drain what is still in flight first. Closing a socket with unread
        ## request bytes makes Windows send a reset, and the client would lose
        ## the error response it was about to read.
        self._drain_remaining_body()
        data = body.encode('utf-8', errors='replace')
        try:
            self.send_response_only(status)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            if self.command != 'HEAD' and data:
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.close_connection = True

    def _drain_remaining_body(self) -> None:
        remaining = min(
            max(0, getattr(self, '_request_body_remaining', 0)),
            MAX_DRAIN_BYTES,
        )
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except (OSError, socket.timeout, TimeoutError):
            pass
        self._request_body_remaining = 0

    @staticmethod
    def _log_error(request_id: int, error: BaseException) -> None:
        detail = ' '.join(str(error).split())
        print(f"[HTTP ERROR] request_id={request_id}: {detail}", file=sys.stderr)


## --------------------------------------------------------------------- options
def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _normalize_options(options: Any) -> ServerOptions:
    if options is None:
        options = {}
    if isinstance(options, (list, tuple)):
        pairs: dict[Any, Any] = {}
        for index, item in enumerate(options):
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError(
                    f"[HTTP ERROR] options: entry {index + 1} must be a "
                    f"[key, value] pair"
                )
            pairs[item[0]] = item[1]
        options = pairs
    if not isinstance(options, dict):
        raise ValueError(
            f"[HTTP ERROR] options: options must be a map, got "
            f"{type(options).__name__}"
        )

    workers = options.get('workers', DEFAULT_WORKERS)
    if not _is_integer(workers) or workers <= 0:
        raise ValueError(
            f"[HTTP ERROR] options: workers must be a positive integer, got "
            f"{workers!r}"
        )

    max_body_bytes = options.get('max_body_bytes', DEFAULT_MAX_BODY_BYTES)
    if not _is_integer(max_body_bytes) or max_body_bytes < 0:
        raise ValueError(
            f"[HTTP ERROR] options: max_body_bytes must be a non-negative "
            f"integer, got {max_body_bytes!r}"
        )

    read_timeout_ms = options.get('read_timeout_ms', DEFAULT_READ_TIMEOUT_MS)
    if isinstance(read_timeout_ms, bool) \
            or not isinstance(read_timeout_ms, (int, float)) \
            or read_timeout_ms <= 0:
        raise ValueError(
            f"[HTTP ERROR] options: read_timeout_ms must be a positive "
            f"number, got {read_timeout_ms!r}"
        )

    host = options.get('host', DEFAULT_HOST)
    if not isinstance(host, str) or not host.strip():
        raise ValueError(
            f"[HTTP ERROR] options: host must be a non-empty string, got "
            f"{host!r}"
        )

    return ServerOptions(
        workers=int(workers),
        max_body_bytes=int(max_body_bytes),
        read_timeout_ms=int(read_timeout_ms),
        host=host.strip(),
    )


def _normalize_port(port: Any) -> int:
    if not _is_integer(port) or port < 1 or port > 65535:
        raise ValueError(
            f"[HTTP ERROR] port: expected an integer in 1..65535, got {port!r}"
        )
    return port


def _require_handler(handler: Any) -> Callable:
    if not callable(handler):
        raise ValueError(
            f"[HTTP ERROR] handler: expected a function, got "
            f"{type(handler).__name__}"
        )
    return handler


# ---------------------------------------------------------------------- server
def _create_handle(port: Any, handler: Any, options: Any):
    port = _normalize_port(port)
    handler = _require_handler(handler)
    server_options = _normalize_options(options)

    state = get_state()
    try:
        server = PowangHTTPServer(
            (server_options.host, port),
            PowangRequestHandler,
            handler,
            server_options,
        )
    except OSError as error:
        raise ValueError(
            f"[HTTP ERROR] bind: cannot listen on "
            f"{server_options.host}:{port}: {error}"
        ) from None

    with _REGISTRY_LOCK:
        server_id = state.http_next_server_id
        state.http_next_server_id += 1
        handle = ServerHandle(server_id, server, server_options)
        state.http_servers[server_id] = handle
    return handle, state


def listen(port: int, handler: Any, options: dict | list | None = None) -> int:
    """Start a background server and return its per-state integer id."""
    handle, _state = _create_handle(port, handler, options)
    thread = threading.Thread(
        target=_serve_forever,
        args=(handle,),
        name=f'powang-http-{handle.server_id}',
        daemon=True,
    )
    handle.thread = thread
    thread.start()
    return handle.server_id


def _serve_forever(handle: ServerHandle) -> None:
    try:
        handle.server.serve_forever(poll_interval=POLL_INTERVAL_SECONDS)
    except Exception as error:  # noqa: BLE001 - background thread boundary
        print(
            f"[HTTP ERROR] server {handle.server_id}: "
            f"{' '.join(str(error).split())}",
            file=sys.stderr,
        )


def serve(port: int, handler: Any, options: dict | list | None = None) -> None:
    """Serve in the calling thread until stopped or interrupted (SIGINT)."""
    handle, state = _create_handle(port, handler, options)
    try:
        handle.server.serve_forever(poll_interval=POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        ## Ctrl-C is a normal shutdown request for a blocking server.
        pass
    finally:
        handle.stop()
        with _REGISTRY_LOCK:
            state.http_servers.pop(handle.server_id, None)


def stop(server_id: int) -> None:
    """Stop a server started with :func:`listen`."""
    if not _is_integer(server_id):
        raise ValueError(
            f"[HTTP ERROR] stop: expected a server id integer, got "
            f"{server_id!r}"
        )
    state = get_state()
    with _REGISTRY_LOCK:
        handle = state.http_servers.get(server_id)
    if handle is None:
        raise ValueError(
            f"[HTTP ERROR] stop: no running server with id {server_id}"
        )
    handle.stop()
    with _REGISTRY_LOCK:
        state.http_servers.pop(server_id, None)


def shutdown_state_servers(state) -> None:
    """Stop every server owned by ``state`` (used at process shutdown)."""
    with _REGISTRY_LOCK:
        handles = list(state.http_servers.values())
        state.http_servers.clear()
    for handle in handles:
        try:
            handle.stop()
        except Exception:
            pass
