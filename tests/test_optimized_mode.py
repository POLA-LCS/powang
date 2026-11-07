"""Language checks must survive ``python -O``."""

from __future__ import annotations

import unittest

from helpers import run_source


class OptimizedModeTests(unittest.TestCase):
    def test_undefined_variable_is_rejected_under_o(self) -> None:
        result = run_source("print(nope);\n", optimize=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("IDENTIFIER ERROR", result.combined)

    def test_invalid_export_is_rejected_under_o(self) -> None:
        result = run_source("export 1;\n", optimize=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("SYNTAX ERROR", result.combined)

    def test_normal_program_still_runs_under_o(self) -> None:
        result = run_source('print("ok");\n', optimize=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")


if __name__ == "__main__":
    unittest.main()
