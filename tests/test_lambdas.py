"""Lambda expressions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class LambdaParserTests(unittest.TestCase):
    def assert_checks(self, source: str) -> None:
        result = run_source(source, args=("--check",))
        self.assertEqual(result.returncode, 0, result.combined)

    def test_expression_body_lambda(self) -> None:
        self.assert_checks("double := fun(x: int): int >> x * 2;\n")

    def test_block_body_lambda(self) -> None:
        self.assert_checks(
            "double := fun(x: int): int {\n"
            "    return x * 2;\n"
            "};\n"
        )

    def test_named_lambda(self) -> None:
        self.assert_checks(
            "factorial := fun fact(n: int): int >>\n"
            "    n <= 1 ?? 1 :> fact(n - 1) * n;\n"
        )

    def test_mutable_capture_lambda(self) -> None:
        self.assert_checks(
            "counter := 0;\n"
            "bump := fun &(value: int) { counter += value; };\n"
        )

    def test_lambda_needs_a_body(self) -> None:
        result = run_source("bad := fun(x: int): int;\n", args=("--check",))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Expected a block or '>>' body", result.combined)


class LambdaRuntimeTests(unittest.TestCase):
    def test_expression_lambda_call(self) -> None:
        result = run_source(
            "double := fun(x: int): int >> x * 2;\n"
            'print(double(3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "6\n")

    def test_block_lambda_call(self) -> None:
        result = run_source(
            "double := fun(x: int): int {\n"
            "    return x * 2;\n"
            "};\n"
            'print(double(3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "6\n")

    def test_named_lambda_recursion(self) -> None:
        result = run_source(
            "factorial := fun fact(n: int): int {\n"
            "    if n <= 1 {\n"
            "        return 1;\n"
            "    }\n"
            "    return fact(n - 1) * n;\n"
            "};\n"
            'print(factorial(5)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "120\n")

    def test_by_value_capture(self) -> None:
        result = run_source(
            "base := 10;\n"
            "add_base := fun(value: int): int >> value + base;\n"
            "base = 20;\n"
            'print(add_base(1)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "11\n")

    def test_by_reference_capture(self) -> None:
        result = run_source(
            "counter := 0;\n"
            "bump := fun &(value: int) { counter += value; };\n"
            "bump(2);\n"
            'print(counter); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "2\n")

    def test_lambda_as_argument(self) -> None:
        result = run_source(
            "fun apply(function: fun[int, int], value: int): int {\n"
            "    return function(value);\n"
            "}\n"
            'print(apply(fun(x: int): int >> x * 2, 4)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "8\n")

    def test_lambda_returned_from_function(self) -> None:
        result = run_source(
            "fun make_adder(n: int): fun[int, int] {\n"
            "    return fun(x: int): int >> x + n;\n"
            "}\n"
            "add5 := make_adder(5);\n"
            'print(add5(3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "8\n")

    def test_lambda_in_array(self) -> None:
        result = run_source(
            "handlers := [\n"
            "    fun(x: int): int >> x + 1,\n"
            "    fun(x: int): int >> x * 2,\n"
            "];\n"
            'print(handlers[0](3)); print(" ");\n'
            'print(handlers[1](3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "4 6\n")

    def test_typedeep_function(self) -> None:
        result = run_source(
            "double := fun(x: int): int >> x * 2;\n"
            'print(typedeep(double)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "fun[int, int]\n")

    def test_mutable_lambda_in_task_is_rejected(self) -> None:
        result = run_source(
            "counter := 0;\n"
            "bump := fun &(value: int) { counter += value; };\n"
            "task := spawn bump(1);\n"
            "wait(task);\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Mutable-capture lambdas cannot be sent to a task", result.combined)

    def test_lambda_captures_this(self) -> None:
        result = run_source(
            "type Counter[+] {\n"
            "    count: int = 0;\n"
            "    fun this.make_bump(): fun[int, int] {\n"
            "        return fun &(value: int): int {\n"
            "            this.count += value;\n"
            "            return this.count;\n"
            "        };\n"
            "    }\n"
            "}\n"
            "c := Counter.[];\n"
            "bump := c.make_bump();\n"
            "bump(2);\n"
            "bump(3);\n"
            'print(c.count); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "5\n")


if __name__ == "__main__":
    unittest.main()
