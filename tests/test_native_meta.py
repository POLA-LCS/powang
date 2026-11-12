"""PWBM metadata generation and native round trip tests for N1."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.vm.compiler import compile_source
from src.vm.native.build import RuntimePaths, ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.meta import build_meta, parse_meta
from src.vm.native.source_gen import render_temp_cpp_buffer


SOURCE = """
fun add(a: int, b: int): int {
    return a + b;
}

fun greet(name: str = "world"): str {
    return "hi " + name;
}

fun sum(values: int...): int {
    total := 0;
    for value >> values {
        total = total + value;
    }
    return total;
}

print(add(1, 2));
"""


class NativeMetaTests(unittest.TestCase):
    paths: RuntimePaths

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.paths = ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def _image(self, source: str = SOURCE):
        return compile_source(
            source,
            path="program.po",
            module_name="program",
            check=False,
        )

    def test_meta_is_deterministic(self) -> None:
        image = self._image()
        first = build_meta(image)
        second = build_meta(image)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith(b"PWBM"))

    def test_meta_hash(self) -> None:
        image = self._image()
        block = parse_meta(build_meta(image))
        self.assertEqual(
            block.image_hash,
            hashlib.sha256(image.to_bytes()).digest(),
        )

    def test_meta_function_metadata(self) -> None:
        image = self._image()
        block = parse_meta(build_meta(image))
        self.assertEqual(len(block.functions), 3)
        functions = {function.name: function for function in block.functions}

        add = functions["add"]
        self.assertEqual(add.code_index, 0)
        self.assertEqual(add.min_argc, 2)
        self.assertEqual(add.variadic_index, -1)
        self.assertEqual([parameter.name for parameter in add.parameters], ["a", "b"])
        self.assertEqual(list(add.defaults), [-1, -1])
        self.assertEqual(
            [parameter.default_index for parameter in add.parameters],
            [-1, -1],
        )

        greet = functions["greet"]
        self.assertEqual(greet.min_argc, 0)
        self.assertEqual(len(greet.parameters), 1)
        self.assertEqual(greet.parameters[0].name, "name")
        self.assertEqual(greet.parameters[0].default_index, 1)
        self.assertEqual(greet.parameters[0].flags & 8, 8)

        total = functions["sum"]
        self.assertEqual(total.variadic_index, 0)
        self.assertEqual(total.flags & 2, 2)
        self.assertEqual(total.parameters[0].name, "values")
        self.assertEqual(total.parameters[0].flags & 4, 4)

        type_names = {index: spec.name for index, spec in enumerate(block.types)}
        self.assertEqual(type_names[add.parameters[0].type_index], "int")
        self.assertEqual(type_names[greet.parameters[0].type_index], "str")

    def test_meta_cpp_roundtrip(self) -> None:
        image = self._image()
        data = build_meta(image)
        block = parse_meta(data)
        with tempfile.TemporaryDirectory(prefix="powang-meta-") as directory:
            path = Path(directory) / "program.pwbm"
            path.write_bytes(data)
            completed = subprocess.run(
                [str(self.paths.executable), "meta", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("functions=3", completed.stdout)
        self.assertIn("types=2", completed.stdout)
        self.assertIn("name=add", completed.stdout)
        self.assertIn("name=greet", completed.stdout)
        self.assertIn("name=sum", completed.stdout)
        self.assertIn(block.image_hash.hex(), completed.stdout)

    def test_source_generator_embeds_meta(self) -> None:
        image = self._image()
        buffer = render_temp_cpp_buffer(image)
        self.assertIsInstance(buffer, io.StringIO)
        self.assertEqual(buffer.tell(), 0)
        text = buffer.getvalue()
        self.assertIn("kPwbMeta", text)
        self.assertIn("kPwbMetaSize", text)
        self.assertIn("run_embedded_image_with_meta", text)
        self.assertIn("kPwbImage", text)


if __name__ == "__main__":
    unittest.main()
