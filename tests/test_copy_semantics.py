"""Implicit copies are values. Explicit references remain aliases."""

from __future__ import annotations

import unittest

from helpers import run_source


class CopySemanticsTests(unittest.TestCase):
    def test_array_assignment_copies(self) -> None:
        result = run_source(
            "a := [1];\n"
            "b := a;\n"
            "b[0] = 9;\n"
            'print(a[0]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "1\n")

    def test_nested_object_property_copies(self) -> None:
        result = run_source(
            "type Box[+] {\n"
            "    items: arr[int] = [1];\n"
            "}\n"
            "first := Box.[];\n"
            "second := first;\n"
            "second.items[0] = 9;\n"
            'print(first.items[0]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "1\n")

    def test_map_value_copies(self) -> None:
        result = run_source(
            'a := ["x" >> [1]];\n'
            "b := a;\n"
            'b["x"][0] = 9;\n'
            'print(a["x"][0]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "1\n")

    def test_explicit_reference_still_aliases(self) -> None:
        result = run_source(
            "fun bump(value: &int) { value += 1; }\n"
            "x := 1;\n"
            "bump(&x);\n"
            'print(x); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "2\n")

    def test_task_reference_is_rejected(self) -> None:
        result = run_source(
            "fun bump(value: &int) { value += 1; }\n"
            "x := 1;\n"
            "try {\n"
            "    task := spawn bump(&x);\n"
            "    wait(task);\n"
            "} catch problem {\n"
            '    print("rejected: " + problem.message + "\\n");\n'
            "}\n"
            'print(x); print("\\n");\n'
        )
        self.assertIn("rejected: References cannot be sent to a task", result.stdout)
        self.assertTrue(result.stdout.endswith("1\n"))

    def test_cyclic_object_copy_terminates(self) -> None:
        result = run_source(
            "type Node[+] {\n"
            "    next: any;\n"
            "}\n"
            "n := Node.[];\n"
            "n.next = n;\n"
            "m := n;\n"
            'print(typeof(m.next)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "Node\n")


if __name__ == "__main__":
    unittest.main()
