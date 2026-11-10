"""Async functions, await and lazy async tasks."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_file, run_source, write_po  # noqa: E402


class AsyncRuntimeTests(unittest.TestCase):
    def test_async_function_and_await(self) -> None:
        result = run_source(
            "async fun double(value: int): int >> value * 2;\n"
            "async fun total(): int {\n"
            "    a := await double(3);\n"
            "    b := await double(4);\n"
            "    return a + b;\n"
            "}\n"
            'print(await total()); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "14\n")

    def test_async_method(self) -> None:
        result = run_source(
            "type Worker[+] {\n"
            "    | value: int;\n"
            "    async fun this.double(): int >> this.value * 2;\n"
            "}\n"
            "worker := Worker.[5];\n"
            'print(await worker.double()); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "10\n")

    def test_async_method_with_argument(self) -> None:
        result = run_source(
            "type Calculator[+] {\n"
            "    | base: int;\n"
            "    async fun this.add(value: int): int >> this.base + value;\n"
            "}\n"
            "calculator := Calculator.[10];\n"
            'print(await calculator.add(5)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "15\n")

    def test_async_static_method(self) -> None:
        result = run_source(
            "type Worker[+] {\n"
            "    | value: int;\n"
            "    async fun make(value: int): Worker >> Worker.[value];\n"
            "}\n"
            "worker := await Worker.make(3);\n"
            'print(worker.value); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3\n")

    def test_async_lambda(self) -> None:
        result = run_source(
            "double := async fun(value: int): int >> value * 2;\n"
            'print(await double(3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "6\n")

    def test_async_module_function(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-async-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/asynclib.po",
                "module asynclib;\n"
                "export async fun double(value: int): int >> value * 2;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/asynclib.po" as a;\n'
                'print(await a.double(3)); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "6\n")

    def test_async_trait_default_method(self) -> None:
        result = run_source(
            "trait AsyncNamed {\n"
            "    | name: str;\n"
            "    fun label(): str;\n"
            "    async fun describe(): str >> this.label();\n"
            "}\n"
            "type Person[+] {\n"
            "    | name: str;\n"
            "    fun this.label(): str >> this.name;\n"
            "}\n"
            'person: AsyncNamed = Person.["Ada"];\n'
            'print(await person.describe()); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "Ada\n")

    def test_wait_on_lazy_async_task(self) -> None:
        result = run_source(
            "async fun value(): int >> 7;\n"
            "task := value();\n"
            'print(task_status(task)); print(" ");\n'
            'print(wait(task)); print(" ");\n'
            'print(task_status(task)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "pending 7 done\n")

    def test_cancel_lazy_async_task(self) -> None:
        result = run_source(
            "async fun value(): int >> 7;\n"
            "task := value();\n"
            "cancel(task);\n"
            'print(task_status(task)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "canceled\n")

    def test_async_error_propagation(self) -> None:
        result = run_source(
            "async fun boom(): int {\n"
            '    error("boom");\n'
            "    return 1;\n"
            "}\n"
            "try {\n"
            "    print(await boom());\n"
            "} catch caught {\n"
            '    print("caught"); print("\\n");\n'
            "}\n"
        )
        self.assertEqual(result.stdout, "caught\n")

    def test_top_level_await(self) -> None:
        result = run_source(
            "async fun value(): int >> 9;\n"
            'print(await value()); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "9\n")

    def test_bare_await_statement(self) -> None:
        result = run_source(
            "async fun work(): int {\n"
            '    println("work");\n'
            "    return 1;\n"
            "}\n"
            "await work();\n"
            'println("done");\n'
        )
        self.assertEqual(result.stdout, "work\ndone\n")

    def test_async_call_returns_task(self) -> None:
        result = run_source(
            "async fun value(): int >> 9;\n"
            "task := value();\n"
            'print(typeof(task)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "task\n")

    def test_many_awaited_async_tasks(self) -> None:
        result = run_source(
            "async fun value(input: int): int >> input;\n"
            "count := 0;\n"
            "loop if count < 70 {\n"
            "    task := value(count);\n"
            "    count = await task;\n"
            "    count += 1;\n"
            "}\n"
            'print(count); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "70\n")

    def test_async_function_value_scoping(self) -> None:
        result = run_source(
            "f := async fun(x: int): int >> x * 2;\n"
            "g := f;\n"
            "fun sync_scope(): int {\n"
            "    f := fun(x: int): int >> x + 10;\n"
            "    return f(5);\n"
            "}\n"
            'print(await f(3)); print(" ");\n'
            'print(await g(4)); print(" ");\n'
            'print(sync_scope()); print(" ");\n'
            'print(await f(3)); print("\\n");\n'
            "h := async fun(x: int): int >> x * 3;\n"
            "h = fun(x: int): int >> x + 1;\n"
            'print(h(5)); print("\\n");\n'
            "async fun double(value: int): int >> value * 2;\n"
            "double_value := double;\n"
            'print(await double_value(3)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "6 8 15 6\n6\n6\n")

    def test_pending_async_task_limit(self) -> None:
        result = run_source(
            "async fun value(): int >> 1;\n"
            "count := 0;\n"
            "try {\n"
            "    loop if count < 70 {\n"
            "        task := value();\n"
            "        count += 1;\n"
            "    }\n"
            "} catch limit_error {\n"
            '    print("limit"); print("\\n");\n'
            "}\n"
        )
        self.assertEqual(result.stdout, "limit\n")


class AsyncDiagnosticTests(unittest.TestCase):
    def test_await_outside_async(self) -> None:
        result = run_source(
            "async fun value(): int >> 1;\n"
            "fun caller(): int {\n"
            "    return await value();\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "'await' is only valid inside an async function",
            result.combined,
        )

    def test_await_non_task(self) -> None:
        result = run_source(
            "async fun value(): int {\n"
            "    return await 1;\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("'await' expects a task value", result.combined)

    def test_await_result_type_mismatch(self) -> None:
        result = run_source(
            "async fun number(): int >> 1;\n"
            "text: str = await number();\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected str", result.combined)
        self.assertIn("but int", result.combined)

    def test_await_non_async_function_call(self) -> None:
        result = run_source(
            "fun number(): int >> 1;\n"
            "async fun value(): int {\n"
            "    return await number();\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("'await' expects a task value", result.combined)

    def test_async_requires_fun(self) -> None:
        result = run_source(
            "async value := 1;\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Expected 'fun' after 'async'", result.combined)


if __name__ == "__main__":
    unittest.main()
