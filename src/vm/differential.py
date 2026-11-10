"""Differential harness for the tree walker and the bytecode VM.

The harness runs one source file twice in separate processes and compares the
observable result: standard output, standard error and the exit code. Timing is
recorded for reports but never used for equality.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POWANG = ROOT / "powang.py"


@dataclass
class EngineResult:
    stdout: str
    stderr: str
    returncode: int
    seconds: float


@dataclass
class DiffResult:
    source: str
    tree: EngineResult
    vm: EngineResult
    mismatches: list[str] = field(default_factory=list)

    @property
    def equal(self) -> bool:
        return not self.mismatches

    def report(self) -> str:
        lines = ["differential result: " + ("equal" if self.equal else "mismatch")]
        if self.mismatches:
            for mismatch in self.mismatches:
                lines.append("  - " + mismatch)
        lines.append(f"tree exit={self.tree.returncode} time={self.tree.seconds:.3f}s")
        lines.append(f"vm   exit={self.vm.returncode} time={self.vm.seconds:.3f}s")
        return "\n".join(lines)


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _run_engine(path: Path, engine: str, cwd: Path,
                extra_args: list[str] | None = None) -> EngineResult:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    command = [sys.executable, str(POWANG), f"--engine={engine}", str(path)]
    if extra_args:
        command.extend(extra_args)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        env=env,
        check=False,
        timeout=120,
    )
    elapsed = time.perf_counter() - started
    return EngineResult(
        _normalize(completed.stdout.decode("utf-8", errors="replace")),
        _normalize(completed.stderr.decode("utf-8", errors="replace")),
        completed.returncode,
        elapsed,
    )


def compare_source(source: str, *, name: str = "program.po",
                   extra_args: list[str] | None = None) -> DiffResult:
    with tempfile.TemporaryDirectory(prefix="powang-diff-") as directory:
        root = Path(directory)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="\n")
        return compare_file(path, extra_args=extra_args)


def compare_file(path: Path | str, *,
                 extra_args: list[str] | None = None) -> DiffResult:
    resolved = Path(path).resolve()
    tree = _run_engine(resolved, "tree", resolved.parent, extra_args)
    vm = _run_engine(resolved, "vm", resolved.parent, extra_args)
    mismatches: list[str] = []
    if tree.stdout != vm.stdout:
        mismatches.append("stdout differs")
    if tree.stderr != vm.stderr:
        mismatches.append("stderr differs")
    if tree.returncode != vm.returncode:
        mismatches.append("exit code differs")
    return DiffResult(
        source=str(resolved),
        tree=tree,
        vm=vm,
        mismatches=mismatches,
    )


def compare_directory(directory: Path | str, *,
                      pattern: str = "*.po") -> list[DiffResult]:
    results: list[DiffResult] = []
    for path in sorted(Path(directory).rglob(pattern)):
        results.append(compare_file(path))
    return results


@dataclass
class SuiteResult:
    tree_returncode: int
    vm_returncode: int
    tree_tail: str
    vm_tail: str

    @property
    def equal(self) -> bool:
        return self.tree_returncode == self.vm_returncode

    def report(self) -> str:
        lines = [
            "suite result: " + ("equal" if self.equal else "mismatch"),
            f"  tree exit={self.tree_returncode}",
            f"  vm   exit={self.vm_returncode}",
        ]
        return "\n".join(lines)


def compare_suite(directory: Path | str) -> SuiteResult:
    """Run the unittest suite on both engines and compare the exit codes."""
    root = Path(directory)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    tails: dict[str, str] = {}
    codes: dict[str, int] = {}
    for engine in ("tree", "vm"):
        run_env = dict(env)
        run_env["POWANG_ENGINE"] = engine
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(root), "-q"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
            env=run_env,
            check=False,
            timeout=1800,
        )
        text = _normalize(completed.stdout.decode("utf-8", errors="replace"))
        codes[engine] = completed.returncode
        tails[engine] = "\n".join(text.splitlines()[-8:])
    return SuiteResult(codes["tree"], codes["vm"], tails["tree"], tails["vm"])


def main(argv: list[str] | None = None) -> int:
    """Command line entry for ``python -m src.vm.differential``."""
    import argparse

    parser = argparse.ArgumentParser(description="Powang engine differential runner")
    parser.add_argument("--examples", metavar="DIR")
    parser.add_argument("--corpus", metavar="DIR")
    parser.add_argument("--suite", metavar="DIR")
    parser.add_argument("--fuzz", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", metavar="DIR")
    parser.add_argument("--fail-fast", action="store_true")
    arguments = parser.parse_args(argv)

    failed = False
    if arguments.suite:
        result = compare_suite(arguments.suite)
        print(result.report())
        if not result.equal:
            print("--- tree tail ---")
            print(result.tree_tail)
            print("--- vm tail ---")
            print(result.vm_tail)
            failed = True
    for label, directory in (
        ("examples", arguments.examples),
        ("corpus", arguments.corpus),
    ):
        if not directory:
            continue
        for result in compare_directory(directory):
            if result.equal:
                print(f"{label}: {result.source}: equal")
                continue
            failed = True
            print(f"{label}: {result.report()}")
            if arguments.fail_fast:
                break
    if arguments.fuzz:
        from .fuzz import run_fuzz
        report = run_fuzz(
            arguments.seed, arguments.count,
            fail_directory=arguments.output,
            fail_fast=arguments.fail_fast,
        )
        print(report.report())
        if not report.ok:
            failed = True
    if not any((arguments.suite, arguments.examples, arguments.corpus, arguments.fuzz)):
        parser.print_help()
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main(_sys.argv[1:]))
