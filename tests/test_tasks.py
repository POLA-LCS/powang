"""Task clones must not share module closure state with the parent."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import run_file, run_source, write_po


class TaskIsolationTests(unittest.TestCase):
    def test_module_closure_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-task-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/counter.po",
                "counter := [0];\n"
                "export fun bump(): int {\n"
                "    counter[0] += 1;\n"
                "    return counter[0];\n"
                "}\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/counter.po" as *;\n'
                "task := spawn bump();\n"
                'print(wait(task)); print(" ");\n'
                'print(bump()); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "1 1\n")

    def test_spawn_user_method(self) -> None:
        result = run_source(
            "type Worker[+] {\n"
            "    | value: int;\n"
            "    fun this.get(): int { return this.value; }\n"
            "}\n"
            "worker := Worker.[7];\n"
            "task := spawn worker.get();\n"
            'print(wait(task)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "7\n")

    def test_spawn_static_method(self) -> None:
        result = run_source(
            "type Math[+] {\n"
            "    fun double(value: int): int { return value * 2; }\n"
            "}\n"
            "task := spawn Math.double(4);\n"
            'print(wait(task)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "8\n")

    def test_spawn_module_method(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-task-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/counter.po",
                "counter := [0];\n"
                "export fun bump(): int {\n"
                "    counter[0] += 1;\n"
                "    return counter[0];\n"
                "}\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/counter.po" as counter;\n'
                "task := spawn counter.bump();\n"
                'print(wait(task)); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "1\n")


if __name__ == "__main__":
    unittest.main()
