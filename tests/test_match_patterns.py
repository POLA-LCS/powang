"""Match destructuring, range patterns and coverage warnings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class MatchRuntimeTests(unittest.TestCase):
    def test_array_pattern(self) -> None:
        result = run_source(
            "values := [1, 2, 3];\n"
            "match values {\n"
            "    case [a, b, c] >> { print($\"{a}{b}{c}\\n\"); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "123\n")

    def test_array_rest_binding(self) -> None:
        result = run_source(
            "values := [1, 2, 3, 4];\n"
            "match values {\n"
            "    case [head, ...tail] >> {\n"
            "        print(head); print(\" \"); print(size(tail)); print(\" \");\n"
            "        print(tail[0]); print(\"\\n\");\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "1 3 2\n")

    def test_array_rest_can_be_ignored(self) -> None:
        result = run_source(
            "match [1, 2, 3] {\n"
            "    case [first, ...] >> { print(first); print(\"\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "1\n")

    def test_array_pattern_copy_keeps_subject(self) -> None:
        result = run_source(
            "values := [1, 2];\n"
            "match values {\n"
            "    case [a, b] >> { a = 99; }\n"
            "}\n"
            "print(values[0]); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "1\n")

    def test_tuple_pattern(self) -> None:
        result = run_source(
            "pair := .[10, 20];\n"
            "match pair {\n"
            "    case .[a, b] >> { print(a + b); print(\"\\n\"); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "30\n")

    def test_array_pattern_matches_tuple(self) -> None:
        result = run_source(
            "pair := .[10, 20];\n"
            "match pair {\n"
            "    case [a, b] >> { print(a + b); print(\"\\n\"); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "30\n")

    def test_typed_binding_inside_array(self) -> None:
        result = run_source(
            "values := [1, 2];\n"
            "match values {\n"
            "    case [a: int, b] >> { print(a + b); print(\"\\n\"); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "3\n")

    def test_object_pattern(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; | y: int; }\n"
            "p := Point.[3, 4];\n"
            "match p {\n"
            "    case Point.[x, y] >> { print(x + y); print(\"\\n\"); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "7\n")

    def test_object_pattern_mapped_fields(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; | y: int; }\n"
            "p := Point.[3, 4];\n"
            "match p {\n"
            "    case Point.[x: px, y: py] >> { print(px * py); print(\"\\n\"); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "12\n")

    def test_object_literal_field_pattern(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; | y: int; }\n"
            "p := Point.[0, 4];\n"
            "match p {\n"
            "    case Point.[x: 0, y] >> { print(y); print(\"\\n\"); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "4\n")

    def test_nested_pattern(self) -> None:
        result = run_source(
            "value := [[1, 2], .[3, 4]];\n"
            "match value {\n"
            "    case [[a, b], .[c, d]] >> { print(a + b + c + d); print(\"\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "10\n")

    def test_range_pattern(self) -> None:
        result = run_source(
            "match 5 {\n"
            "    case 0 >> 10 >> { print(\"low\\n\"); }\n"
            "    case _ >> { print(\"high\\n\"); }\n"
            "}\n"
            "match 10 {\n"
            "    case 0 >> 10 >> { print(\"low\\n\"); }\n"
            "    case _ >> { print(\"high\\n\"); }\n"
            "}\n"
            "match -5 {\n"
            "    case -10 >> 0 >> { print(\"negative\\n\"); }\n"
            "    case _ >> { print(\"other\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "low\nhigh\nnegative\n")

    def test_guard_with_destructuring(self) -> None:
        result = run_source(
            "pair := [1, 2];\n"
            "match pair {\n"
            "    case [a, b] if a < b >> { print(\"asc\\n\"); }\n"
            "    case [a, b] if a > b >> { print(\"desc\\n\"); }\n"
            "    case _ >> { print(\"same\\n\"); }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "asc\n")

    def test_match_expression_result_type(self) -> None:
        result = run_source(
            "fun describe(value: int): str {\n"
            "    return value match {\n"
            "        case 0 >> \"zero\"\n"
            "        case _ >> \"other\"\n"
            "    };\n"
            "}\n"
            "print(describe(0)); print(\" \"); print(describe(2)); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "zero other\n")


class MatchDiagnosticTests(unittest.TestCase):
    def test_bool_exhaustiveness_warning(self) -> None:
        result = run_source(
            "match true {\n"
            "    case true >> { print(\"t\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("match on bool is not exhaustive; missing false", result.stderr)

    def test_bool_exhaustive_has_no_warning(self) -> None:
        result = run_source(
            "match true {\n"
            "    case true >> { print(\"t\\n\"); }\n"
            "    case false >> { print(\"f\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertNotIn("not exhaustive", result.stderr)

    def test_enum_exhaustiveness_warning(self) -> None:
        result = run_source(
            "type Color enum { RED, GREEN, BLUE }\n"
            "c: Color = Color.RED;\n"
            "match c {\n"
            "    case Color.RED >> { print(\"r\\n\"); }\n"
            "    case Color.GREEN >> { print(\"g\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertIn(
            "match on Color is not exhaustive; missing BLUE",
            result.stderr,
        )

    def test_enum_exhaustive_has_no_warning(self) -> None:
        result = run_source(
            "type Color enum { RED, GREEN, BLUE }\n"
            "c: Color = Color.RED;\n"
            "match c {\n"
            "    case Color.RED >> { print(\"r\\n\"); }\n"
            "    case Color.GREEN >> { print(\"g\\n\"); }\n"
            "    case Color.BLUE >> { print(\"b\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertNotIn("not exhaustive", result.stderr)

    def test_wildcard_suppresses_exhaustiveness_warning(self) -> None:
        result = run_source(
            "match true {\n"
            "    case true >> { print(\"t\\n\"); }\n"
            "    case _ >> { print(\"f\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertNotIn("not exhaustive", result.stderr)

    def test_unreachable_after_wildcard(self) -> None:
        result = run_source(
            "match 1 {\n"
            "    case _ >> { print(\"all\\n\"); }\n"
            "    case 1 >> { print(\"one\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertIn("unreachable match case", result.stderr)

    def test_duplicate_literal_warning(self) -> None:
        result = run_source(
            "match 1 {\n"
            "    case 1 >> { print(\"one\\n\"); }\n"
            "    case 1 >> { print(\"again\\n\"); }\n"
            "    case _ >> { print(\"other\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertIn("unreachable match case", result.stderr)

    def test_guarded_duplicate_does_not_warn(self) -> None:
        result = run_source(
            "x := 1;\n"
            "match x {\n"
            "    case 1 if x > 0 >> { print(\"guarded\\n\"); }\n"
            "    case 1 >> { print(\"one\\n\"); }\n"
            "    case _ >> { print(\"other\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertNotIn("unreachable match case", result.stderr)

    def test_duplicate_range_warning(self) -> None:
        result = run_source(
            "match 5 {\n"
            "    case 0 >> 10 >> { print(\"low\\n\"); }\n"
            "    case 0 >> 10 >> { print(\"low2\\n\"); }\n"
            "    case _ >> { print(\"other\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertIn("unreachable match case", result.stderr)

    def test_literal_inside_range_warning(self) -> None:
        result = run_source(
            "match 5 {\n"
            "    case 0 >> 10 >> { print(\"low\\n\"); }\n"
            "    case 5 >> { print(\"five\\n\"); }\n"
            "    case _ >> { print(\"other\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertIn("unreachable match case", result.stderr)

    def test_array_pattern_subject_type_error(self) -> None:
        result = run_source(
            "match 5 {\n"
            "    case [a] >> { print(a); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("array pattern cannot match subject type int", result.combined)

    def test_unknown_object_field_error(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; | y: int; }\n"
            "p := Point.[3, 4];\n"
            "match p {\n"
            "    case Point.[z] >> { print(z); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no property named 'z'", result.combined)

    def test_tuple_arity_error(self) -> None:
        result = run_source(
            "pair := .[1, 2];\n"
            "match pair {\n"
            "    case .[a] >> { print(a); }\n"
            "    case _ >> { print(\"no\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("tuple pattern has 1 elements", result.combined)

    def test_range_bound_type_error(self) -> None:
        result = run_source(
            "start := \"a\";\n"
            "match 5 {\n"
            "    case 0 >> start >> { print(\"range\\n\"); }\n"
            "    case _ >> { print(\"other\\n\"); }\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("match range", result.combined)

    def test_match_expression_result_type_error(self) -> None:
        result = run_source(
            "value := 1;\n"
            "x: str = value match {\n"
            "    case 1 >> 1\n"
            "    case _ >> 2\n"
            "};\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected str", result.combined)
        self.assertIn("int", result.combined)

    def test_match_expression_exhaustiveness_warning(self) -> None:
        result = run_source(
            "value := true;\n"
            "x := value match {\n"
            "    case true >> 1\n"
            "};\n",
            args=("--check",),
        )
        self.assertIn("match on bool is not exhaustive; missing false", result.stderr)


if __name__ == "__main__":
    unittest.main()
