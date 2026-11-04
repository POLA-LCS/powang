"""HTTP client helpers for Powang.

The module speaks plain HTTP and HTTPS through :mod:`urllib.request` from the
standard library. Values cross the extern boundary as plain Python objects:
the response is a ``dict`` with ``status``, ``headers``, ``body``, ``url`` and
``elapsed_ms`` keys.

Policy:

* non-2xx responses are normal results, never exceptions
* failures raise ``ValueError`` with a short kind prefix so programs can
  branch on the message text: ``timeout:``, ``dns:``, ``connect:``,
  ``tls:``, ``protocol:`` or ``invalid url:``
* the body is capped at :data:`MAX_BODY_BYTES` to bound memory use
* TLS certificates are verified unless ``verify_tls`` is false
"""

import http.client
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_BODY_BYTES: int = 1024 * 1024
DEFAULT_TIMEOUT_MS: int = 10000

SUPPORTED_METHODS = frozenset({
    'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS',
})


def _require_text(value: Any, argument: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"{argument}: {argument} must be a string, got {type(value).__name__}"
        )
    return value


def _require_boolean(value: Any, argument: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"options: {argument} must be a boolean, got {type(value).__name__}"
        )
    return value


def _normalize_method(method: Any) -> str:
    if not isinstance(method, str):
        raise ValueError(
            f"method: method must be a string, got {type(method).__name__}"
        )
    normalized = method.strip().upper()
    if normalized not in SUPPORTED_METHODS:
        raise ValueError(
            f"method: unsupported HTTP method {method!r}; "
            f"expected one of {', '.join(sorted(SUPPORTED_METHODS))}"
        )
    return normalized


def _timeout_seconds(timeout_ms: Any) -> float:
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, (int, float)):
        raise ValueError(
            f"timeout: timeout_ms must be an integer, got "
            f"{type(timeout_ms).__name__}"
        )
    if timeout_ms <= 0:
        raise ValueError(f"timeout: timeout_ms must be positive, got {timeout_ms}")
    return timeout_ms / 1000.0


def _normalize_headers(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, (list, tuple)):
        ## An empty Powang map literal is written `[]`, and the extern bridge
        ## keeps explicitly passed arrays as lists. Accept [key, value] pairs.
        pairs: dict[Any, Any] = {}
        for index, item in enumerate(headers):
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError(
                    f"headers: entry {index + 1} must be a [key, value] pair"
                )
            pairs[item[0]] = item[1]
        headers = pairs
    if not isinstance(headers, dict):
        raise ValueError(
            f"headers: headers must be a map, got {type(headers).__name__}"
        )
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str):
            raise ValueError(
                f"headers: header names must be strings, got "
                f"{type(key).__name__}"
            )
        if isinstance(value, str):
            text = value
        elif isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, (int, float)):
            text = str(value)
        else:
            raise ValueError(
                f"headers: value for {key!r} must be a string, number or "
                f"boolean, got {type(value).__name__}"
            )
        normalized[key] = text
    return normalized


def _validate_url(url: Any) -> str:
    if not isinstance(url, str):
        raise ValueError(
            f"invalid url: url must be a string, got {type(url).__name__}"
        )
    text = url.strip()
    if not text:
        raise ValueError("invalid url: url must not be empty")
    if any(character.isspace() for character in text):
        raise ValueError(f"invalid url: whitespace in {text!r}")
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError as error:
        raise ValueError(f"invalid url: {text!r}: {error}") from None
    if parts.scheme.lower() not in {'http', 'https'}:
        raise ValueError(
            f"invalid url: unsupported scheme {parts.scheme!r} in {text!r}; "
            f"expected http or https"
        )
    if not parts.netloc:
        raise ValueError(f"invalid url: missing host in {text!r}")
    return text


