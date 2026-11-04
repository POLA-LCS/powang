"""Minimal Language Server Protocol implementation for powang.

The server speaks JSON-RPC over standard input and output and provides:

* diagnostics from the parser and the gradual type checker
* keyword and builtin completion

It has no third-party dependencies and only needs the repository root on
``sys.path`` (run it from the checkout with ``python tools/powang_lsp.py``).

Every editor that supports the Language Server Protocol can use it by pointing
the client at this command.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.parser import Parser  # noqa: E402
from src.typecheck import check_source  # noqa: E402
from src.error import PowangError  # noqa: E402

KEYWORDS = [
    "if", "else", "for", "fun", "return", "use", "type", "extern",
    "try", "catch", "finally", "spawn", "export",
]

BUILTINS = [
    "output", "format", "printf", "error", "fail", "input", "typeof", "size",
    "open", "write", "read", "close", "system", "wait", "cancel", "task_status",
    "spawn",
]

DOCUMENTS: dict[str, str] = {}


def send(message: dict) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n")
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n", b""):
            break
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _line_number(error: Exception) -> int:
    line = getattr(error, "line", None)
    if isinstance(line, int) and line > 0:
        return line - 1
    if isinstance(line, str) and line.isdigit():
        return int(line) - 1
    return 0


def diagnose(uri: str, text: str) -> None:
    diagnostics: list[dict] = []
    try:
        parser = Parser(text, source_path=uri)
        program = parser.parse()
    except PowangError as error:
        diagnostics.append({
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 1},
            },
            "severity": 1,
            "source": "powang",
            "message": str(error),
        })
    else:
        try:
            for type_error in check_source(text, uri):
                diagnostics.append({
                    "range": {
                        "start": {"line": _line_number(type_error), "character": 0},
                        "end": {"line": _line_number(type_error), "character": 1},
                    },
                    "severity": 1,
                    "source": "powang",
                    "message": str(type_error),
                })
        except Exception as error:  # noqa: BLE001 - never crash the server
            diagnostics.append({
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 1},
                },
                "severity": 2,
                "source": "powang",
                "message": f"internal checker error: {error}",
            })

    send({
        "jsonrpc": "2.0",
        "method": "textDocument/publishDiagnostics",
        "params": {
            "uri": uri,
            "diagnostics": diagnostics,
        },
    })


def handle_initialize(request_id) -> None:
    send({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "capabilities": {
                "textDocumentSync": 1,
                "completionProvider": {
                    "triggerCharacters": [".", ":"],
                },
                "hoverProvider": False,
            },
            "serverInfo": {
                "name": "powang-lsp",
                "version": "0.2.0",
            },
        },
    })


def handle_completion(request_id) -> None:
    items = [
        {"label": name, "kind": 14, "detail": "keyword"}
        for name in KEYWORDS
    ] + [
        {"label": name, "kind": 3, "detail": "builtin"}
        for name in BUILTINS
    ]
    send({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": items,
    })


def main() -> None:
    while True:
        message = read_message()
        if message is None:
            break
        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            handle_initialize(request_id)
        elif method == "initialized":
            pass
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": request_id, "result": None})
        elif method == "exit":
            break
        elif method == "textDocument/didOpen":
            params = message.get("params", {})
            document = params.get("textDocument", {})
            uri = document.get("uri")
            text = document.get("text", "")
            if uri is not None:
                DOCUMENTS[uri] = text
                diagnose(uri, text)
        elif method == "textDocument/didChange":
            params = message.get("params", {})
            document = params.get("textDocument", {})
            uri = document.get("uri")
            changes = params.get("contentChanges", [])
            if uri is not None and changes:
                DOCUMENTS[uri] = changes[-1].get("text", "")
                diagnose(uri, DOCUMENTS[uri])
        elif method == "textDocument/didSave":
            params = message.get("params", {})
            document = params.get("textDocument", {})
            uri = document.get("uri")
            if uri in DOCUMENTS:
                diagnose(uri, DOCUMENTS[uri])
        elif method == "textDocument/completion":
            handle_completion(request_id)
        else:
            if request_id is not None:
                send({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                })


if __name__ == "__main__":
    main()
