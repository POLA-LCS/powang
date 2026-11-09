"""Operator overloading through built-in structural traits."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


VECTOR = """
type Vector[+] {
    | x: int;
    | y: int;

    fun this.add(other: Vector): Vector >> Vector.[this.x + other.x, this.y + other.y];
    fun this.subtract(other: Vector): Vector >> Vector.[this.x - other.x, this.y - other.y];
    fun this.multiply(scale: int): Vector >> Vector.[this.x * scale, this.y * scale];
    fun this.negate(): Vector >> Vector.[-this.x, -this.y];
    fun this.compare(other: Vector): int {
        if this.x < other.x {
            return -1;
        }
        if this.x > other.x {
            return 1;
        }
        return this.y - other.y;
    }
}
"""


class OperatorRuntimeTests(unittest.TestCase):
    def test_arithmetic_and_unary_operators(self) -> None:
        result = run_source(
            VECTOR
            + "a := Vector.[1, 2];\n"
            "b := Vector.[3, 4];\n"
            "c := a + b;\n"
            'println(c.x); println(c.y);\n'
            "d := a - b;\n"
            'println(d.x); println(d.y);\n'
            "e := a * 3;\n"
            'println(e.x); println(e.y);\n'
            "f := -a;\n"
            'println(f.x); println(f.y);\n'
        )
        self.assertEqual(result.stdout, "4\n6\n-2\n-2\n3\n6\n-1\n-2\n")

    def test_comparison_operators(self) -> None:
        result = run_source(
            VECTOR
            + "a := Vector.[1, 2];\n"
            "b := Vector.[3, 4];\n"
            "equal := Vector.[1, 2];\n"
            "println(a < b);\n"
            "println(a <= b);\n"
            "println(a > b);\n"
            "println(a >= b);\n"
            "println(a == equal);\n"
            "println(a != b);\n"
        )
        self.assertEqual(result.stdout, "true\ntrue\nfalse\nfalse\ntrue\ntrue\n")

    def test_compound_assignment_uses_operator(self) -> None:
        result = run_source(
            VECTOR
            + "a := Vector.[1, 2];\n"
            "b := Vector.[3, 4];\n"
            "a += b;\n"
            'println(a.x); println(a.y);\n'
        )
        self.assertEqual(result.stdout, "4\n6\n")

    def test_trait_qualified_operator_methods(self) -> None:
        result = run_source(
            "type Vector[+] {\n"
            "    | x: int;\n"
            "    | y: int;\n"
            "    fun Add.add(other: Vector): Vector >> Vector.[this.x + other.x, this.y + other.y];\n"
            "    fun Compare.compare(other: Vector): int >> this.x - other.x;\n"
            "}\n"
            "a := Vector.[1, 2];\n"
            "b := Vector.[3, 4];\n"
            'println((a + b).x);\n'
            'println(a < b);\n'
            'println(a == b);\n'
        )
        self.assertEqual(result.stdout, "4\ntrue\nfalse\n")

    def test_custom_trait_qualified_operator_methods(self) -> None:
        result = run_source(
            "trait Arithmetic {\n"
            "    fun add(other: any): any;\n"
            "    fun compare(other: any): int;\n"
            "}\n"
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun Arithmetic.add(other: Point): Point >> Point.[this.x + other.x];\n"
            "    fun Arithmetic.compare(other: Point): int >> this.x - other.x;\n"
            "}\n"
            "value: Arithmetic = Point.[1];\n"
            "other := Point.[2];\n"
            "print((value + other).x); print(\"\\n\");\n"
            "print(value < other); print(\"\\n\");\n"
            "fun plus[T: Arithmetic](left: T, right: T): any >> left + right;\n"
            "print((plus(value, other) + other).x); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "3\ntrue\n5\n")

    def test_custom_trait_operator_without_annotation(self) -> None:
        result = run_source(
            "trait Arithmetic {\n"
            "    fun add(other: any): any;\n"
            "}\n"
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun Arithmetic.add(other: Point): Point >> Point.[this.x + other.x];\n"
            "}\n"
            "left := Point.[1];\n"
            "right := Point.[2];\n"
            'print((left + right).x); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3\n")

    def test_trait_annotation_and_generic_constraint(self) -> None:
        result = run_source(
            VECTOR
            + "value: Add = Vector.[1, 2];\n"
            "println((value + Vector.[3, 4]).x);\n"
            "fun plus[T: Add](left: T, right: T): T >> left + right;\n"
            "println(plus(Vector.[1, 2], Vector.[3, 4]).y);\n"
        )
        self.assertEqual(result.stdout, "4\n6\n")

    def test_private_operator_method_is_callable_through_operator(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    - fun this.add(other: Point): Point >> Point.[this.x + other.x];\n"
            "}\n"
            "a := Point.[1];\n"
            "b := Point.[2];\n"
            'println((a + b).x);\n'
        )
        self.assertEqual(result.stdout, "3\n")

    def test_native_operators_still_work(self) -> None:
        result = run_source(
            'println(1 + 2);\n'
            'println("a" + "b");\n'
            'println(3 < 4);\n'
        )
        self.assertEqual(result.stdout, "3\nab\ntrue\n")


class OperatorDiagnosticTests(unittest.TestCase):
    def test_operator_operand_type_error(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun this.add(other: Point): Point >> this;\n"
            "}\n"
            "point := Point.[1];\n"
            "point + 1;\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("operator +", result.combined)
        self.assertIn("expected object:Point", result.combined)
        self.assertIn("int", result.combined)

    def test_async_operator_method_is_rejected_when_used(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    async fun this.add(other: Point): Point >> this;\n"
            "}\n"
            "point := Point.[1];\n"
            "point + point;\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("operator method 'add' cannot be async", result.combined)

    def test_async_operator_method_runtime_guard(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    async fun this.add(other: Point): Point >> this;\n"
            "}\n"
            "point := Point.[1];\n"
            "point + point;\n",
            args=("--no-check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("operator methods cannot be async", result.combined)

    def test_static_method_does_not_overload_operator(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun add(other: Point): Point >> Point.[0];\n"
            "}\n"
            "point := Point.[1];\n"
            "print(point + point);\n",
            args=("--no-check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid operation", result.combined)

    def test_reserved_operator_trait_name(self) -> None:
        result = run_source(
            "trait Add {\n"
            "    fun add(other: any): any;\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("reserved for operator overloading", result.combined)

    def test_reserved_operator_trait_runtime_guard(self) -> None:
        result = run_source(
            "trait Add {\n"
            "    fun add(other: any): any;\n"
            "}\n",
            args=("--no-check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("built-in operator trait", result.combined)

    def test_reserved_operator_trait_name_for_types(self) -> None:
        result = run_source(
            "type Add[+] {\n"
            "    | x: int;\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("reserved for operator overloading", result.combined)
        runtime = run_source(
            "type Add[+] {\n"
            "    | x: int;\n"
            "}\n",
            args=("--no-check",),
        )
        self.assertEqual(runtime.returncode, 1)
        self.assertIn("built-in operator trait", runtime.combined)

    def test_compare_must_return_int_at_check_time(self) -> None:
        result = run_source(
            "type Bad[+] {\n"
            "    | x: int;\n"
            "    fun this.compare(other: Bad): str >> \"x\";\n"
            "}\n"
            "left := Bad.[1];\n"
            "right := Bad.[2];\n"
            "left < right;\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not satisfy Compare.compare", result.combined)

    def test_compare_must_return_int_at_runtime(self) -> None:
        result = run_source(
            "type Bad[+] {\n"
            "    | x: int;\n"
            "    fun this.compare(other: Bad): str >> \"x\";\n"
            "}\n"
            "left := Bad.[1];\n"
            "right := Bad.[2];\n"
            "print(left < right);\n",
            args=("--no-check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("compare must return int", result.combined)

    def test_operator_method_overloads_select_by_operand(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun this.add(other: Point): Point >> Point.[this.x + other.x];\n"
            "    fun this.add(scale: int): Point >> Point.[this.x + scale];\n"
            "}\n"
            "left := Point.[1];\n"
            "right := Point.[2];\n"
            'print((left + right).x); print(" ");\n'
            'print((left + 3).x); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3 4\n")

    def test_dynamic_dispatch_is_ambiguous_with_two_operator_traits(self) -> None:
        result = run_source(
            "trait Arithmetic {\n"
            "    fun add(other: any): any;\n"
            "}\n"
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun Add.add(other: Point): Point >> Point.[this.x + other.x];\n"
            "    fun Arithmetic.add(other: Point): Point >> Point.[this.x - other.x];\n"
            "}\n"
            "fun dynamic(value: any, other: Point): any >> value + other;\n"
            "point := Point.[2];\n"
            "print(dynamic(point, point).x);\n",
            args=("--no-check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("ambiguous", result.combined)

    def test_operator_method_arity_error(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun this.add(left: Point, right: Point): Point >> this;\n"
            "}\n"
            "a := Point.[1];\n"
            "b := Point.[2];\n"
            "a + b;\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not satisfy Add.add", result.combined)


if __name__ == "__main__":
    unittest.main()
