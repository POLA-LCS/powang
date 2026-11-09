"""Cross-module type checking."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_file, write_po  # noqa: E402


class CrossModuleRuntimeTests(unittest.TestCase):
    def test_aliased_function_and_variable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/mathlib.po",
                "module mathlib;\n"
                "export fun add(a: int, b: int): int >> a + b;\n"
                "export version: int = 3;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/mathlib.po" as m;\n'
                'print(m.add(2, 3)); print(" ");\n'
                'print(m.version); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "5 3\n")

    def test_wildcard_import_type_and_function(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/geometry.po",
                "module geometry;\n"
                "export type Point[+] {\n"
                "    | x: int;\n"
                "    | y: int;\n"
                "}\n"
                "export fun distance(a: Point, b: Point): int {\n"
                "    dx: int = a.x - b.x;\n"
                "    dy: int = a.y - b.y;\n"
                "    return dx * dx + dy * dy;\n"
                "}\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/geometry.po" as *;\n'
                "a: Point = Point.[0, 0];\n"
                "b: Point = Point.[3, 4];\n"
                'print(distance(a, b)); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "25\n")

    def test_qualified_type_annotation_and_construction(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/geometry.po",
                "module geometry;\n"
                "export type Point[+] {\n"
                "    | x: int;\n"
                "    | y: int;\n"
                "}\n"
                "export fun distance(a: Point, b: Point): int {\n"
                "    dx: int = a.x - b.x;\n"
                "    dy: int = a.y - b.y;\n"
                "    return dx * dx + dy * dy;\n"
                "}\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/geometry.po" as g;\n'
                "a: g.Point = g.Point.[0, 0];\n"
                "b: g.Point = g.Point.[3, 4];\n"
                'print(g.distance(a, b)); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "25\n")

    def test_directory_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/geometry_dir/use.po",
                "module geometry;\n"
                "export fun square(value: int): int >> value * value;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/geometry_dir" as geo;\n'
                'print(geo.square(5)); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "25\n")

    def test_legacy_module_without_exports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/legacy.po",
                "module legacy;\n"
                "fun hello(name: str): str >> \"hello \" + name;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/legacy.po" as legacy;\n'
                'print(legacy.hello("x")); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "hello x\n")

    def test_imported_generic_function(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/generic.po",
                "module generic;\n"
                "export fun first[T](values: T...): T >> values[0];\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/generic.po" as g;\n'
                'print(g.first(7, 8, 9)); print(" ");\n'
                'print(g.first("a", "b")); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "7 a\n")

    def test_imported_trait_constraint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/traitlib.po",
                "module traitlib;\n"
                "export trait Drawable { fun draw(): str; }\n"
                "export fun render[T: Drawable](value: T): str >> value.draw();\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/traitlib.po" as g;\n'
                "type Screen[+] { fun this.draw(): str >> \"screen\"; }\n"
                'print(g.render(Screen.[])); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "screen\n")

    def test_imported_trait_annotation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/shapes.po",
                "module shapes;\n"
                "export trait Named {\n"
                "    | name: str;\n"
                "    fun label(): str;\n"
                "    fun describe(): str >> this.label();\n"
                "}\n"
                "export type Person[+] {\n"
                "    | name: str;\n"
                "    fun this.label(): str >> this.name;\n"
                "}\n"
                "export fun render(value: Named): str >> value.describe();\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/shapes.po" as s;\n'
                "p: s.Named = s.Person.[\"Ada\"];\n"
                'print(s.render(p)); print("\\n");\n',
            )
            result = run_file(main)
        self.assertEqual(result.stdout, "Ada\n")


class CrossModuleDiagnosticTests(unittest.TestCase):
    def test_wrong_argument_type_at_call_site(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/mathlib.po",
                "module mathlib;\n"
                "export fun add(a: int, b: int): int >> a + b;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/mathlib.po" as m;\n'
                "\n"
                'm.add("a", 2);\n',
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ln: 3", result.combined)
        self.assertIn("expected int", result.combined)
        self.assertIn("but str", result.combined)

    def test_imported_variable_type_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/config.po",
                "module config;\n"
                "export value: str = \"x\";\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/config.po" as c;\n'
                "number: int = c.value;\n",
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ln: 2", result.combined)
        self.assertIn("expected int", result.combined)
        self.assertIn("but str", result.combined)

    def test_missing_module_member(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/mathlib.po",
                "module mathlib;\n"
                "export fun add(a: int, b: int): int >> a + b;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/mathlib.po" as m;\n'
                "m.missing();\n",
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no function named 'missing'", result.combined)

    def test_missing_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            main = write_po(
                root,
                "main.po",
                'use "./lib/missing.po" as m;\n',
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot find module 'missing'", result.combined)

    def test_module_internal_error_reported_at_import(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/bad.po",
                "module bad;\n"
                "export fun broken(): int >> \"not int\";\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/bad.po" as bad;\n'
                "print(bad.broken());\n",
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ln: 1", result.combined)
        self.assertIn("module 'bad' has type errors", result.combined)
        self.assertIn("expected int", result.combined)

    def test_import_cycle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/cycle_a.po",
                "module cycle_a;\n"
                'use "./cycle_b.po" as b;\n'
                "export fun a(): int >> 1;\n",
            )
            write_po(
                root,
                "lib/cycle_b.po",
                "module cycle_b;\n"
                'use "./cycle_a.po" as a;\n'
                "export fun b(): int >> 2;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/cycle_a.po" as a;\n'
                "print(a.a());\n",
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cyclic module import", result.combined)

    def test_wildcard_import_collision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/hello.po",
                "module hello;\n"
                "export fun hello(): int >> 1;\n",
            )
            main = write_po(
                root,
                "main.po",
                "fun hello(): int >> 2;\n"
                'use "./lib/hello.po" as *;\n',
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("wildcard import collides with function 'hello'", result.combined)

    def test_imported_function_arity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-cross-") as directory:
            root = Path(directory)
            write_po(
                root,
                "lib/mathlib.po",
                "module mathlib;\n"
                "export fun add(a: int, b: int): int >> a + b;\n",
            )
            main = write_po(
                root,
                "main.po",
                'use "./lib/mathlib.po" as m;\n'
                "m.add(1);\n",
            )
            result = run_file(main, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("received too few arguments", result.combined)


if __name__ == "__main__":
    unittest.main()
