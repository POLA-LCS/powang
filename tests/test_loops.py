"""Loop syntax, labels, break, continue and loop warnings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class LoopTests(unittest.TestCase):
    def test_loop_breaks(self) -> None:
        result = run_source(
            "count := 0;\n"
            "loop {\n"
            "    count += 1;\n"
            "    if count >= 3 { break; }\n"
            "}\n"
            'print(count); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3\n")

    def test_loop_if_condition(self) -> None:
        result = run_source(
            "count := 0;\n"
            "loop if count < 3 {\n"
            "    count += 1;\n"
            "}\n"
            'print(count); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "3\n")

    def test_loop_if_declaration_scope(self) -> None:
        result = run_source(
            "index := 0;\n"
            "loop if current := index < 3 {\n"
            '    print(current); print(" ");\n'
            "    index += 1;\n"
            "}\n"
            'print("\\n");\n'
        )
        self.assertEqual(result.stdout, "true true true \n")

    def test_continue_skips_to_the_next_iteration(self) -> None:
        result = run_source(
            "for i := 0; i < 3; i += 1 {\n"
            "    if i == 1 { continue; }\n"
            '    print(i); print(" ");\n'
            "}\n"
            'print("\\n");\n'
        )
        self.assertEqual(result.stdout, "0 2 \n")

    def test_labeled_break_exits_outer_loop(self) -> None:
        result = run_source(
            "found := false;\n"
            "for |outer| i >> 0 >> 3 {\n"
            "    for j >> 0 >> 3 {\n"
            "        if i == 1 && j == 1 {\n"
            "            found = true;\n"
            "            break outer;\n"
            "        }\n"
            "    }\n"
            "}\n"
            'print(found); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "true\n")

    def test_labeled_continue_continues_outer_loop(self) -> None:
        result = run_source(
            "for |outer| i >> 0 >> 2 {\n"
            "    for j >> 0 >> 2 {\n"
            "        if j == 1 { continue outer; }\n"
            '        print(i); print(" "); print(j); print("\\n");\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(result.stdout, "0 0\n1 0\n")

    def test_break_runs_finally(self) -> None:
        result = run_source(
            "count := 0;\n"
            "loop {\n"
            "    try {\n"
            "        count += 1;\n"
            "        break;\n"
            "    } finally {\n"
            '        print("finally");\n'
            "    }\n"
            "}\n"
            'print(" "); print(count); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "finally 1\n")

    def test_break_outside_loop_is_rejected(self) -> None:
        result = run_source("break;\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("only valid inside a loop", result.combined)

    def test_unknown_label_is_rejected(self) -> None:
        result = run_source(
            "for i >> 0 >> 1 {\n"
            "    break missing;\n"
            "}\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown loop label", result.combined)

    def test_duplicate_label_is_rejected(self) -> None:
        result = run_source(
            "for |outer| i >> 0 >> 1 {\n"
            "    for |outer| j >> 0 >> 1 { break; }\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("already in use", result.combined)

    def test_loop_without_break_warns(self) -> None:
        result = run_source(
            'loop { print("x"); }\n',
            args=("--check",),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("loop has no break", result.stderr)

    def test_loop_if_false_is_removed(self) -> None:
        result = run_source(
            'loop if false { print("x"); }\n',
            args=("--check",),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("loop has no effect", result.stderr)

    def test_loop_if_true_recommends_loop(self) -> None:
        result = run_source(
            'loop if true { print("x"); }\n',
            args=("--check",),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("use loop instead of loop if true", result.stderr)


if __name__ == "__main__":
    unittest.main()
