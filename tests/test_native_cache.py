"""Warm executable cache tests for the integrated native path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.loader import compile_image
from src.vm.native.session import compile_native_file


class NativeCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_second_compile_uses_the_cache(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="powang-native-cache-",
        ) as directory:
            path = Path(directory) / "program.po"
            path.write_text(
                "print(1 + 2);\n", encoding="utf-8", newline="\n",
            )
            session = compile_native_file(path)
            first = compile_image(
                session.image, bundle=session.bundle, use_cache=True,
            )
            second = compile_image(
                session.image, bundle=session.bundle, use_cache=True,
            )
            self.assertIsNotNone(first.compile_result)
            self.assertIsNone(second.compile_result)
            self.assertFalse(second.temporary)
            self.assertTrue(second.executable.is_file())


if __name__ == "__main__":
    unittest.main()
