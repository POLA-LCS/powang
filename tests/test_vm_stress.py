"""Stress tests for the bytecode VM.

Each case compares the two engines and asserts a concrete result so a shared
failure cannot pass. The sizes are chosen to stay fast on a laptop while still
exercising large heaps, many closures, many tasks and repeated VM creation.
"""

from __future__ import annotations

import unittest

from tests.helpers import run_source


def run_both(case: unittest.TestCase, source: str) -> str:
    tree = run_source(source, engine="tree", timeout=120)
    vm = run_source(source, engine="vm", timeout=120)
    case.assertEqual(tree.returncode, vm.returncode,
                     f"tree={tree.combined}\nvm={vm.combined}")
    case.assertEqual(tree.stdout, vm.stdout,
                     f"tree={tree.combined}\nvm={vm.combined}")
    case.assertEqual(tree.stderr, vm.stderr,
                     f"tree={tree.combined}\nvm={vm.combined}")
    return vm.stdout


class StressTests(unittest.TestCase):
    def test_large_array_and_map(self) -> None:
        source = (
            "values := [];\n"
            "for index >> 0 >> 3000 { values = values + [index]; }\n"
            "total := 0;\n"
            "for value >> values { total += value; }\n"
            "print(total); print(\" \"); print(size(values)); print(\"\\n\");\n"
            "table := [>>];\n"
            "for index >> 0 >> 500 { table[index] = index * 2; }\n"
            "print(size(table)); print(\" \\n\");\n"
        )
        out = run_both(self, source)
        self.assertEqual(out, "4498500 3000\n500 \n")

    def test_many_closures(self) -> None:
        source = (
            "total := 0;\n"
            "for index >> 0 >> 200 {\n"
            "    offset := index;\n"
            "    add := fun(value: int): int >> value + offset;\n"
            "    total += add(1);\n"
            "}\n"
            "print(total); print(\"\\n\");\n"
        )
        out = run_both(self, source)
        self.assertEqual(out, "20100\n")

    def test_many_awaited_tasks(self) -> None:
        source = (
            "async fun square(value: int): int >> value * value;\n"
            "total := 0;\n"
            "for index >> 0 >> 200 {\n"
            "    total += await square(index);\n"
            "}\n"
            "print(total); print(\"\\n\");\n"
        )
        out = run_both(self, source)
        self.assertEqual(out, "2646700\n")

    def test_large_string_slicing(self) -> None:
        source = (
            "text := \"\";\n"
            "for index >> 0 >> 2000 {\n"
            "    text = text + \"ab\";\n"
            "}\n"
            "print(size(text)); print(\" \");\n"
            "print(size(text[100 >> 1900])); print(\" \");\n"
            "print(text[-1]); print(\"\\n\");\n"
        )
        out = run_both(self, source)
        self.assertEqual(out, "4000 1800 b\n")

    def test_repeated_runs_are_isolated(self) -> None:
        source = (
            "counter := 0;\n"
            "for index >> 0 >> 50 { counter += 1; }\n"
            "print(counter); print(\"\\n\");\n"
        )
        first = run_source(source, engine="vm")
        second = run_source(source, engine="vm")
        self.assertEqual(first.stdout, "50\n")
        self.assertEqual(second.stdout, "50\n")
        self.assertEqual(first.stderr, "")
        self.assertEqual(second.stderr, "")


if __name__ == "__main__":
    unittest.main()
