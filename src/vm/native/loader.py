"""Compile a program image to a native executable and run it.

The intermediate generated source stays in memory. A temporary executable
directory is removed by :meth:`NativeProgram.cleanup` unless the caller chose
an explicit output path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..image import ProgramImage
from .build import RuntimePaths, ensure_runtime
from .compiler import CompileResult, IntegratedGcc, NativeBuildError
from .source_gen import render_bundle_cpp, render_temp_cpp


@dataclass(frozen=True)
class NativeProgram:
    """One compiled native executable plus its generated source."""

    executable: Path
    source: str
    compile_result: CompileResult
    temporary: bool

    def cleanup(self) -> None:
        """Remove the executable directory when this program is temporary."""
        if not self.temporary:
            return
        shutil.rmtree(self.executable.parent, ignore_errors=True)


@dataclass(frozen=True)
class NativeRunResult:
    """The observable outcome of one native run."""

    stdout: str
    stderr: str
    returncode: int
    executable: Path
    compile_result: CompileResult | None = None


def compile_image(
    image: ProgramImage,
    *,
    output: Path | None = None,
    keep_source: bool = False,
    paths: RuntimePaths | None = None,
    bundle: bytes | None = None,
) -> NativeProgram:
    """Render, compile and return the native program for ``image``."""
    paths = paths or ensure_runtime()
    source = (
        render_bundle_cpp(bundle) if bundle is not None
        else render_temp_cpp(image)
    )
    temporary = output is None
    if temporary:
        directory = Path(tempfile.mkdtemp(prefix="powang-native-"))
        name = "program.exe" if os.name == "nt" else "program"
        executable = directory / name
    else:
        executable = Path(output)
    driver = IntegratedGcc(
        include_dir=paths.include_dir, library_dir=paths.build_dir,
    )
    try:
        result = driver.compile(
            source, executable, keep_source=keep_source,
        )
    except BaseException:
        if temporary:
            shutil.rmtree(executable.parent, ignore_errors=True)
        raise
    if not result.ok:
        if temporary:
            shutil.rmtree(executable.parent, ignore_errors=True)
        raise NativeBuildError("native compile failed", result)
    return NativeProgram(
        executable=executable,
        source=source,
        compile_result=result,
        temporary=temporary,
    )


def run_native(
    image: ProgramImage,
    args: Sequence[str] = (),
    *,
    input_text: str | None = None,
    timeout: float = 60.0,
    paths: RuntimePaths | None = None,
    state: object | None = None,
    bundle: bytes | None = None,
) -> NativeRunResult:
    """Compile ``image``, run the executable and capture its output.

    A prebuilt bundle is used as is. With a state and no bundle, the bundle is
    built here and the state must already be the active state, because the
    builder resolves imports through ``get_module_loader()``.
    """
    if bundle is None and state is not None:
        from .bundle import build_bundle
        bundle = build_bundle(image, state)
    program = compile_image(image, paths=paths, bundle=bundle)
    try:
        completed = subprocess.run(
            [str(program.executable), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            input=input_text,
        )
    finally:
        program.cleanup()
    return NativeRunResult(
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        returncode=completed.returncode,
        executable=program.executable,
        compile_result=program.compile_result,
    )
