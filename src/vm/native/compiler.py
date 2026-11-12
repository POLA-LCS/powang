"""Integrated g++ driver for the native runtime.

The driver builds an argv list, never a shell string, and compiles the
generated translation unit either from a temporary ``temp.cpp`` or from
standard input. Diagnostics are captured as text so the CLI and the tests can
report them without a second process.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


BASE_FLAGS: tuple[str, ...] = (
    "-std=c++17",
    "-O2",
    "-DNDEBUG",
    "-fno-rtti",
    "-Wall",
    "-Wextra",
    "-Wpedantic",
)

PROBE_TIMEOUT = 30.0
CAPTURE_LIMIT = 1024 * 1024
TRUNCATION_MARKER = "\n... [truncated]"


@dataclass(frozen=True)
class CompileResult:
    """The structured outcome of one compiler invocation."""

    ok: bool
    command: tuple[str, ...]
    output: Path
    returncode: int
    stdout: str
    stderr: str
    duration: float
    source_path: Path | None = None


class NativeBuildError(RuntimeError):
    """A native build failure, optionally carrying the compiler result."""

    def __init__(
        self, message: str, result: CompileResult | None = None,
    ) -> None:
        super().__init__(message)
        self.result = result


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _truncate(text: str) -> str:
    """Bound one captured stream to 1 MiB of UTF-8 bytes."""
    encoded = text.encode("utf-8", errors="ignore")
    if len(encoded) <= CAPTURE_LIMIT:
        return text
    return (
        encoded[:CAPTURE_LIMIT].decode("utf-8", errors="ignore")
        + TRUNCATION_MARKER
    )


class IntegratedGcc:
    """Compile C++17 sources against the prebuilt native runtime library."""

    def __init__(
        self,
        *,
        compiler: str = "g++",
        include_dir: Path,
        library_dir: Path | None = None,
        timeout: float = 120.0,
        static_link: bool = True,
    ) -> None:
        self.compiler = compiler
        self.include_dir = Path(include_dir)
        self.library_dir = Path(library_dir) if library_dir is not None else None
        self.timeout = timeout
        self.static_link = static_link
        self._version: str | None = None

    def available(self) -> str | None:
        """Return the resolved compiler path, or None when it is missing."""
        return shutil.which(self.compiler)

    def version(self) -> str:
        """Return the first line of ``--version`` or an empty string."""
        if self._version is not None:
            return self._version
        executable = self.available()
        if executable is None:
            self._version = ""
            return self._version
        try:
            completed = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PROBE_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            self._version = ""
            return self._version
        lines = completed.stdout.splitlines() if completed.returncode == 0 else []
        self._version = lines[0].strip() if lines else ""
        return self._version

    def compile(
        self,
        source: str,
        output: Path,
        *,
        use_stdin: bool = False,
        extra_flags: Sequence[str] = (),
        keep_source: bool = False,
    ) -> CompileResult:
        """Compile ``source`` to ``output`` and capture the diagnostics."""
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        command: list[str] = [self.compiler, *BASE_FLAGS]
        started = time.perf_counter()
        # A failed compile must not leave a stale executable behind.
        try:
            output.unlink(missing_ok=True)
        except OSError as error:
            return CompileResult(
                ok=False,
                command=tuple(command),
                output=output,
                returncode=-1,
                stdout="",
                stderr=(
                    f"cannot remove stale output {output}: {error}"
                ),
                duration=time.perf_counter() - started,
            )
        temporary: tempfile.TemporaryDirectory[str] | None = None
        generated: Path | None = None
        try:
            if use_stdin:
                command.extend(["-x", "c++", "-"])
            else:
                temporary = tempfile.TemporaryDirectory(
                    prefix="powang-native-"
                )
                generated = Path(temporary.name) / "temp.cpp"
                generated.write_text(source, encoding="utf-8", newline="\n")
                command.append(str(generated))
            command.extend(["-o", str(output), "-I", str(self.include_dir)])
            if self.library_dir is not None:
                command.extend(
                    ["-L", str(self.library_dir), "-lpwb_runtime"]
                )
            command.extend(extra_flags)
            if self.static_link:
                command.extend(
                    ["-static", "-static-libgcc", "-static-libstdc++"]
                )
            command.extend(["-pthread", "-s"])
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout,
                    input=source if use_stdin else None,
                )
            except FileNotFoundError:
                duration = time.perf_counter() - started
                return CompileResult(
                    ok=False,
                    command=tuple(command),
                    output=output,
                    returncode=-1,
                    stdout="",
                    stderr=(
                        f"compiler not found: {self.compiler}. "
                        "Install g++ and put it on PATH."
                    ),
                    duration=duration,
                )
            except subprocess.TimeoutExpired as error:
                duration = time.perf_counter() - started
                message = (
                    f"compiler timed out after {self.timeout:g} seconds: "
                    f"{self.compiler}"
                )
                captured = _truncate(_text(error.stderr).strip())
                if captured:
                    message = message + "\n" + captured
                return CompileResult(
                    ok=False,
                    command=tuple(command),
                    output=output,
                    returncode=-1,
                    stdout=_truncate(_text(error.stdout)),
                    stderr=_truncate(message),
                    duration=duration,
                )
            duration = time.perf_counter() - started
            source_copy: Path | None = None
            if keep_source and generated is not None:
                source_copy = output.with_suffix(".cpp")
                shutil.copyfile(generated, source_copy)
            produced = (
                output.exists() and output.is_file()
                and output.stat().st_size > 0
            )
            return CompileResult(
                ok=completed.returncode == 0 and produced,
                command=tuple(command),
                output=output,
                returncode=completed.returncode,
                stdout=_truncate(completed.stdout or ""),
                stderr=_truncate(completed.stderr or ""),
                duration=duration,
                source_path=source_copy,
            )
        finally:
            if temporary is not None:
                temporary.cleanup()
