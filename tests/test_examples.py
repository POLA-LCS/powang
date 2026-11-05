"""Characterization tests for the documented example programs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ROOT, assert_no_traceback, run_file  # noqa: E402


class VariablesExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_file(ROOT / "examples" / "variables.po")

    def test_expected_lines(self) -> None:
        expected = [
            "<int: undefined>",
            "Holaaa",
            "[10, 20, 30]",
            "2 -> int",
            "2.0 -> num",
            "25 -> str",
            "Weak: nova",
            "Weak: Holaaa",
            "Weak: nova",
            "6.9",
        ]
        self.assertEqual(self.result.lines, expected)

    def test_documented_values(self) -> None:
        output = self.result.stdout
        self.assertIn("Holaaa", output)
        self.assertIn("[10, 20, 30]", output)
        self.assertIn("<int: undefined>", output)
        self.assertIn("2 -> int", output)
        self.assertIn("2.0 -> num", output)
        self.assertIn("25 -> str", output)
        self.assertIn("Weak: Holaaa", output)
        self.assertTrue(output.endswith("6.9"))

    def test_no_diagnostics(self) -> None:
        self.assertEqual(self.result.stderr, "")
        self.assertNotIn("[ERROR]", self.result.stdout)
        assert_no_traceback(self, self.result)


class FunctionsExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_file(ROOT / "examples" / "functions.po")

    def test_output_is_exactly_two_overloads(self) -> None:
        self.assertEqual(self.result.lines, ["21", "21.5"])

    def test_integer_overload(self) -> None:
        self.assertIn("21", self.result.lines)

    def test_number_overload(self) -> None:
        self.assertIn("21.5", self.result.lines)

    def test_no_diagnostics(self) -> None:
        self.assertEqual(self.result.stderr, "")
        self.assertNotIn("[ERROR]", self.result.stdout)
        assert_no_traceback(self, self.result)


class ArithmeticsExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_file(ROOT / "examples" / "arithmetics.po")

    def test_expected_lines(self) -> None:
        expected = [
            "10",
            "4",
            "21",
            "2",
            "nova",
            "2.5",
            "3.5",
            "2",
            "true",
            "true",
            "false",
            "ababab",
            "[ab, cd]",
            "[a, b, c]",
            "[1, 2, 3, 4]",
            "[1, 2]",
            "[[1, 2], [3, 4]]",
        ]
        self.assertEqual(self.result.lines, expected)

    def test_documented_values(self) -> None:
        lines = self.result.lines
        self.assertEqual(lines[0], "10")
        self.assertEqual(lines[2], "21")
        self.assertEqual(lines[3], "2")
        self.assertEqual(lines[4], "nova")
        self.assertEqual(lines[5], "2.5")
        self.assertEqual(lines[6], "3.5")
        self.assertEqual(lines[11], "ababab")
        self.assertEqual(lines[12], "[ab, cd]")
        self.assertEqual(lines[13], "[a, b, c]")
        self.assertEqual(lines[14], "[1, 2, 3, 4]")
        self.assertEqual(lines[15], "[1, 2]")
        self.assertEqual(lines[16], "[[1, 2], [3, 4]]")

    def test_no_diagnostics(self) -> None:
        self.assertEqual(self.result.stderr, "")
        self.assertNotIn("[ERROR]", self.result.stdout)
        assert_no_traceback(self, self.result)


class AllExamplesTests(unittest.TestCase):
    """Every example is a runnable showcase, not just the three original ones."""

    def test_every_example_runs_cleanly(self) -> None:
        examples = sorted((ROOT / "examples").glob("*.po"))
        self.assertGreaterEqual(len(examples), 10)
        for example in examples:
            with self.subTest(example=example.name):
                result = run_file(example)
                self.assertEqual(result.returncode, 0, msg=result.combined)
                self.assertNotIn("[ERROR]", result.stdout)
                self.assertNotIn("Traceback", result.combined)


if __name__ == "__main__":
    unittest.main()
