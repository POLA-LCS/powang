"""Diagnostics characterization: stable ``[KIND ERROR]`` text, no raw tracebacks."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import (  # noqa: E402
    ROOT,
    assert_no_traceback,
    run_command,
    run_file,
    run_source,
)

DIAGNOSTIC_RE = re.compile(r"\[[A-Z]+ ERROR\]")


class ErrorDiagnosticTests(unittest.TestCase):
    def assert_diagnostic(self, result, kind: str, fragment: str) -> None:
        self.assertIn(f"[{kind} ERROR]", result.combined)
        self.assertRegex(result.combined, DIAGNOSTIC_RE)
        self.assertIn(fragment, result.combined)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)

    def test_top_level_return_is_rejected(self) -> None:
        result = run_source("return 5;\n")
        self.assert_diagnostic(result, "LOGIC", "non function scope")
        self.assertIn("[LOGIC ERROR]", result.stdout)
        self.assertIn("the scope you are trying to return from it's global", result.stdout)
        self.assertIn("|", result.stdout)
        self.assertNotIn("Traceback (most recent call last)", result.combined)

    def test_zero_array_chunk_size_is_rejected(self) -> None:
        result = run_source("output(0 / [1 2 3]);\n")
        self.assert_diagnostic(result, "VALUE", "Chunk size must be positive")
        self.assertIn("non-positive size 0", result.stdout)
        self.assertIn("[VALUE ERROR]", result.stdout)

    def test_unknown_identifier(self) -> None:
        result = run_source("output(nope);\n")
        self.assert_diagnostic(result, "IDENTIFIER", "nope")
        self.assertIn("doens't exists", result.stdout)

    def test_type_mismatch_in_typed_declaration(self) -> None:
        result = run_source('x: integer = "hi";\n')
        self.assert_diagnostic(result, "TYPE", "expected integer")
        self.assertIn("but string was encounter", result.stdout)

    def test_syntax_error(self) -> None:
        result = run_source("output(1 +);\n")
        self.assert_diagnostic(result, "SYNTAX", "Unexpected token")
        self.assertIn("expected literal", result.stdout)

    def test_user_error_builtin(self) -> None:
        result = run_source('error("boom", "detail");\n')
        self.assert_diagnostic(result, "USER", "boom")
        self.assertIn("detail", result.stdout)

    def test_missing_input_file(self) -> None:
        missing = ROOT / "tests" / "__does_not_exist__.po"
        result = run_file(missing)
        self.assert_diagnostic(result, "INPUT", "File not founded")
        self.assertIn("__does_not_exist__.po", result.stdout)

    def test_invalid_cli_flag(self) -> None:
        result = run_command(["--definitely-not-a-flag"])
        self.assert_diagnostic(result, "USAGE", "invalid flag")
        self.assertIn("definitely-not-a-flag", result.stdout)

    def test_language_errors_do_not_leak_python_assertions(self) -> None:
        cases = {
            "return": "return 1;\n",
            "identifier": "output(missing);\n",
            "chunk": "output(0 / [1 2]);\n",
            "syntax": "output(1 +);\n",
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                result = run_source(source)
                self.assertNotIn("Traceback (most recent call last)", result.combined)
                self.assertNotIn("AssertionError", result.stdout)
                self.assertRegex(result.combined, DIAGNOSTIC_RE)
                self.assertEqual(result.stderr, "")

    def test_successful_program_has_no_diagnostics(self) -> None:
        result = run_source('output("ok"); output("\\n");\n')
        self.assertEqual(result.stdout, "ok\n")
        self.assertNotIn("[ERROR]", result.combined)
        self.assertNotRegex(result.combined, DIAGNOSTIC_RE)
        self.assertEqual(result.stderr, "")
        assert_no_traceback(self, result)


if __name__ == "__main__":
    unittest.main()
