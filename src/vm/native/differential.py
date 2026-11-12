"""Differential runner for the native engine.

Compares the Python VM and the native runtime on a corpus of ``.po`` files,
including standard output, standard error and exit code. The Python VM is the
oracle. A native build or a compile error before execution is reported as a
failure with the captured text.

Usage:

    python -m src.vm.native.differential --corpus tests/native/corpus/n5
    python -m src.vm.native.differential --examples examples --fail-fast
    python -m src.vm.native.differential --corpus tests/native/corpus --json
    python -m src.vm.native.differential --fuzz --seed 2026 --count 1000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ...error import PowangError
from .build import ensure_runtime
from .compiler import NativeBuildError
from .session import run_native_file


@dataclass(frozen=True)
class Comparison:
    path: Path
    python_stdout: str
    python_stderr: str
    python_code: int
    native_stdout: str
    native_stderr: str
    native_code: int
    error: str = ""

    @property
    def equal(self) -> bool:
        return (
            self.python_code == self.native_code
            and self.python_stdout == self.native_stdout
            and self.python_stderr == self.native_stderr
            and not self.error
        )

    def report(self) -> str:
        if self.equal:
            return f"ok   {self.path}"
        lines = [f"fail {self.path}"]
        if self.error:
            lines.append(f"     error: {self.error}")
        if self.python_code != self.native_code:
            lines.append(
                f"     exit: python={self.python_code} "
                f"native={self.native_code}"
            )
        if self.python_stdout != self.native_stdout:
            lines.append(f"     python stdout: {self.python_stdout!r}")
            lines.append(f"     native stdout: {self.native_stdout!r}")
        if self.python_stderr != self.native_stderr:
            lines.append(f"     python stderr: {self.python_stderr!r}")
            lines.append(f"     native stderr: {self.native_stderr!r}")
        return "\n".join(lines)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _python_run(path: Path) -> tuple[str, str, int]:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "powang.py"),
            "--engine=vm",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPOSITORY_ROOT),
        timeout=120,
    )
    return completed.stdout or "", completed.stderr or "", completed.returncode


def compare_file(path: Path) -> Comparison:
    python_stdout, python_stderr, python_code = _python_run(path)
    try:
        native = run_native_file(path)
        return Comparison(
            path=path,
            python_stdout=python_stdout,
            python_stderr=python_stderr,
            python_code=python_code,
            native_stdout=native.stdout,
            native_stderr=native.stderr,
            native_code=native.returncode,
        )
    except PowangError as error:
        return Comparison(
            path=path,
            python_stdout=python_stdout,
            python_stderr=python_stderr,
            python_code=python_code,
            native_stdout=str(error) + "\n",
            native_stderr="",
            native_code=1,
        )
    except NativeBuildError as error:
        return Comparison(
            path=path,
            python_stdout=python_stdout,
            python_stderr=python_stderr,
            python_code=python_code,
            native_stdout="",
            native_stderr="",
            native_code=1,
            error=f"native build error: {error}",
        )


def collect_programs(
    corpora: Iterable[Path], examples: Iterable[Path],
) -> list[Path]:
    programs: list[Path] = []
    for corpus in corpora:
        for path in sorted(corpus.rglob("*.po")):
            if "fixtures" in path.parts:
                continue
            programs.append(path)
    for example in examples:
        if example.is_file():
            programs.append(example)
        else:
            programs.extend(sorted(example.glob("*.po")))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in programs:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def run_fuzz(
    seed: int,
    count: int,
    *,
    fail_fast: bool = False,
    as_json: bool = False,
) -> int:
    import random
    import tempfile

    from ..fuzz import generate_program

    ensure_runtime()
    rng = random.Random(seed)
    results: list[Comparison] = []
    with tempfile.TemporaryDirectory(
        prefix="powang-native-fuzz-",
    ) as directory:
        root = Path(directory)
        for index in range(count):
            source = generate_program(rng)
            path = root / f"fuzz_{index:04d}.po"
            path.write_text(source, encoding="utf-8", newline="\n")
            result = compare_file(path)
            results.append(result)
            if not as_json:
                print(result.report())
            if not result.equal and fail_fast:
                break
    if as_json:
        print(json.dumps({
            "seed": seed,
            "requested": count,
            "total": len(results),
            "passed": sum(1 for item in results if item.equal),
            "failed": sum(1 for item in results if not item.equal),
        }, indent=2))
    return 0 if all(item.equal for item in results) else 1


def run(
    corpora: Sequence[Path] = (),
    examples: Sequence[Path] = (),
    *,
    fail_fast: bool = False,
    as_json: bool = False,
    fuzz: bool = False,
    seed: int = 1,
    count: int = 100,
) -> int:
    if fuzz:
        return run_fuzz(
            seed, count, fail_fast=fail_fast, as_json=as_json)
    ensure_runtime()
    programs = collect_programs(corpora, examples)
    if not programs:
        print("no programs selected", file=sys.stderr)
        return 2
    results: list[Comparison] = []
    for path in programs:
        result = compare_file(path)
        results.append(result)
        if not as_json:
            print(result.report())
        if not result.equal and fail_fast:
            break
    if as_json:
        print(json.dumps({
            "total": len(results),
            "passed": sum(1 for item in results if item.equal),
            "failed": sum(1 for item in results if not item.equal),
            "programs": [
                {
                    "path": str(item.path),
                    "equal": item.equal,
                    "python_code": item.python_code,
                    "native_code": item.native_code,
                    "error": item.error,
                }
                for item in results
            ],
        }, indent=2))
    return 0 if all(item.equal for item in results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="python -m src.vm.native.differential",
        description="Compare the Python VM and the native runtime.",
    )
    parser.add_argument(
        "--corpus", action="append", default=[], type=Path,
        help="corpus directory, may be repeated",
    )
    parser.add_argument(
        "--examples", action="append", default=[], type=Path,
        help="example file or directory, may be repeated",
    )
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fuzz", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--count", type=int, default=100)
    arguments = parser.parse_args(argv)
    return run(
        arguments.corpus,
        arguments.examples,
        fail_fast=arguments.fail_fast,
        as_json=arguments.json,
        fuzz=arguments.fuzz,
        seed=arguments.seed,
        count=arguments.count,
    )


if __name__ == "__main__":
    raise SystemExit(main())
