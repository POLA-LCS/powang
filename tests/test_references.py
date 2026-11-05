"""Reference parameter tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class ReferenceTests(unittest.TestCase):
    def test_reference_parameter_mutates_caller(self) -> None:
        result = run_source(
            "fun increment(value: &int) { value += 1; }\n"
            "x := 10;\n"
            "increment(&x);\n"
            "print(x);\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["11"])

    def test_swap_through_references(self) -> None:
        result = run_source(
            "fun swap(a: &int, b: &int) {\n"
            "    temp := a;\n"
            "    a = b;\n"
            "    b = temp;\n"
            "}\n"
            "left := 1;\n"
            "right := 2;\n"
            "swap(&left, &right);\n"
            "print(left); print(\" \"); print(right);\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["2 1"])

    def test_reading_through_reference(self) -> None:
        result = run_source(
            "fun doubled(value: &int): int { return value * 2; }\n"
            "x := 21;\n"
            "print(doubled(&x));\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["42"])

    def test_reference_to_constant_is_rejected(self) -> None:
        result = run_source(
            "fun increment(value: &int) { value += 1; }\n"
            "limit: int! = 5;\n"
            "increment(&limit);\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("REFERENCE ERROR", result.combined)
        self.assertIn("constant", result.combined)

    def test_reference_cannot_be_stored(self) -> None:
        result = run_source(
            "x := 1;\n"
            "y := &x;\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("references cannot be stored", result.combined)

    def test_missing_ampersand_is_rejected(self) -> None:
        result = run_source(
            "fun increment(value: &int) { value += 1; }\n"
            "x := 1;\n"
            "increment(x);\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("No overload", result.combined)


if __name__ == "__main__":
    unittest.main()
