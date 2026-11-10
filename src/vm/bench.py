"""Benchmark corpus and runner for the bytecode VM.

The corpus covers the areas named by the performance plan: arithmetic loops,
recursion, containers, strings, objects, traits, errors, tasks and modules.
Timing is reported for regression tracking, never used for correctness.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POWANG = ROOT / "powang.py"


BENCHMARKS: dict[str, str] = {
    "arithmetic": """\
total := 0;
for index >> 0 >> 100000 {
    total += index * 2;
}
print(total);
print("\\n");
""",
    "recursion": """\
fun fib(value: int): int {
    if value < 2 {
        return value;
    }
    return fib(value - 1) + fib(value - 2);
}
print(fib(20));
print("\\n");
""",
    "containers": """\
values := [];
for index >> 0 >> 2000 {
    values = values + [index];
}
total := 0;
for value >> values {
    total += value;
}
print(total);
print("\\n");
""",
    "strings": """\
text := "";
for index >> 0 >> 2000 {
    text = text + "x";
}
print(size(text));
print("\\n");
""",
    "objects": """\
type Point {
    | x: int;
    | y: int;
    fun constructor(px: int, py: int): Point {
        this.x = px;
        this.y = py;
    }
    fun this.sum(other: Point): int {
        return this.x + other.x + this.y + other.y;
    }
}
total := 0;
for index >> 0 >> 2000 {
    first := Point.[index, index];
    second := Point.[1, 2];
    total += first.sum(second);
}
print(total);
print("\\n");
""",
    "errors": """\
total := 0;
for index >> 0 >> 2000 {
    try {
        if index == -1 {
            error("unreachable");
        }
        total += 1;
    } catch problem {
        total -= 1;
    }
}
print(total);
print("\\n");
""",
    "tasks": """\
async fun work(value: int): int >> value * 2;
total := 0;
for index >> 0 >> 500 {
    total += await work(index);
}
print(total);
print("\\n");
""",
}


@dataclass
class BenchResult:
    name: str
    engine: str
    seconds: float
    returncode: int
    stdout: str


def _run(source: str, engine: str, runs: int) -> BenchResult:
    with tempfile.TemporaryDirectory(prefix="powang-bench-") as directory:
        path = Path(directory) / "bench.po"
        path.write_text(source, encoding="utf-8", newline="\n")
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        best = None
        output = ""
        returncode = 0
        for _ in range(max(1, runs)):
            started = time.perf_counter()
            completed = subprocess.run(
                [sys.executable, str(POWANG), f"--engine={engine}", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(ROOT),
                env=env,
                check=False,
                timeout=300,
            )
            elapsed = time.perf_counter() - started
            returncode = completed.returncode
            output = completed.stdout.decode("utf-8", errors="replace")
            if best is None or elapsed < best:
                best = elapsed
        return BenchResult("", engine, best or 0.0, returncode, output)


def run_benchmarks(names: list[str] | None = None, runs: int = 3,
                   engines: tuple[str, ...] = ("tree", "vm")) -> list[BenchResult]:
    selected = names or list(BENCHMARKS)
    results: list[BenchResult] = []
    for name in selected:
        source = BENCHMARKS[name]
        for engine in engines:
            result = _run(source, engine, runs)
            result.name = name
            results.append(result)
    return results


def format_results(results: list[BenchResult]) -> str:
    by_name: dict[str, dict[str, BenchResult]] = {}
    for result in results:
        by_name.setdefault(result.name, {})[result.engine] = result
    lines = ["benchmark results"]
    lines.append(f"{'name':<14}{'tree':>10}{'vm':>10}{'ratio':>10}")
    for name, engines in by_name.items():
        tree = engines.get("tree")
        vm = engines.get("vm")
        tree_time = f"{tree.seconds:.3f}" if tree else "-"
        vm_time = f"{vm.seconds:.3f}" if vm else "-"
        ratio = "-"
        if tree and vm and tree.seconds > 0:
            ratio = f"{vm.seconds / tree.seconds:.2f}x"
        lines.append(f"{name:<14}{tree_time:>10}{vm_time:>10}{ratio:>10}")
        if tree and vm and tree.stdout != vm.stdout:
            lines.append(f"  warning: output mismatch in {name}")
    return "\n".join(lines)
