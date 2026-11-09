"""Subprocess helpers for the Powang characterization test suite.

Every test runs the interpreter in a fresh Python subprocess. That keeps the
interpreter's module-level state isolated between tests and exercises the real
CLI path (``python powang.py <file>``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POWANG = ROOT / "powang.py"
DEFAULT_TIMEOUT = 60

_ENV = dict(os.environ)
_ENV["PYTHONIOENCODING"] = "utf-8"
_ENV["PYTHONUTF8"] = "1"


def normalize_newlines(text: str) -> str:
    """Normalize CRLF and bare CR to LF so golden output is platform-neutral."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _decode(data: bytes) -> str:
    return normalize_newlines(data.decode("utf-8", errors="replace"))


@dataclass(frozen=True)
class RunResult:
    """Captured result of one interpreter process."""

    args: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int

    @property
    def combined(self) -> str:
        return self.stdout + self.stderr

    @property
    def lines(self) -> list[str]:
        return self.stdout.splitlines()

    @property
    def error_lines(self) -> list[str]:
        return self.stderr.splitlines()


def run_command(
    args: list[str] | tuple[str, ...],
    *,
    input_text: str | None = None,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    optimize: bool = False,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Run ``python powang.py <args>`` and capture decoded output."""
    command = [sys.executable]
    if optimize:
        command.append("-O")
    command.extend([str(POWANG), *args])
    process_env = dict(_ENV)
    if env:
        process_env.update(env)
    completed = subprocess.run(
        command,
        input=input_text.encode("utf-8") if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd if cwd is not None else ROOT),
        env=process_env,
        timeout=timeout,
        check=False,
    )
    return RunResult(
        args=tuple(args),
        stdout=_decode(completed.stdout),
        stderr=_decode(completed.stderr),
        returncode=completed.returncode,
    )


def run_file(
    path: Path | str,
    *args: str,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    optimize: bool = False,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Run one ``.po`` file by path. Relative paths resolve against the repo."""
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return run_command(
        [str(resolved), *args],
        cwd=cwd,
        timeout=timeout,
        optimize=optimize,
        env=env,
    )


def write_po(directory: Path | str, name: str, source: str) -> Path:
    """Write a UTF-8, LF-only Powang source file into ``directory``."""
    path = Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8", newline="\n")
    return path


def run_source(
    source: str,
    *,
    name: str = "program.po",
    timeout: int = DEFAULT_TIMEOUT,
    optimize: bool = False,
    args: tuple[str, ...] = (),
) -> RunResult:
    """Write ``source`` to a temporary ``.po`` file and run it."""
    with tempfile.TemporaryDirectory(prefix="powang-test-") as directory:
        path = write_po(directory, name, source)
        return run_file(path, *args, timeout=timeout, optimize=optimize)


def run_source_with_input(
    source: str,
    input_text: str,
    *,
    name: str = "program.po",
    timeout: int = DEFAULT_TIMEOUT,
) -> RunResult:
    """Write ``source`` to a temporary ``.po`` file and run it with stdin."""
    with tempfile.TemporaryDirectory(prefix="powang-test-") as directory:
        path = write_po(directory, name, source)
        return run_command([str(path)], input_text=input_text, timeout=timeout)


def run_repl(lines: str | list[str] | tuple[str, ...]) -> RunResult:
    """Pipe lines into the REPL. ``exit`` is not appended automatically."""
    if isinstance(lines, str):
        payload = lines
    else:
        payload = "".join(
            line if line.endswith("\n") else line + "\n" for line in lines
        )
    return run_command([], input_text=payload)


def assert_no_traceback(case, result: RunResult) -> None:
    """Assert that a failed run produced a Powang diagnostic, not a Python crash."""
    case.assertNotIn("Traceback (most recent call last)", result.combined)
    case.assertNotIn("AssertionError", result.stdout)
