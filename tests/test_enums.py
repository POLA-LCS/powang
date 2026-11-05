"""Enum tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class EnumTests(unittest.TestCase):
    def test_enum_declaration_and_access(self) -> None:
        result = run_source(
            'type Color enum {\n'
            '    RED,\n'
            '    GREEN,\n'
            '    BLUE,\n'
            '}\n'
            'println(Color.RED);\n'
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["<Color: RED>"])

    def test_enum_variable_and_comparison(self) -> None:
        result = run_source(
            'type Color enum {\n'
            '    RED,\n'
            '    GREEN,\n'
            '    BLUE,\n'
            '}\n'
            'c: Color = Color.RED;\n'
            'println(c == Color.RED);\n'
            'println(c == Color.BLUE);\n'
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["true", "false"])

    def test_enum_type_check(self) -> None:
        result = run_source(
            'type Color enum {\n'
            '    RED,\n'
            '    GREEN,\n'
            '    BLUE,\n'
            '}\n'
            'c: Color = Color.RED;\n'
            'println(c :: Color);\n'
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["true"])

    def test_enum_in_function(self) -> None:
        result = run_source(
            'type Color enum {\n'
            '    RED,\n'
            '    GREEN,\n'
            '    BLUE,\n'
            '}\n'
            'fun describe(c: Color): str {\n'
            '    if c == Color.RED { return "red"; }\n'
            '    if c == Color.GREEN { return "green"; }\n'
            '    return "blue";\n'
            '}\n'
            'println(describe(Color.RED));\n'
            'println(describe(Color.GREEN));\n'
            'println(describe(Color.BLUE));\n'
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["red", "green", "blue"])

    def test_enum_typeof(self) -> None:
        result = run_source(
            'type Color enum {\n'
            '    RED,\n'
            '    GREEN,\n'
            '    BLUE,\n'
            '}\n'
            'println(typeof(Color.RED));\n'
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.lines, ["Color"])


if __name__ == "__main__":
    unittest.main()
