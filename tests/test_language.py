"""Characterization tests for language semantics that P1 to P3 must preserve."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import assert_no_traceback, run_source  # noqa: E402


class LanguageTestCase(unittest.TestCase):
    def assert_program_output(self, source: str, expected: str) -> None:
        result = run_source(source)
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)

    def assert_program_lines(self, source: str, expected: list[str]) -> None:
        result = run_source(source)
        self.assertEqual(result.lines, expected)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


class ArithmeticTests(LanguageTestCase):
    def test_documented_arithmetic_values(self) -> None:
        source = (
            'output(7 + 3); output("\\n");\n'
            'output(7 - 3); output("\\n");\n'
            'output(7 * 3); output("\\n");\n'
            'output(7 / 3); output("\\n");\n'
            'output(7 / 0); output("\\n");\n'
            'output(1.5 + 1); output("\\n");\n'
            'output(7.0 / 2.0); output("\\n");\n'
            'output(2 + 0.5); output("\\n");\n'
            'output(2 +: 0.5); output("\\n");\n'
            'output("ab" * 3); output("\\n");\n'
            'output("abcd" / 2); output("\\n");\n'
            'output("a,b,c" / ","); output("\\n");\n'
            'output([1 2] + [3 4]); output("\\n");\n'
            'output([1 2 3 4] - 2); output("\\n");\n'
            'output(2 / [1 2 3 4]); output("\\n");\n'
            'output(-5); output("\\n");\n'
            'output([-]123); output("\\n");\n'
        )
        result = run_source(source)
        self.assertEqual(
            result.lines,
            [
                "10",
                "4",
                "21",
                "2",
                "nova",
                "2.5",
                "3.5",
                "2",
                "2.5",
                "ababab",
                "[ab, cd]",
                "[a, b, c]",
                "[1, 2, 3, 4]",
                "[1, 2]",
                "[[1, 2], [3, 4]]",
                "-5",
                "321",
            ],
        )
        self.assertEqual(result.lines[0], "10")
        self.assertEqual(result.lines[3], "2")
        self.assertEqual(result.lines[4], "nova")
        self.assertEqual(result.lines[9], "ababab")
        self.assertEqual(result.lines[10], "[ab, cd]")
        self.assertEqual(result.lines[12], "[1, 2, 3, 4]")
        self.assertEqual(result.lines[13], "[1, 2]")
        self.assertEqual(result.lines[14], "[[1, 2], [3, 4]]")
        self.assertNotIn("[ERROR]", result.stdout)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)

    def test_integer_division_is_floor_and_zero_returns_nova(self) -> None:
        self.assert_program_lines(
            'output(7 / 3); output("\\n"); output(7 / 0); output("\\n");\n',
            ["2", "nova"],
        )

    def test_boolean_arithmetic(self) -> None:
        source = (
            'output(true + true); output("\\n");\n'
            'output(true - false); output("\\n");\n'
            'output(true * false); output("\\n");\n'
        )
        self.assert_program_lines(source, ["true", "true", "false"])


class ComparisonTests(LanguageTestCase):
    def test_comparison_operators(self) -> None:
        source = (
            'output(1 < 2); output("\\n");\n'
            'output(2 <= 2); output("\\n");\n'
            'output(3 > 2); output("\\n");\n'
            'output(3 >= 4); output("\\n");\n'
            'output(2 == 2); output("\\n");\n'
            'output(2 != 2); output("\\n");\n'
            'output(1 :: integer); output("\\n");\n'
            'output("a" !: integer); output("\\n");\n'
        )
        result = run_source(source)
        self.assertEqual(
            result.lines,
            ["true", "true", "true", "false", "true", "false", "true", "true"],
        )
        self.assertEqual(result.lines[0], "true")
        self.assertEqual(result.lines[3], "false")
        self.assertEqual(result.lines[5], "false")
        self.assertEqual(result.lines[6], "true")
        self.assertEqual(result.lines[7], "true")
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


class ControlFlowTests(LanguageTestCase):
    def test_if_else_inside_c_style_loop(self) -> None:
        source = (
            "for i := 0; i < 5; i += 1 {\n"
            '    if i < 3 { output(i); } else { output("x"); }\n'
            "}\n"
            'output("\\n");\n'
        )
        self.assert_program_output(source, "012xx\n")

    def test_c_style_for_accumulates(self) -> None:
        source = (
            "total := 0;\n"
            "for i := 0; i < 5; i += 1 { total += i; }\n"
            'output(total); output("\\n");\n'
        )
        self.assert_program_output(source, "10\n")

    def test_else_if_chain(self) -> None:
        source = (
            "n := 2;\n"
            'if n == 1 { output("one"); }\n'
            'else if n == 2 { output("two"); }\n'
            'else { output("other"); }\n'
            'output("\\n");\n'
        )
        self.assert_program_output(source, "two\n")


class ForEachTests(LanguageTestCase):
    def test_typed_bare_and_filtered_forms(self) -> None:
        source = (
            "arr := [10 20 30];\n"
            'for i1: integer >> arr { output(i1); output(" "); }\n'
            'output("\\n");\n'
            'for i2 >> arr { output(i2); output(" "); }\n'
            'output("\\n");\n'
            'for i3 >> arr if i3 > 15 { output(i3); output(" "); }\n'
            'output("\\n");\n'
        )
        result = run_source(source)
        self.assertEqual(result.lines, ["10 20 30 ", "10 20 30 ", "20 30 "])
        self.assertEqual(result.lines[0], "10 20 30 ")
        self.assertEqual(result.lines[1], "10 20 30 ")
        self.assertEqual(result.lines[2], "20 30 ")
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


class FunctionTests(LanguageTestCase):
    def test_recursive_factorial(self) -> None:
        source = (
            "fun fact(n: integer): integer {\n"
            "    if n <= 1 { return 1; }\n"
            "    return n * fact(n - 1);\n"
            "}\n"
            'output(fact(5)); output("\\n");\n'
        )
        self.assert_program_output(source, "120\n")

    def test_overload_selection(self) -> None:
        source = (
            "fun pick(a: integer, b: integer): integer { return a + b; }\n"
            "fun pick(a: integer, b: number): number { return a +: b; }\n"
            'output(pick(2, 3)); output("\\n");\n'
            'output(pick(20, 1.5)); output("\\n");\n'
        )
        self.assert_program_lines(source, ["5", "21.5"])

    def test_function_value_assignment_with_some_type(self) -> None:
        source = (
            "fun add(left: integer, right: integer): integer { return left + right; }\n"
            "f: some = add;\n"
            'output(typeof(f)); output("\\n");\n'
        )
        self.assert_program_output(source, "function\n")

    def test_function_value_assignment_with_inference(self) -> None:
        source = (
            "fun add(left: integer, right: integer): integer { return left + right; }\n"
            "g := add;\n"
            'output(typeof(g)); output("\\n");\n'
        )
        self.assert_program_output(source, "function\n")


class UserTypeTests(LanguageTestCase):
    def test_constructor_properties_and_method(self) -> None:
        source = (
            "type Point {\n"
            "    + x: integer;\n"
            "    - y: integer = 7;\n"
            "    + fun constructor(px: integer): Point { this.x = px; }\n"
            "    + fun sum(other: Point): integer { return this.x + other.x; }\n"
            "}\n"
            "p := [5] as Point;\n"
            "q: Point = 9;\n"
            'output(p.x); output(" "); output(p.sum(q)); output("\\n");\n'
        )
        result = run_source(source)
        self.assertEqual(result.stdout, "5 14\n")
        self.assertEqual(result.lines, ["5 14"])
        self.assertIn("5 14", result.stdout)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)

    def test_instance_method_can_mutate_property(self) -> None:
        source = (
            "type Counter {\n"
            "    + count: integer = 0;\n"
            "    + fun bump(): integer { this.count += 1; return this.count; }\n"
            "}\n"
            "a := [] as Counter;\n"
            'output(a.count); output(" ");\n'
            "a.bump();\n"
            'output(a.count); output("\\n");\n'
        )
        self.assert_program_output(source, "0 1\n")


class MapTests(LanguageTestCase):
    def test_map_literal_and_non_destructive_concat(self) -> None:
        source = (
            'm := ["a" >> 1, "b" >> 2];\n'
            'joined := m + ["c" >> 3];\n'
            'output(size(m)); output(" "); output(size(joined)); output("\\n");\n'
            'output(m["a"]); output(" "); output(joined["c"]); output("\\n");\n'
        )
        result = run_source(source)
        self.assertEqual(result.lines, ["2 3", "1 3"])
        self.assertEqual(result.lines[0], "2 3")
        self.assertEqual(result.lines[1], "1 3")
        self.assertIn("2 3", result.stdout)
        self.assertIn("1 3", result.stdout)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


class StringTests(LanguageTestCase):
    def test_escapes_and_unicode(self) -> None:
        source = (
            'output("café ñ 🎉\\n");\n'
            'output("tab\\there\\n");\n'
            'output("quote\\"backslash\\\\\\n");\n'
            'output("null:[\\0]\\n");\n'
            'output("unknown:\\q\\n");\n'
        )
        expected = (
            "café ñ 🎉\n"
            "tab\there\n"
            'quote"backslash\\\n'
            "null:[\x00]\n"
            "unknown:\\q\n"
        )
        result = run_source(source)
        self.assertEqual(result.stdout, expected)
        self.assertIn("café", result.stdout)
        self.assertIn("ñ", result.stdout)
        self.assertIn("🎉", result.stdout)
        self.assertIn("\t", result.stdout)
        self.assertIn("\x00", result.stdout)
        self.assertIn("\\q", result.stdout)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


class VariableTests(LanguageTestCase):
    def test_typed_inferred_weak_and_const(self) -> None:
        source = (
            "a: integer = 2.5;\n"
            "b: number = 2;\n"
            'c := "hi";\n'
            "w: @string = nova;\n"
            'w = "value";\n'
            "k: number!;\n"
            "k = 6.9;\n"
            'output(a); output(" "); output(b); output(" ");\n'
            'output(c); output(" "); output(w); output(" "); output(k); output("\\n");\n'
        )
        self.assert_program_output(source, "2 2.0 hi value 6.9\n")


if __name__ == "__main__":
    unittest.main()
