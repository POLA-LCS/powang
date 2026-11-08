"""Variadic functions, explicit type arguments and spread."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class VariadicRuntimeTests(unittest.TestCase):
    def test_variadic_sum(self) -> None:
        result = run_source(
            "fun sum(values: int...): int {\n"
            "    total := 0;\n"
            "    for value >> values {\n"
            "        total += value;\n"
            "    }\n"
            "    return total;\n"
            "}\n"
            'print(sum()); print(" ");\n'
            'print(sum(1)); print(" ");\n'
            'print(sum(1, 2, 3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "0 1 6\n")

    def test_fixed_and_variadic_parameters(self) -> None:
        result = run_source(
            "fun join(prefix: str, values: str...): str {\n"
            "    result := prefix;\n"
            "    for value >> values {\n"
            "        result += value;\n"
            "    }\n"
            "    return result;\n"
            "}\n"
            'print(join(">", "a", "b", "c")); print("\\n");\n'
        )
        self.assertEqual(result.stdout, ">abc\n")

    def test_variadic_sugar(self) -> None:
        result = run_source(
            "fun count(values..): int >> size(values);\n"
            'print(count(1, 2, 3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3\n")

    def test_variadic_type_parameter_sugar(self) -> None:
        result = run_source(
            "fun first[T, ...](values..): T {\n"
            "    return values[0];\n"
            "}\n"
            'print(first(7, 8, 9)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "7\n")

    def test_explicit_type_arguments_select_template(self) -> None:
        result = run_source(
            "fun add(a: int, b: int): int >> a + b;\n"
            "fun add[T](a: T, b: T): T {\n"
            '    println("TEMPLATE");\n'
            "    return a + b;\n"
            "}\n"
            'print(add(1, 2)); print(" ");\n'
            'print(add[int](1, 2)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3 TEMPLATE\n3\n")

    def test_spread_array(self) -> None:
        result = run_source(
            "fun sum(values: int...): int {\n"
            "    total := 0;\n"
            "    for value >> values { total += value; }\n"
            "    return total;\n"
            "}\n"
            "values := [1, 2, 3];\n"
            'print(sum(...values)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "6\n")

    def test_spread_tuple_and_set(self) -> None:
        result = run_source(
            "fun count(values: any...): int >> size(values);\n"
            "pair := .[1, 2, 3];\n"
            "unique := [/4, 5, 6];\n"
            'print(count(...pair)); print(" ");\n'
            'print(count(...unique)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3 3\n")

    def test_spread_map_and_string(self) -> None:
        result = run_source(
            "fun count(values: any...): int >> size(values);\n"
            "pairs := [\"a\" >> 1, \"b\" >> 2];\n"
            'print(count(...pairs)); print(" ");\n'
            'print(count(..."ab")); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "2 2\n")

    def test_variadic_method(self) -> None:
        result = run_source(
            "type Adder[+] {\n"
            "    | base: int;\n"
            "    fun this.sum(values: int...): int {\n"
            "        total := this.base;\n"
            "        for value >> values { total += value; }\n"
            "        return total;\n"
            "    }\n"
            "}\n"
            "adder := Adder.[10];\n"
            'print(adder.sum(...[1, 2, 3])); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "16\n")

    def test_variadic_function_type_annotation(self) -> None:
        result = run_source(
            "fun sum(values: int...): int {\n"
            "    total := 0;\n"
            "    for value >> values { total += value; }\n"
            "    return total;\n"
            "}\n"
            "adder: fun[int..., int] = sum;\n"
            'print(adder(1, 2, 3)); print("\\n");\n'
            'print(typedeep(adder)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "6\nfun[int..., int]\n")

    def test_typedeep_variadic_function(self) -> None:
        result = run_source(
            "fun sum(values: int...): int {\n"
            "    total := 0;\n"
            "    for value >> values { total += value; }\n"
            "    return total;\n"
            "}\n"
            'print(typedeep(sum)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "fun[int..., int]\n")


class VariadicDiagnosticTests(unittest.TestCase):
    def test_variadic_parameter_must_be_last(self) -> None:
        result = run_source(
            "fun bad(values: int..., other: int): int >> 0;\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("variadic parameter must be last", result.combined)

    def test_explicit_type_arguments_require_a_template(self) -> None:
        result = run_source(
            "fun add(a: int, b: int): int >> a + b;\n"
            "add[int](1, 2);\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("No generic overload", result.combined)

    def test_generic_variadic_arguments_infer_element_type(self) -> None:
        result = run_source(
            "fun first[T](values: T...): T {\n"
            "    return values[0];\n"
            "}\n"
            "x: str = first(1, 2);\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected str", result.combined)
        self.assertIn("int", result.combined)

    def test_zero_variadic_arguments_infer_undef(self) -> None:
        result = run_source(
            "fun count[T](values: T...): int >> size(values);\n"
            "x: int = count();\n"
            "print(x);\n"
            'print("\\n");\n'
        )
        self.assertEqual(result.stdout, "0\n")


if __name__ == "__main__":
    unittest.main()
