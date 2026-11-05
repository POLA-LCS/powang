"""Characterization tests for language semantics that P1 to P3 must preserve."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import assert_no_traceback, run_source, run_source_with_input  # noqa: E402


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
            'print(7 + 3); print("\\n");\n'
            'print(7 - 3); print("\\n");\n'
            'print(7 * 3); print("\\n");\n'
            'print(7 / 3); print("\\n");\n'
            'print(7 / 0); print("\\n");\n'
            'print(1.5 + 1); print("\\n");\n'
            'print(7.0 / 2.0); print("\\n");\n'
            'print(2 + 0.5); print("\\n");\n'
            'print(2 +: 0.5); print("\\n");\n'
            'print("ab" * 3); print("\\n");\n'
            'print("abcd" / 2); print("\\n");\n'
            'print("a,b,c" / ","); print("\\n");\n'
            'print([1 2] + [3 4]); print("\\n");\n'
            'print([1 2 3 4] - 2); print("\\n");\n'
            'print(2 / [1 2 3 4]); print("\\n");\n'
            'print(-5); print("\\n");\n'
            'print([-]123); print("\\n");\n'
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
            'print(7 / 3); print("\\n"); print(7 / 0); print("\\n");\n',
            ["2", "nova"],
        )

    def test_boolean_arithmetic(self) -> None:
        source = (
            'print(true + true); print("\\n");\n'
            'print(true - false); print("\\n");\n'
            'print(true * false); print("\\n");\n'
        )
        self.assert_program_lines(source, ["true", "true", "false"])


class ComparisonTests(LanguageTestCase):
    def test_comparison_operators(self) -> None:
        source = (
            'print(1 < 2); print("\\n");\n'
            'print(2 <= 2); print("\\n");\n'
            'print(3 > 2); print("\\n");\n'
            'print(3 >= 4); print("\\n");\n'
            'print(2 == 2); print("\\n");\n'
            'print(2 != 2); print("\\n");\n'
            'print(1 :: int); print("\\n");\n'
            'print("a" !: int); print("\\n");\n'
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
            '    if i < 3 { print(i); } else { print("x"); }\n'
            "}\n"
            'print("\\n");\n'
        )
        self.assert_program_output(source, "012xx\n")

    def test_c_style_for_accumulates(self) -> None:
        source = (
            "total := 0;\n"
            "for i := 0; i < 5; i += 1 { total += i; }\n"
            'print(total); print("\\n");\n'
        )
        self.assert_program_output(source, "10\n")

    def test_else_if_chain(self) -> None:
        source = (
            "n := 2;\n"
            'if n == 1 { print("one"); }\n'
            'else if n == 2 { print("two"); }\n'
            'else { print("other"); }\n'
            'print("\\n");\n'
        )
        self.assert_program_output(source, "two\n")


class ForEachTests(LanguageTestCase):
    def test_typed_bare_and_filtered_forms(self) -> None:
        source = (
            "arr := [10 20 30];\n"
            'for i1: int >> arr { print(i1); print(" "); }\n'
            'print("\\n");\n'
            'for i2 >> arr { print(i2); print(" "); }\n'
            'print("\\n");\n'
            'for i3 >> arr if i3 > 15 { print(i3); print(" "); }\n'
            'print("\\n");\n'
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
            "fun fact(n: int): int {\n"
            "    if n <= 1 { return 1; }\n"
            "    return n * fact(n - 1);\n"
            "}\n"
            'print(fact(5)); print("\\n");\n'
        )
        self.assert_program_output(source, "120\n")

    def test_expression_bodied_function(self) -> None:
        source = (
            "fun double(x: int): int >> x * 2;\n"
            "print(double(21));\n"
        )
        self.assert_program_output(source, "42")

    def test_overload_selection(self) -> None:
        source = (
            "fun pick(a: int, b: int): int { return a + b; }\n"
            "fun pick(a: int, b: num): num { return a +: b; }\n"
            'print(pick(2, 3)); print("\\n");\n'
            'print(pick(20, 1.5)); print("\\n");\n'
        )
        self.assert_program_lines(source, ["5", "21.5"])

    def test_function_value_assignment_with_some_type(self) -> None:
        source = (
            "fun add(left: int, right: int): int { return left + right; }\n"
            "f: some = add;\n"
            'print(typeof(f)); print("\\n");\n'
        )
        self.assert_program_output(source, "function\n")

    def test_function_value_assignment_with_inference(self) -> None:
        source = (
            "fun add(left: int, right: int): int { return left + right; }\n"
            "g := add;\n"
            'print(typeof(g)); print("\\n");\n'
        )
        self.assert_program_output(source, "function\n")


class UserTypeTests(LanguageTestCase):
    def test_constructor_properties_and_method(self) -> None:
        source = (
            "type Point {\n"
            "    + x: int;\n"
            "    - y: int = 7;\n"
            "    + fun constructor(px: int): Point { this.x = px; }\n"
            "    + fun sum(other: Point): int { return this.x + other.x; }\n"
            "}\n"
            "p := [5] as Point;\n"
            "q: Point = 9;\n"
            'print(p.x); print(" "); print(p.sum(q)); print("\\n");\n'
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
            "    + count: int = 0;\n"
            "    + fun bump(): int { this.count += 1; return this.count; }\n"
            "}\n"
            "a := [] as Counter;\n"
            'print(a.count); print(" ");\n'
            "a.bump();\n"
            'print(a.count); print("\\n");\n'
        )
        self.assert_program_output(source, "0 1\n")


class MapTests(LanguageTestCase):
    def test_map_literal_and_non_destructive_concat(self) -> None:
        source = (
            'm := ["a" >> 1, "b" >> 2];\n'
            'joined := m + ["c" >> 3];\n'
            'print(size(m)); print(" "); print(size(joined)); print("\\n");\n'
            'print(m["a"]); print(" "); print(joined["c"]); print("\\n");\n'
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
            'print("café ñ 🎉\\n");\n'
            'print("tab\\there\\n");\n'
            'print("quote\\"backslash\\\\\\n");\n'
            'print("null:[\\0]\\n");\n'
            'print("unknown:\\q\\n");\n'
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


class ArrayTypingTests(LanguageTestCase):
    def test_typed_array_declaration_and_index(self) -> None:
        source = "numbers: arr[int] = [1 2 3];\nprint(numbers[1]);\n"
        self.assert_program_output(source, "2")

    def test_bare_array_is_array_any(self) -> None:
        source = 'values: arr = [1 "two" true];\nprint(size(values));\n'
        self.assert_program_output(source, "3")

    def test_explicit_array_any_accepts_mixed_elements(self) -> None:
        source = 'values: arr[any] = [1 "two" true];\nprint(size(values));\n'
        self.assert_program_output(source, "3")

    def test_typed_array_rejects_mixed_elements(self) -> None:
        result = run_source('numbers: arr[int] = [1 "two"];\n')
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected arr[int]", result.combined)
        self.assertIn("arr[mixed]", result.combined)
        assert_no_traceback(self, result)

    def test_typed_array_function_parameter(self) -> None:
        source = (
            "fun first(values: arr[int]): int {\n"
            "    return values[0];\n"
            "}\n"
            "print(first([4 5 6]));\n"
        )
        self.assert_program_output(source, "4")

    def test_typed_array_index_assignment_rejects_wrong_type(self) -> None:
        result = run_source('numbers: arr[int] = [1 2];\nnumbers[0] = "x";\n')
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected int", result.combined)
        assert_no_traceback(self, result)

    def test_for_each_infers_element_type(self) -> None:
        source = (
            "numbers: arr[int] = [1 2 3];\n"
            "for value >> numbers { print(value); print(\" \"); }\n"
            "print(\"\\n\");\n"
        )
        self.assert_program_output(source, "1 2 3 \n")

    def test_for_each_rejects_wrong_iterator_type(self) -> None:
        source = (
            "numbers: arr[int] = [1 2];\n"
            "for value: str >> numbers { print(value); }\n"
        )
        result = run_source(source)
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected str", result.combined)
        assert_no_traceback(self, result)

    def test_nested_typed_array(self) -> None:
        source = (
            "nested: arr[arr[int]] = [[1 2]];\n"
            "for row >> nested { print(row[0]); }\n"
        )
        self.assert_program_output(source, "1")

    def test_array_cast_accepts_typed_annotation(self) -> None:
        source = (
            "values := [1 2 3];\n"
            "casted := values as arr[int];\n"
            "print(casted[1]);\n"
        )
        self.assert_program_output(source, "2")


class BuiltinRenameTests(LanguageTestCase):
    def test_print_and_format(self) -> None:
        source = 'print(format("{0}-{1}", "a", 2));\n'
        self.assert_program_output(source, "a-2")

    def test_inputf_prints_prompt_and_reads_receptor(self) -> None:
        source = 'value: str;\ninputf(value, "Name: ");\nprint(value);\n'
        result = run_source_with_input(source, "Ada\n")
        self.assertEqual(result.stdout, "Name: Ada")
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


class ModernSyntaxTests(LanguageTestCase):
    def test_trailing_commas(self) -> None:
        source = (
            "numbers := [1, 2, 3,];\n"
            "fun add(a: int, b: int = 0,): int { return a + b; }\n"
            'print(add(1, 2,),); print("\\n",);\n'
        )
        self.assert_program_output(source, "3\n")

    def test_block_comments_and_interpolation(self) -> None:
        source = (
            "#! block\ncomment !#\n"
            'name := "Ada";\n'
            'println($"Hello, {name}! {2 + 2}");\n'
        )
        self.assert_program_output(source, "Hello, Ada! 4\n")

    def test_range_loop(self) -> None:
        source = 'for i >> 0 >> 2 >> 6 { print(i); }\nprint("\\n");\n'
        self.assert_program_output(source, "024\n")

    def test_for_each_destructuring(self) -> None:
        source = (
            'pairs := ["a" >> 1, "b" >> 2];\n'
            'for [key: str, value: int] >> pairs { print($"{key}={value};"); }\n'
        )
        self.assert_program_output(source, "a=1;b=2;")

    def test_destructuring_and_references(self) -> None:
        source = (
            "pair := [1, 2];\n"
            "[a: int, b] := pair;\n"
            'print(a + b); print("\\n");\n'
            "[r:&, s] := pair;\n"
            "r = 10;\n"
            'print(pair[0]); print("\\n");\n'
        )
        self.assert_program_output(source, "3\n10\n")

    def test_safe_access_and_if_declaration(self) -> None:
        source = (
            "value: @str = nova;\n"
            'print(value ?? "default"); print("\\n");\n'
            'if name := value { print("yes"); } else { print("no"); }\n'
            'print("\\n");\n'
            'value = "Ada";\n'
            'if name := value { print($"yes {name}"); } else { print("no"); }\n'
            'print("\\n");\n'
        )
        self.assert_program_output(source, "default\nno\nyes Ada\n")

    def test_match_statement(self) -> None:
        source = (
            "fun classify(value: int): str {\n"
            "    match value {\n"
            '        case 0 >> return "zero";\n'
            '        case n if n < 0 >> return "negative";\n'
            '        case _ >> return "positive";\n'
            "    }\n"
            "}\n"
            'print(classify(-1)); print(" "); print(classify(0)); print(" ");\n'
            'print(classify(9)); print("\\n");\n'
        )
        self.assert_program_output(source, "negative zero positive\n")

    def test_named_arguments(self) -> None:
        source = (
            'fun greet(name: str = "world", punctuation: str = "!") {\n'
            '    print($"{name}{punctuation}");\n'
            "}\n"
            "greet();\n"
            'greet(name >> "Ada");\n'
            'greet(punctuation >> "?", name >> "Grace");\n'
        )
        self.assert_program_output(source, "world!Ada!Grace?")

    def test_pipeline(self) -> None:
        source = (
            "use strings;\n"
            'result := "  powang  " |> strings.trim |> strings.upper;\n'
            'print(result); print("\\n");\n'
        )
        self.assert_program_output(source, "POWANG\n")

    def test_const_macros(self) -> None:
        source = (
            "const MAX_SIZE: int = 8;\n"
            "const DOUBLE_MAX = MAX_SIZE * 2;\n"
            'print(DOUBLE_MAX); print("\\n");\n'
        )
        self.assert_program_output(source, "16\n")


class VariableTests(LanguageTestCase):
    def test_typed_inferred_weak_and_const(self) -> None:
        source = (
            "a: int = 2.5;\n"
            "b: num = 2;\n"
            'c := "hi";\n'
            "w: @str = nova;\n"
            'w = "value";\n'
            "k: num!;\n"
            "k = 6.9;\n"
            'print(a); print(" "); print(b); print(" ");\n'
            'print(c); print(" "); print(w); print(" "); print(k); print("\\n");\n'
        )
        self.assert_program_output(source, "2 2.0 hi value 6.9\n")


if __name__ == "__main__":
    unittest.main()
