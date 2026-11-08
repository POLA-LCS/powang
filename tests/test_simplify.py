"""Literal boolean branches are warned about and removed from the AST."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402
from src.parser import Parser  # noqa: E402
from src.simplify import simplify_program  # noqa: E402
from src.state import fresh_state, reset_state, set_state  # noqa: E402


class SimplifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._state_token = set_state(fresh_state())

    def tearDown(self) -> None:
        reset_state(self._state_token)

    def _simplify(self, source: str):
        warnings: list[tuple[str, str]] = []

        def warn(message, line=None, column=None, code="PW200"):
            warnings.append((code, message))

        ast = Parser(source).parse()
        ast = simplify_program(ast, warn)
        return ast, warnings

    def test_if_false_removes_then_branch(self) -> None:
        ast, warnings = self._simplify(
            'if false { print("DEAD"); } else { print("ALIVE"); }'
        )
        text = repr(ast)
        self.assertNotIn("DEAD", text)
        self.assertIn("ALIVE", text)
        self.assertIn(
            ("PW211", "condition is always false, this branch has no effect"),
            warnings,
        )

    def test_if_true_removes_else_branch(self) -> None:
        ast, warnings = self._simplify(
            'if true { print("ALIVE"); } else { print("DEAD"); }'
        )
        text = repr(ast)
        self.assertIn("ALIVE", text)
        self.assertNotIn("DEAD", text)
        self.assertIn(("PW214", "else branch is unreachable"), warnings)

    def test_if_false_without_else_becomes_empty_block(self) -> None:
        ast, warnings = self._simplify('if false { print("DEAD"); }')
        self.assertNotIn("DEAD", repr(ast))
        self.assertEqual(ast[0]["type"].name, "BLOCK_STATEMENT")
        self.assertEqual(ast[0]["value"], [])
        self.assertTrue(any(code == "PW211" for code, _ in warnings))

    def test_warning_is_printed_and_branch_is_skipped(self) -> None:
        result = run_source(
            'if false { print("DEAD"); } else { print("ALIVE"); }\n'
        )
        self.assertEqual(result.stdout, "ALIVE")
        self.assertIn("condition is always false", result.stderr)

    def test_no_warnings_flag_suppresses_constant_condition_warning(self) -> None:
        result = run_source(
            'if false { print("DEAD"); }\n',
            args=("--no-warnings",),
        )
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
