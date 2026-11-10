"""Bare, relative and explicit module resolution."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_file, write_po  # noqa: E402


class ModuleResolutionTests(unittest.TestCase):
    def test_relative_sibling_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-rel-module-") as directory:
            root = Path(directory)
            write_po(
                root,
                "helper.po",
                "module helper;\nexport fun value(): int >> 7;\n",
            )
            main = write_po(
                root,
                "main.po",
                "use .helper as helper;\n"
                "println(helper.value());\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "7\n")

    def test_relative_parent_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-rel-parent-") as directory:
            root = Path(directory)
            write_po(
                root,
                "shared.po",
                "module shared;\nexport fun value(): int >> 9;\n",
            )
            (root / "app").mkdir()
            main = write_po(
                root,
                "app/main.po",
                "use ..shared as shared;\n"
                "println(shared.value());\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "9\n")

    def test_relative_grandparent_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-rel-grand-") as directory:
            root = Path(directory)
            write_po(
                root,
                "shared.po",
                "module shared;\nexport fun value(): int >> 9;\n",
            )
            (root / "app" / "deep").mkdir(parents=True)
            main = write_po(
                root,
                "app/deep/main.po",
                "use ...shared as shared;\n"
                "println(shared.value());\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "9\n")

    def test_relative_directory_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-rel-dir-") as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            write_po(
                root,
                "lib/a.po",
                "module lib;\nexport fun value(): int >> 42;\n",
            )
            main = write_po(
                root,
                "main.po",
                "use .lib as lib;\n"
                "println(lib.value());\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "42\n")

    def test_bare_name_does_not_search_input_modules(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-bare-module-") as directory:
            root = Path(directory)
            (root / "modules" / "local").mkdir(parents=True)
            write_po(
                root,
                "modules/local/use.po",
                "module local;\nexport fun value(): int >> 99;\n",
            )
            main = write_po(
                root,
                "main.po",
                "use local;\nprint(local.value());\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot find module 'local'", result.combined)

    def test_bare_name_finds_builtin_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-builtin-module-") as directory:
            main = write_po(
                Path(directory),
                "main.po",
                "use math;\nprintln(math.sqrt(9));\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "3.0\n")

    def test_explicit_path_import_still_works(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-path-module-") as directory:
            root = Path(directory)
            write_po(
                root,
                "helper.po",
                "module helper;\nexport fun value(): int >> 7;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./helper.po" as helper;\n'
                "println(helper.value());\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "7\n")

    def test_nested_relative_module_inside_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-nested-module-") as directory:
            root = Path(directory)
            (root / "lib").mkdir()
            write_po(
                root,
                "lib/helper.po",
                "module helper;\nexport fun base_value(): int >> 7;\n",
            )
            write_po(
                root,
                "lib/main.po",
                "module lib;\n"
                "use .helper as helper;\n"
                "export fun value(): int >> helper.base_value() + 1;\n",
            )
            main = write_po(
                root,
                "main.po",
                "use .lib as lib;\n"
                "println(lib.value());\n",
            )
            result = run_file(main)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "8\n")

    def test_relative_module_type_checking(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-check-module-") as directory:
            root = Path(directory)
            write_po(
                root,
                "helper.po",
                "module helper;\nexport fun value(): int >> 7;\n",
            )
            main = write_po(
                root,
                "main.po",
                "use .helper as helper;\n"
                "println(helper.value());\n",
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 0, result.combined)


if __name__ == "__main__":
    unittest.main()
