"""Task clones must not share module closure state with the parent."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import run_file, write_po


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


if __name__ == "__main__":
    unittest.main()
