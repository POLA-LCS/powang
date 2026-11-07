"""Logical operators must not evaluate an unnecessary right operand."""

from __future__ import annotations

import unittest

from helpers import run_source


class ShortCircuitTests(unittest.TestCase):
    def test_and_skips_rhs(self) -> None:
        result = run_source(
            "fun bump(counter: &int) { counter += 1; }\n"
            "c := 0;\n"
            "false && bump(&c);\n"
            'print(c); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "0\n")

    def test_or_skips_rhs(self) -> None:
        result = run_source(
            "fun bump(counter: &int) { counter += 1; }\n"
            "c := 0;\n"
            "true || bump(&c);\n"
            'print(c); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "0\n")

    def test_coalesce_skips_rhs_when_left_is_present(self) -> None:
        result = run_source(
            "fun bump(counter: &int) { counter += 1; }\n"
            "c := 0;\n"
            "5 ?? bump(&c);\n"
            'print(c); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "0\n")

    def test_coalesce_evaluates_rhs_when_left_is_nova(self) -> None:
        result = run_source(
            "fun bump(counter: &int) { counter += 1; }\n"
            "c := 0;\n"
            "nova ?? bump(&c);\n"
            'print(c); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "1\n")


if __name__ == "__main__":
    unittest.main()
