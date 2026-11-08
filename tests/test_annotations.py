"""Built-in annotations: obj, task, file, handle and error."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_file, run_source, write_po  # noqa: E402


class AnnotationTests(unittest.TestCase):
    def test_obj_accepts_user_instances(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; }\n"
            "p: obj = Point.[1];\n"
            'print(typeof(p)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "Point\n")

    def test_obj_member_access_requires_a_cast(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; }\n"
            "p: obj = Point.[1];\n"
            'print(p.x); print("\\n");\n'
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires a cast or trait", result.combined)

    def test_obj_cast_to_concrete_type(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; }\n"
            "p: obj = Point.[1];\n"
            "q: Point = p as Point;\n"
            'print(q.x); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "1\n")

    def test_task_annotation(self) -> None:
        result = run_source(
            "fun work(): int { return 7; }\n"
            "t: task = spawn work();\n"
            'print(typeof(t)); print(" "); print(wait(t)); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "task 7\n")

    def test_error_annotation(self) -> None:
        result = run_source(
            'e: error = fail("KIND", "boom");\n'
            'print(typeof(e)); print(" "); print(e.kind); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "error KIND\n")

    def test_file_annotation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-file-") as directory:
            path = write_po(
                directory,
                "main.po",
                'f: file = file.open("data.txt", "write");\n'
                'print(typeof(f)); print("\\n");\n'
                'file.write(f, "hi");\n'
                "file.close(f);\n",
            )
            result = run_file(path, cwd=directory)
        self.assertEqual(result.stdout, "file\n")

    def test_handle_and_file_annotations_check(self) -> None:
        result = run_source(
            "h: handle;\n"
            "f: file;\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 0, result.combined)


if __name__ == "__main__":
    unittest.main()
