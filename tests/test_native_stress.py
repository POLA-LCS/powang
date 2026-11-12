"""Native startup and task lifecycle stress checks."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.loader import compile_image, run_native
from src.vm.native.session import compile_native_file


class NativeStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_one_hundred_native_startups(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="powang-native-stress-",
        ) as directory:
            path = Path(directory) / "program.po"
            path.write_text(
                "print(1 + 2);\n", encoding="utf-8", newline="\n",
            )
            session = compile_native_file(path)
            program = compile_image(
                session.image, bundle=session.bundle,
            )
            try:
                for index in range(100):
                    completed = subprocess.run(
                        [str(program.executable)],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=30,
                    )
                    self.assertEqual(
                        completed.returncode, 0,
                        f"run {index}: {completed.stderr}",
                    )
                    self.assertEqual(completed.stdout, "3")
            finally:
                program.cleanup()

    def test_many_task_lifecycles(self) -> None:
        source = (
            "async fun value(input: int): int >> input;\n"
            "fun worker(value: int): int >> value + 1;\n"
            "async fun run(): int {\n"
            "    total := 0;\n"
            "    count := 0;\n"
            "    loop if count < 100 {\n"
            "        pending := value(count);\n"
            "        total += await pending;\n"
            "        count += 1;\n"
            "    }\n"
            "    return total;\n"
            "}\n"
            "fun run_workers(): int {\n"
            "    total := 0;\n"
            "    count := 0;\n"
            "    loop if count < 100 {\n"
            "        pending := spawn worker(count);\n"
            "        total += wait(pending);\n"
            "        count += 1;\n"
            "    }\n"
            "    return total;\n"
            "}\n"
            'print(await run()); print(" "); print(run_workers()); print("\\n");\n'
        )
        with tempfile.TemporaryDirectory(
            prefix="powang-native-task-stress-",
        ) as directory:
            path = Path(directory) / "tasks.po"
            path.write_text(source, encoding="utf-8", newline="\n")
            session = compile_native_file(path)
            result = run_native(
                session.image, bundle=session.bundle, timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "4950 5050\n")


if __name__ == "__main__":
    unittest.main()
