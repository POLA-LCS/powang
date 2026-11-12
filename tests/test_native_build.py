"""N0 gate tests for the integrated native build.

The suite builds the native runtime once, then exercises the in-memory
``temp.cpp`` generator, the g++ driver, the packaged executable and the
``powang vm native`` commands.
"""

from __future__ import annotations

import io
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.vm.compiler import compile_source
from src.vm.disasm import disassemble_code
from src.vm.image import CodeObject, ModuleInfo, ProgramImage
from src.vm.native import gen_opcodes
from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import (
    CAPTURE_LIMIT,
    TRUNCATION_MARKER,
    IntegratedGcc,
    NativeBuildError,
    _truncate,
)
from src.vm.native.loader import run_native
from src.vm.native.source_gen import (
    render_temp_cpp,
    render_temp_cpp_buffer,
)
from src.vm.opcodes import BY_NAME
from src.vm.verifier import VerificationError, verify_image

from tests.helpers import run_command, write_po


class NativeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.paths = ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(
                f"native toolchain unavailable: {error}"
            ) from error

    def _compile(self, source: str) -> ProgramImage:
        return compile_source(
            source, path="program.po", module_name="program", check=False,
        )

    def test_generated_opcode_header_is_current(self) -> None:
        self.assertEqual(
            gen_opcodes.HEADER_PATH.read_bytes(),
            gen_opcodes.render_header().encode("utf-8"),
        )

    def test_source_generator_returns_seeked_buffer(self) -> None:
        image = self._compile("print(1 + 2);\n")
        buffer = render_temp_cpp_buffer(image)
        self.assertIsInstance(buffer, io.StringIO)
        self.assertEqual(buffer.tell(), 0)
        text = buffer.getvalue()
        self.assertIn("kPwbImage", text)
        self.assertIn("kPwbImageSize", text)
        self.assertIn("run_embedded_image", text)

    def test_native_print_expression(self) -> None:
        image = self._compile("print(1 + 2);\n")
        result = run_native(image, paths=self.paths)
        self.assertEqual(result.stdout, "3")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 0)

    def test_native_number_semantics(self) -> None:
        cases = (
            # Int left arithmetic casts the num right operand to int.
            ("print(5 + 2.5);\n", "7"),
            ("print(5 - 2.5);\n", "3"),
            ("print(5 * 2.5);\n", "10"),
            ("print(5 / 2.0);\n", "2"),
            ("print(5 % 2.5);\n", "1"),
            # Num left arithmetic casts the int right operand to num.
            ("print(2.5 + 5);\n", "7.5"),
            ("print(2.5 - 5);\n", "-2.5"),
            ("print(2.5 * 5);\n", "12.5"),
            ("print(2.5 / 5);\n", "0.5"),
            ("print(2.5 % 5);\n", "2.5"),
            # Int left comparison casts the num right operand to int.
            ("print(1 == 1.5);\n", "true"),
            ("print(1 != 1.5);\n", "false"),
            ("print(1 < 1.5);\n", "false"),
            ("print(1 <= 1.5);\n", "true"),
            ("print(4611686018427387903 == 4611686018427387904.0);\n",
             "false"),
            # Num left comparison casts the int right operand to num.
            ("print(2.5 == 1);\n", "false"),
            ("print(1.5 == 1);\n", "false"),
            ("print(2.5 > 1);\n", "true"),
            # Bool uses the Python comparison casts.
            ("print(true == 1);\n", "true"),
            ("print(true == 1.5);\n", "true"),
            ("print(true == 2);\n", "true"),
            ("print(false == 0.5);\n", "false"),
            ("print(true); print(false);\n", "truefalse"),
            # Float modulo follows the divisor sign, including signed zero.
            ("print(-1.0 % 3.0);\n", "2.0"),
            ("print(1.0 % -3.0);\n", "-2.0"),
            ("print(3.0 % -3.0);\n", "-0.0"),
            ("print(-3.0 % 3.0);\n", "0.0"),
            # Division and modulo by zero yield nova instead of throwing.
            ("print(1 / 0);\n", "nova"),
            ("print(1 % 0);\n", "nova"),
            ("print(1.0 / 0.0);\n", "nova"),
            ("print(1.0 % 0.0);\n", "nova"),
            # Negative division truncates the double quotient toward zero.
            ("print(-5 / 2.0);\n", "-2"),
            ("print(-5 % 2.5);\n", "1"),
            ("print(5 % -2.5);\n", "-1"),
            ("print(1 % 0.5);\n", "nova"),
            # println accepts zero arguments and emits one newline.
            ("println();\n", "\n"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                image = self._compile(source)
                result = run_native(image, paths=self.paths)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_native_print_arity(self) -> None:
        image = self._compile("print();\n")
        result = run_native(image, paths=self.paths)
        self.assertEqual(result.returncode, 1)
        self.assertIn("print", result.stderr)
        self.assertIn("too few arguments", result.stderr)

    def test_native_verifier_accepts_loop_image(self) -> None:
        image = self._compile("for n >> [1 2 3] { print(n); }\n")
        with tempfile.TemporaryDirectory(
            prefix="powang-native-test-"
        ) as directory:
            image_path = Path(directory) / "loop.pwb"
            image_path.write_bytes(image.to_bytes())
            completed = subprocess.run(
                [str(self.paths.executable), "verify", str(image_path)],
                capture_output=True,
                timeout=60,
            )
        self.assertEqual(
            completed.returncode, 0,
            completed.stderr.decode("utf-8", errors="replace"),
        )
        self.assertEqual(completed.stdout, b"ok\n")

    def test_native_verifier_rejects_bad_jump(self) -> None:
        bytecode = bytes([BY_NAME["JUMP"].opcode]) + struct.pack("<i", 5)
        image = ProgramImage(
            entry_module=0,
            entry_code=0,
            modules=[
                ModuleInfo(name="program", path="program.po", code_index=0),
            ],
            codes=[
                CodeObject(
                    name="program",
                    bytecode=bytecode,
                    max_stack=0,
                ),
            ],
        )
        with self.assertRaises(VerificationError):
            verify_image(image)
        with tempfile.TemporaryDirectory(
            prefix="powang-native-test-"
        ) as directory:
            image_path = Path(directory) / "bad-jump.pwb"
            image_path.write_bytes(image.to_bytes())
            completed = subprocess.run(
                [str(self.paths.executable), "verify", str(image_path)],
                capture_output=True,
                timeout=60,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn(b"jump target", completed.stderr)

    def test_native_disassembly_matches_python(self) -> None:
        image = self._compile("print(1 + 2);\n")
        with tempfile.TemporaryDirectory(prefix="powang-native-test-") as directory:
            image_path = Path(directory) / "program.pwb"
            image_path.write_bytes(image.to_bytes())
            completed = subprocess.run(
                [str(self.paths.executable), "disasm", str(image_path)],
                capture_output=True,
                timeout=60,
            )
        expected = disassemble_code(image.codes[image.entry_code], image)
        self.assertEqual(completed.stdout, expected.encode("utf-8"))
        self.assertEqual(
            completed.returncode, 0,
            completed.stderr.decode("utf-8", errors="replace"),
        )

    def test_native_rejects_corrupt_image(self) -> None:
        image = self._compile("print(1 + 2);\n")
        payload = bytearray(image.to_bytes())
        payload[-1] ^= 0xFF
        with tempfile.TemporaryDirectory(prefix="powang-native-test-") as directory:
            image_path = Path(directory) / "corrupt.pwb"
            image_path.write_bytes(bytes(payload))
            completed = subprocess.run(
                [str(self.paths.executable), "run", str(image_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("checksum", completed.stderr)

    def test_integrated_compiler_reports_diagnostics(self) -> None:
        driver = IntegratedGcc(
            include_dir=self.paths.include_dir,
            library_dir=self.paths.build_dir,
        )
        with tempfile.TemporaryDirectory(prefix="powang-native-test-") as directory:
            output = Path(directory) / "broken.exe"
            result = driver.compile("int main( {\n", output)
        self.assertFalse(result.ok)
        self.assertIn("error", result.stderr.lower())
        self.assertIn("temp.cpp", result.stderr)

    def test_capture_truncation_is_byte_aware(self) -> None:
        self.assertEqual(
            _truncate("x" * CAPTURE_LIMIT), "x" * CAPTURE_LIMIT,
        )
        marker_bytes = len(TRUNCATION_MARKER.encode("utf-8"))
        mixed = ("a" * (CAPTURE_LIMIT - 1)) + ("\u00e9" * 64)
        bounded = _truncate(mixed)
        self.assertTrue(bounded.endswith(TRUNCATION_MARKER))
        self.assertNotIn("\ufffd", bounded)
        self.assertLessEqual(
            len(bounded.encode("utf-8")), CAPTURE_LIMIT + marker_bytes,
        )
        wide = "\u00e9" * ((CAPTURE_LIMIT // 2) + 1)
        self.assertTrue(_truncate(wide).endswith(TRUNCATION_MARKER))

    def test_failed_compile_removes_stale_output(self) -> None:
        image = self._compile("print(1 + 2);\n")
        driver = IntegratedGcc(
            include_dir=self.paths.include_dir,
            library_dir=self.paths.build_dir,
        )
        with tempfile.TemporaryDirectory(
            prefix="powang-native-test-"
        ) as directory:
            output = Path(directory) / "app.exe"
            first = driver.compile(render_temp_cpp(image), output)
            self.assertTrue(first.ok, first.stderr)
            self.assertTrue(output.exists())
            second = driver.compile("int main( {\n", output)
            self.assertFalse(second.ok)
            self.assertFalse(output.exists())

    def test_integrated_compiler_missing(self) -> None:
        driver = IntegratedGcc(
            compiler="powang-no-such-compiler",
            include_dir=self.paths.include_dir,
            library_dir=self.paths.build_dir,
        )
        with tempfile.TemporaryDirectory(
            prefix="powang-native-test-"
        ) as directory:
            output = Path(directory) / "missing.exe"
            result = driver.compile("int main() { return 0; }\n", output)
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, -1)
        self.assertIn("compiler not found", result.stderr)

    def test_integrated_compiler_stdin(self) -> None:
        image = self._compile("print(1 + 2);\n")
        driver = IntegratedGcc(
            include_dir=self.paths.include_dir,
            library_dir=self.paths.build_dir,
        )
        with tempfile.TemporaryDirectory(
            prefix="powang-native-test-"
        ) as directory:
            root = Path(directory)
            name = "app.exe" if os.name == "nt" else "app"
            output = root / name
            result = driver.compile(
                render_temp_cpp(image), output, use_stdin=True,
            )
            self.assertTrue(result.ok, result.stderr)
            self.assertTrue(output.exists())
            completed = subprocess.run(
                [str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "3")

    def test_compile_leaves_no_temp_cpp(self) -> None:
        image = self._compile("print(1 + 2);\n")
        driver = IntegratedGcc(
            include_dir=self.paths.include_dir,
            library_dir=self.paths.build_dir,
        )
        with tempfile.TemporaryDirectory(prefix="powang-native-test-") as directory:
            root = Path(directory)
            output = root / "app.exe"
            result = driver.compile(render_temp_cpp(image), output)
            self.assertTrue(result.ok, result.stderr)
            self.assertTrue(output.exists())
            self.assertFalse((output.parent / "temp.cpp").exists())
            self.assertIsNone(result.source_path)

    def test_cli_native_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-native-test-") as directory:
            path = write_po(directory, "program.po", "print(1 + 2);\n")
            result = run_command(
                ["vm", "native", "run", str(path)], timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "3")

    def test_cli_native_compile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-native-test-") as directory:
            root = Path(directory)
            path = write_po(directory, "program.po", "print(1 + 2);\n")
            output = root / "app.exe"
            result = run_command(
                [
                    "vm", "native", "compile",
                    "--output", str(output), str(path),
                ],
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.combined)
            self.assertTrue(output.exists())
            if os.name == "nt":
                self.assertEqual(output.read_bytes()[:2], b"MZ")

    def test_native_info(self) -> None:
        result = run_command(["vm", "native", "info"], timeout=120)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn("compiler", result.stdout)


if __name__ == "__main__":
    unittest.main()
