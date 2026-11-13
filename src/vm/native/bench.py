"""Benchmark runner for the native engine.

The Python VM is the reference baseline. Each program is compiled to a native
executable once, then both engines run it ``runs`` times. The median wall time
is reported so a single slow startup does not dominate the result.
"""

from __future__ import annotations

import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from .loader import compile_image
from .session import compile_native_file


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BENCHMARKS = REPOSITORY_ROOT / "native" / "benches"


def _run_python(path: Path, runs: int) -> list[float]:
    timings: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "powang.py"),
                "--engine=vm",
                str(path),
            ],
            cwd=str(REPOSITORY_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        timings.append(time.perf_counter() - started)
    return timings


def run_native_benchmarks(
    programs: Sequence[Path] | None = None,
    *,
    runs: int = 3,
) -> list[dict[str, object]]:
    """Run the native and Python VM benchmarks and return median timings."""
    selected = list(programs or ())
    if not selected:
        selected = sorted(DEFAULT_BENCHMARKS.glob("*.po"))
    if not selected:
        raise FileNotFoundError("no benchmark programs found")
    count = max(1, runs)
    records: list[dict[str, object]] = []
    for path in selected:
        program_path = Path(path)
        session = compile_native_file(program_path)
        program = compile_image(
            session.image, bundle=session.bundle, use_cache=False,
        )
        try:
            native_timings: list[float] = []
            for _ in range(count):
                started = time.perf_counter()
                subprocess.run(
                    [str(program.executable)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                )
                native_timings.append(time.perf_counter() - started)
            python_timings = _run_python(program_path, count)
        finally:
            program.cleanup()
        native_median = statistics.median(native_timings)
        python_median = statistics.median(python_timings)
        records.append({
            "program": str(program_path),
            "runs": count,
            "python_seconds": python_median,
            "native_seconds": native_median,
            "speedup": (
                python_median / native_median
                if native_median > 0 else 0.0
            ),
        })
    return records
