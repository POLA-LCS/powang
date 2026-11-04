"""REPL characterization: piped input is interpreted line by line."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import assert_no_traceback, run_repl  # noqa: E402


class ReplTests(unittest.TestCase):
    def test_assignment_then_read_echoes_values(self) -> None:
        result = run_repl(["x := 5;", "x;", "exit"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Powang X REPL", result.stdout)
        self.assertIn("5", result.stdout)
        self.assertEqual(result.lines.count("5"), 2)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)

    def test_expression_is_echoed(self) -> None:
        result = run_repl(["2 + 3;", "exit"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("5", result.stdout)
        self.assertIn("5", result.lines)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)

    def test_exit_terminates_input_processing(self) -> None:
        result = run_repl(["exit", "output(99);"])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("99", result.stdout)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)

    def test_piped_repl_does_not_print_prompts(self) -> None:
        result = run_repl(["x := 1;", "exit"])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(">>> ", result.stdout)
        self.assertIn("1", result.stdout)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


if __name__ == "__main__":
    unittest.main()
