"""The --engine=native command line integration."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from tests.helpers import ROOT, run_file, run_source, write_po


class NativeEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_native_engine_runs_a_file(self) -> None:
        result = run_source("print(1 + 2);\n", engine="native")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "3")
        self.assertEqual(result.stderr, "")

    def test_native_engine_error_uses_stdout(self) -> None:
        result = run_source("missing;\n", engine="native")
        self.assertEqual(result.returncode, 1)
        self.assertIn("IDENTIFIER ERROR", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_native_engine_imports(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="powang-native-engine-",
        ) as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/math.po",
                "module math;\n"
                "export fun add(a: int, b: int): int >> a + b;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/math.po" as m;\n'
                "print(m.add(2, 3));\n",
            )
            result = run_file(main, engine="native")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "5")

    def test_native_engine_rejects_ast_output(self) -> None:
        result = run_source(
            "print(1);\n", engine="native",
            args=("--ast", "out.json"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("not supported", result.stdout)

    def test_native_differential_module(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="powang-native-diff-",
        ) as directory:
            path = write_po(
                Path(directory), "program.po",
                "print(2 * 3);\n",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.vm.native.differential",
                    "--examples",
                    str(path),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"failed": 0', completed.stdout)


if __name__ == "__main__":
    unittest.main()
