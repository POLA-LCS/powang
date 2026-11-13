"""Native benchmark runner tests."""

from __future__ import annotations

import unittest

from src.vm.native.bench import run_native_benchmarks
from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from tests.helpers import ROOT


class NativeBenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_benchmark_runner_reports_timings(self) -> None:
        records = run_native_benchmarks(
            [ROOT / "native" / "benches" / "loop.po"], runs=1,
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["runs"], 1)
        self.assertGreater(record["native_seconds"], 0.0)
        self.assertGreater(record["python_seconds"], 0.0)
        self.assertGreater(record["speedup"], 0.0)


if __name__ == "__main__":
    unittest.main()
