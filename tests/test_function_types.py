"""Function type annotations."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class FunctionTypeAnnotationTests(unittest.TestCase):
    def assert_checks(self, source: str) -> None:
        result = run_source(source, args=("--check",))
        self.assertEqual(result.returncode, 0, result.combined)

    def test_variable_annotation(self) -> None:
        self.assert_checks("handler: fun[int, int];\n")

    def test_array_of_functions(self) -> None:
        self.assert_checks("handlers: arr[fun[int, int]];\n")

    def test_function_parameter(self) -> None:
        self.assert_checks(
            "fun apply(function: fun[int, int], value: int): int {\n"
            "    return function(value);\n"
            "}\n"
        )

    def test_nested_function_return_type(self) -> None:
        self.assert_checks("handler: fun[int, fun[int, int]];\n")

    def test_union_with_function(self) -> None:
        self.assert_checks("handler: fun[int, int] | nova;\n")

    def test_empty_function_type_is_rejected(self) -> None:
        result = run_source("handler: fun[];\n", args=("--check",))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Function types need a return type", result.combined)

    def test_function_keyword_is_not_a_type_annotation(self) -> None:
        result = run_source("handler: function;\n", args=("--check",))
        self.assertEqual(result.returncode, 1)
        self.assertIn("'function' is not a type annotation", result.combined)
        self.assertIn("fun[arg_types..., return_type]", result.combined)

    def test_function_keyword_cannot_be_redeclared(self) -> None:
        result = run_source(
            "type function { | value: int; }\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("a powang native type", result.combined)


if __name__ == "__main__":
    unittest.main()
