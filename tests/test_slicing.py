"""Slicing and negative indexing for strings, arrays and tuples."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class SlicingTests(unittest.TestCase):
    def test_string_slice_copy(self) -> None:
        result = run_source(
            'text := "abcdef";\n'
            'print(text[>>]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "abcdef\n")

    def test_string_slice_open_ends(self) -> None:
        result = run_source(
            'text := "abcdef";\n'
            'print(text[2 >>]); print(" ");\n'
            'print(text[>> 3]); print(" ");\n'
            'print(text[1 >> 4]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "cdef abc bcd\n")

    def test_string_slice_negative_indices(self) -> None:
        result = run_source(
            'text := "abcdef";\n'
            'print(text[-3 >>]); print(" ");\n'
            'print(text[>> -1]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "def abcde\n")

    def test_string_slice_empty_and_clamped(self) -> None:
        result = run_source(
            'text := "abc";\n'
            'print(text[2 >> 1]); print("|");\n'
            'print(text[>> 100]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "|abc\n")

    def test_array_slice(self) -> None:
        result = run_source(
            "values := [1, 2, 3, 4];\n"
            "sliced := values[1 >> 3];\n"
            'print(size(sliced)); print(" "); print(sliced[0]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "2 2\n")

    def test_tuple_slice(self) -> None:
        result = run_source(
            "values := .[1, 2, 3, 4];\n"
            "sliced := values[1 >> 3];\n"
            'print(size(sliced)); print(" "); print(sliced[0]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "2 2\n")

    def test_negative_ordinary_indexing(self) -> None:
        result = run_source(
            'text := "abc";\n'
            "values := [1, 2, 3];\n"
            "pair := .[4, 5, 6];\n"
            'print(text[-1]); print(" ");\n'
            'print(values[-1]); print(" "); print(pair[-1]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "c 3 6\n")

    def test_negative_out_of_bounds_is_rejected(self) -> None:
        result = run_source(
            "values := [1, 2, 3];\n"
            'print(values[-10]); print("\\n");\n'
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("out of range", result.combined.lower())

    def test_slice_index_must_be_int(self) -> None:
        result = run_source(
            "values := [1, 2, 3];\n"
            'print(values["a" >> 2]); print("\\n");\n'
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("slice index", result.combined)


if __name__ == "__main__":
    unittest.main()
