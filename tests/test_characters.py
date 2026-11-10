"""Character literals, native methods and code point helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import assert_no_traceback, run_source  # noqa: E402


class CharacterLiteralTests(unittest.TestCase):
    def test_literal_type_and_escapes(self) -> None:
        result = run_source(
            "a := 'A';\n"
            "b := '\\n';\n"
            "c := '\\u{1F600}';\n"
            "print(a); print(\"|\"); print(ord(a)); print(\"|\"); print(size(a)); print(\"|\");\n"
            "print(typedeep(a)); print(\"|\"); print(typeof(a)); print(\"|\");\n"
            "print(b == '\\n'); print(\"|\"); print(ord(c)); println(\"\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "A|65|1|char|char|true|128512\n")
        assert_no_traceback(self, result)

    def test_string_index_and_get_return_char(self) -> None:
        result = run_source(
            "value := \"A\"[0];\n"
            "println(typeof(value));\n"
            "println(typeof(\"abc\".get(0)));\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "char\nchar\n")

    def test_string_access_returns_char(self) -> None:
        result = run_source(
            "text := \"aé😀\";\n"
            "print(text[1]); print(\"|\");\n"
            "print(text[-1]); print(\"|\");\n"
            "print(typedeep(text.chars())); print(\"|\");\n"
            "println(typeof(text[0]));\n"
            "for ch >> text { print(ch); print(\" \"); }\n"
            "println(\"\");\n"
            "for ch >> text.chars() { print(ch); print(\" \"); }\n"
            "println(\"\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "é|😀|arr[char]|char\na é 😀 \na é 😀 \n")

    def test_concatenation_and_comparison(self) -> None:
        result = run_source(
            "print(\"x\" + 'y'); print(\"|\");\n"
            "print('a' + \"b\"); print(\"|\");\n"
            "print('a' + 'b'); print(\"|\");\n"
            "print('a' < 'b'); print(\"|\");\n"
            "print('a' == \"a\"); println(\"\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "xy|ab|ab|true|true\n")

    def test_char_literal_in_interpolation(self) -> None:
        result = run_source("println($\"ch={'q'}\");\n")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "ch=q\n")

    def test_unsupported_char_arithmetic_is_a_powang_error(self) -> None:
        result = run_source("value := 'a' - 'b';\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported \"-\" operation between char and char", result.combined)
        assert_no_traceback(self, result)


class CharacterBuiltinTests(unittest.TestCase):
    def test_predicates_and_code_points(self) -> None:
        result = run_source(
            "print(is_digit('7')); print(\" \");\n"
            "print(is_digit(\"x\")); print(\" \");\n"
            "print(is_alpha('A')); print(\" \");\n"
            "print(is_alnum('9')); print(\" \");\n"
            "print(is_space('\\t')); print(\" \");\n"
            "print(is_upper('A')); print(\" \");\n"
            "print(is_lower('a')); print(\" \");\n"
            "print(is_ascii('é')); println(\"\");\n"
            "println(digit_value('7'));\n"
            "println(digit_value('x'));\n"
            "println(chr(65));\n"
            "println(ord('A'));\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(
            result.stdout,
            "true false true true true true true false\n7\n-1\nA\n65\n",
        )

    def test_unicode_escape_in_string(self) -> None:
        result = run_source(
            "print(\"\\u{1F600}\"); print(\"|\"); print(is_ascii('\\u{00E9}')); println(\"\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "😀|false\n")

    def test_predicate_rejects_long_string(self) -> None:
        result = run_source("is_alpha(\"ab\");\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected a char or a one-character str", result.combined)
        assert_no_traceback(self, result)

    def test_chr_rejects_invalid_code_point(self) -> None:
        result = run_source("chr(-1);\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid Unicode scalar value", result.combined)
        self.assertIn("-1 is not a Unicode scalar value", result.combined)
        assert_no_traceback(self, result)


class CharacterNativeMethodTests(unittest.TestCase):
    def test_native_char_methods(self) -> None:
        result = run_source(
            "ch := 'G';\n"
            "print(ch.code()); print(\"|\");\n"
            "print(ch.to_str()); print(\"|\");\n"
            "print(ch.is_alpha()); print(\"|\");\n"
            "print(ch.is_upper()); print(\"|\");\n"
            "print(ch.is_ascii()); println(\"\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "71|G|true|true|true\n")

    def test_string_native_methods_accept_char(self) -> None:
        result = run_source(
            "println(\"ab\" :> str.add('c'));\n"
            "println(\"a,b\" :> str.div(','));\n"
            "println(\"a-b-c\" :> str.count('-'));\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "abc\n[a, b]\n2\n")

    def test_explicit_casts_and_construction(self) -> None:
        result = run_source(
            "print('x' as str); print(\"|\");\n"
            "print(\"y\" as char); print(\"|\");\n"
            "print(str.['z']); print(\"|\");\n"
            "print(char.[\"w\"]); print(\"|\");\n"
            "print(typedeep(char.[\"w\"])); println(\"\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "x|y|z|w|char\n")


class CharacterTypeTests(unittest.TestCase):
    def test_assignment_and_function_parameters(self) -> None:
        result = run_source(
            "fun first(text: str): char >> text[0];\n"
            "ch: char = 'a';\n"
            "text: str = 'b';\n"
            "println(ch);\n"
            "println(text);\n"
            "println(first(\"Powang\"));\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "a\nb\nP\n")

    def test_string_spread_yields_char(self) -> None:
        result = run_source(
            "fun count(values: any...): int >> size(values);\n"
            "fun first(values: char...): char >> values[0];\n"
            "print(count(...\"ab\")); print(\"|\");\n"
            "println(first(...\"xy\"));\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "2|x\n")

    def test_typed_string_iteration_binds_char(self) -> None:
        result = run_source(
            "for ch: char >> \"ab\" { print(ch); }\n"
            "println(\"\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "ab\n")

    def test_string_to_char_annotation_requires_cast(self) -> None:
        result = run_source("ch: char = \"a\";\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected char", result.combined)
        assert_no_traceback(self, result)

    def test_typed_array_and_match(self) -> None:
        result = run_source(
            "letters: arr[char] = ['a', 'b'];\n"
            "println(letters);\n"
            "println(typedeep(letters));\n"
            "fun classify(ch: char): str {\n"
            "    return ch match {\n"
            "        case 'a' >> \"alpha\"\n"
            "        case '0' >> \"digit\"\n"
            "        case _ >> \"other\"\n"
            "    };\n"
            "}\n"
            "println(classify('a'));\n"
            "println(classify('0'));\n"
            "println(classify('x'));\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[a, b]\narr[char]\nalpha\ndigit\nother\n")

    def test_char_keys_in_sets_and_maps(self) -> None:
        result = run_source(
            "seen := [/ 'a', 'b', 'a'];\n"
            "print(size(seen)); print(\"|\"); println(set.has(seen, 'a'));\n"
            "mapping := ['k' >> 1];\n"
            "println(mapping['k']);\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "2|true\n1\n")


class InvalidCharacterLiteralTests(unittest.TestCase):
    def test_invalid_literals(self) -> None:
        cases = [
            ("''", "exactly one character"),
            ("'ab'", "exactly one character"),
            ("'\\u{D800}'", "surrogate"),
            ("'\\u{110000}'", "out of range"),
            ("'\\u{-1}'", "not hexadecimal"),
        ]
        for literal, message in cases:
            with self.subTest(literal=literal):
                result = run_source(f"value := {literal};\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.combined)
                assert_no_traceback(self, result)


if __name__ == "__main__":
    unittest.main()