def _build_ssl_context(verify_tls: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not verify_tls:
        ## Explicit opt-out: leave hostname checking and chain validation off.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Turn every redirect into an ``HTTPError`` carrying the real response."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _headers_to_map(headers: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if headers is None:
        return result
    for key, value in headers.items():
        name = str(key).lower()
        text = str(value)
        if name in result:
            result[name] = f"{result[name]}, {text}"
        else:
            result[name] = text
    return result


def _response_status(response: Any) -> int:
    status = getattr(response, 'status', None)
    if status is None:
        status = getattr(response, 'code', 0)
    return int(status)


def _read_body(response: Any, max_body_bytes: int) -> str:
    raw = response.read(max_body_bytes + 1)
    if raw is None:
        raw = b""
    if len(raw) > max_body_bytes:
        raw = raw[:max_body_bytes]
    return raw.decode('utf-8', errors='replace')


def _translate_url_error(
    error: urllib.error.URLError, url: str, timeout_ms: int,
) -> ValueError:
    reason = getattr(error, 'reason', None)
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return ValueError(
            f"timeout: request to {url} timed out after {timeout_ms} ms: {reason}"
        )
    if isinstance(reason, socket.gaierror):
        return ValueError(f"dns: cannot resolve host for {url}: {reason}")
    if isinstance(reason, ssl.SSLError):
        return ValueError(f"tls: TLS failure for {url}: {reason}")
    if isinstance(reason, ConnectionRefusedError):
        return ValueError(f"connect: connection refused by {url}: {reason}")
    if isinstance(reason, OSError):
        return ValueError(f"connect: request to {url} failed: {reason}")
    return ValueError(f"connect: request to {url} failed: {reason or error}")


def _execute(
    method: str,
    url: str,
    body: str,
    headers: dict[str, str],
    timeout_seconds: float,
    timeout_ms: int,
    follow_redirects: bool,
    verify_tls: bool,
    max_body_bytes: int,
) -> dict[str, Any]:
    if method in {'GET', 'HEAD'} and body == "":
        data = None
    else:
        data = body.encode('utf-8')

    request = urllib.request.Request(
        url, data=data, headers=headers, method=method,
    )

    handlers: list[Any] = [
        urllib.request.HTTPSHandler(context=_build_ssl_context(verify_tls)),
    ]
    if not follow_redirects:
        handlers.append(_NoRedirectHandler())
    opener = urllib.request.build_opener(*handlers)

    start = time.perf_counter()
    try:
        response = opener.open(request, timeout=timeout_seconds)
    except urllib.error.HTTPError as http_error:
        ## 4xx, 5xx and (without a redirect handler) 3xx are real responses.
        response = http_error

    try:
        body_text = _read_body(response, max_body_bytes)
        status = _response_status(response)
        response_headers = _headers_to_map(getattr(response, 'headers', None))
        final_url = response.geturl() if hasattr(response, 'geturl') else url
    finally:
        response.close()
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    return {
        'status': status,
        'headers': response_headers,
        'body': body_text,
        'url': final_url,
        'elapsed_ms': elapsed_ms,
    }


def _perform(
    method: str,
    url: Any,
    body: Any,
    headers: Any,
    timeout_ms: Any,
    follow_redirects: Any,
    verify_tls: Any,
) -> dict[str, Any]:
    method = _normalize_method(method)
    url = _validate_url(url)
    body = _require_text(body, "body")
    headers = _normalize_headers(headers)
    timeout_seconds = _timeout_seconds(timeout_ms)
    follow_redirects = _require_boolean(follow_redirects, "follow_redirects")
    verify_tls = _require_boolean(verify_tls, "verify_tls")

    try:
        return _execute(
            method,
            url,
            body,
            headers,
            timeout_seconds,
            timeout_ms,
            follow_redirects,
            verify_tls,
            MAX_BODY_BYTES,
        )
    except urllib.error.URLError as url_error:
        raise _translate_url_error(url_error, url, timeout_ms) from None
    except socket.gaierror as dns_error:
        raise ValueError(f"dns: cannot resolve host for {url}: {dns_error}") from None
    except (socket.timeout, TimeoutError) as timeout_error:
        raise ValueError(
            f"timeout: request to {url} timed out after {timeout_ms} ms: "
            f"{timeout_error}"
        ) from None
    except ssl.SSLError as tls_error:
        raise ValueError(f"tls: TLS failure for {url}: {tls_error}") from None
    except http.client.HTTPException as protocol_error:
        raise ValueError(
            f"protocol: invalid HTTP response from {url}: {protocol_error}"
        ) from None
    except ConnectionError as connect_error:
        raise ValueError(
            f"connect: failed to connect to {url}: {connect_error}"
        ) from None
    except OSError as os_error:
        raise ValueError(f"connect: request to {url} failed: {os_error}") from None
    except ValueError as value_error:
        raise ValueError(f"invalid url: {value_error}") from None


def get(
    url: str,
    headers: dict | list | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    follow_redirects: bool = True,
    verify_tls: bool = True,
) -> dict[str, Any]:
    """Perform a GET request and return the response map."""
    return _perform(
        'GET', url, "", headers, timeout_ms, follow_redirects, verify_tls,
    )


def post(
    url: str,
    body: str = "",
    headers: dict | list | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    follow_redirects: bool = True,
    verify_tls: bool = True,
) -> dict[str, Any]:
    """Perform a POST request with an optional UTF-8 body."""
    return _perform(
        'POST', url, body, headers, timeout_ms, follow_redirects, verify_tls,
    )


def request(
    method: str,
    url: str,
    body: str = "",
    headers: dict | list | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    follow_redirects: bool = True,
    verify_tls: bool = True,
) -> dict[str, Any]:
    """Perform an arbitrary supported method and return the response map."""
    return _perform(
        method, url, body, headers, timeout_ms, follow_redirects, verify_tls,
    )
