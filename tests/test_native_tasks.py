"""Native N5 host input and task boundary tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.loader import run_native
from src.vm.native.session import compile_native_file
from tests.helpers import run_source_with_input


class NativeTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_native_input_matches_python(self) -> None:
        source = (
            "name := input();\n"
            'print("hi "); print(name); print("\\n");\n'
        )
        with tempfile.TemporaryDirectory(
            prefix="powang-native-input-",
        ) as directory:
            path = Path(directory) / "input.po"
            path.write_text(source, encoding="utf-8", newline="\n")
            session = compile_native_file(path)
            native = run_native(
                session.image,
                bundle=session.bundle,
                input_text="Ada\n",
            )
        python = run_source_with_input(source, "Ada\n")
        self.assertEqual(native.returncode, python.returncode)
        self.assertEqual(native.stdout, python.stdout)
        self.assertEqual(native.stderr, python.stderr)

    def test_native_task_status_names(self) -> None:
        source = (
            "async fun value(): int >> 1;\n"
            "task := value();\n"
            "print(task_status(task)); print(\" \");\n"
            "print(wait(task)); print(\" \");\n"
            "print(task_status(task)); print(\"\\n\");\n"
        )
        with tempfile.TemporaryDirectory(
            prefix="powang-native-task-",
        ) as directory:
            path = Path(directory) / "tasks.po"
            path.write_text(source, encoding="utf-8", newline="\n")
            session = compile_native_file(path)
            native = run_native(session.image, bundle=session.bundle)
        self.assertEqual(native.returncode, 0, native.stderr)
        self.assertEqual(native.stdout, "pending 1 done\n")


if __name__ == "__main__":
    unittest.main()
