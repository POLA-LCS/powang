"""Structural traits, default methods and trait-qualified dispatch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_source  # noqa: E402


class TraitRuntimeTests(unittest.TestCase):
    def test_trait_annotation_and_default_method(self) -> None:
        result = run_source(
            "trait Drawable {\n"
            "    | name: str;\n"
            "    fun draw(): str;\n"
            "    fun describe(): str {\n"
            "        return $\"name={this.name} draw={this.draw()}\";\n"
            "    }\n"
            "}\n"
            "type Screen[+] {\n"
            "    | name: str;\n"
            "    fun this.draw(): str {\n"
            "        return \"screen\";\n"
            "    }\n"
            "}\n"
            "screen := Screen.[\"main\"];\n"
            "value: Drawable = screen;\n"
            "print(value.draw()); print(\" \");\n"
            "print(value.describe()); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "screen name=main draw=screen\n")

    def test_trait_qualified_methods_and_calls(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "trait Named { fun draw(): int; }\n"
            "type Screen[+] {\n"
            "    | name: str;\n"
            "    fun Drawable.draw(): str {\n"
            "        return \"screen\";\n"
            "    }\n"
            "    fun Named.draw(): int {\n"
            "        return 7;\n"
            "    }\n"
            "}\n"
            "screen := Screen.[\"main\"];\n"
            "value: Drawable = screen;\n"
            "print(value.draw()); print(\" \");\n"
            "print(Drawable.draw(screen)); print(\" \");\n"
            "print(Named.draw(screen)); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "screen screen 7\n")

    def test_default_method_uses_qualified_method(self) -> None:
        result = run_source(
            "trait Drawable {\n"
            "    fun draw(): str;\n"
            "    fun describe(): str >> this.draw();\n"
            "}\n"
            "type Screen[+] {\n"
            "    fun Drawable.draw(): str >> \"screen\";\n"
            "}\n"
            "screen := Screen.[];\n"
            "print(screen.describe()); print(\" \");\n"
            "print(Drawable.describe(screen)); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "screen screen\n")

    def test_generic_trait_constraint(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "type Screen[+] { fun this.draw(): str >> \"screen\"; }\n"
            "fun render[T: Drawable](value: T): str >> value.draw();\n"
            "print(render(Screen.[])); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "screen\n")

    def test_multiple_compatible_constraints(self) -> None:
        result = run_source(
            "trait A { fun draw(): str; }\n"
            "trait B { fun draw(): str; }\n"
            "type Screen[+] { fun this.draw(): str >> \"screen\"; }\n"
            "fun render[T: A & B](value: T): str >> value.draw();\n"
            "print(render(Screen.[])); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "screen\n")

    def test_multiple_conflicting_constraints_with_qualified_methods(self) -> None:
        result = run_source(
            "trait A { fun draw(): str; }\n"
            "trait B { fun draw(): int; }\n"
            "type Screen[+] {\n"
            "    fun A.draw(): str >> \"a\";\n"
            "    fun B.draw(): int >> 1;\n"
            "}\n"
            "fun render[T: A & B](value: T): str >> \"ok\";\n"
            "print(render(Screen.[])); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "ok\n")

    def test_lambda_trait_constraint(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "type Screen[+] { fun this.draw(): str >> \"screen\"; }\n"
            "render := fun[T: Drawable](value: T): str >> value.draw();\n"
            "print(render(Screen.[])); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "screen\n")

    def test_trait_to_trait_assignment(self) -> None:
        result = run_source(
            "trait A { fun draw(): str; }\n"
            "trait B { fun draw(): str; fun label(): str; }\n"
            "fun to_a(value: B): A >> value;\n"
            "type Screen[+] {\n"
            "    | name: str;\n"
            "    fun this.draw(): str >> \"screen\";\n"
            "    fun this.label(): str >> this.name;\n"
            "}\n"
            "screen := Screen.[\"main\"];\n"
            "a: A = to_a(screen);\n"
            "print(a.draw()); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "screen\n")

    def test_trait_annotation_copies_the_object(self) -> None:
        result = run_source(
            "trait Readable { | value: int; }\n"
            "type Cell[+] { | value: int; }\n"
            "cell := Cell.[1];\n"
            "value: Readable = cell;\n"
            "cell.value = 99;\n"
            "print(value.value); print(\"\\n\");\n"
        )
        self.assertEqual(result.stdout, "1\n")


class TraitDiagnosticTests(unittest.TestCase):
    def test_missing_method(self) -> None:
        result = run_source(
            "trait Drawable { | name: str; fun draw(): str; }\n"
            "type Screen[+] { | name: str; }\n"
            "x: Drawable = Screen.[\"main\"];\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("type Screen cannot satisfy Drawable", result.combined)
        self.assertIn("missing method draw", result.combined)

    def test_missing_property(self) -> None:
        result = run_source(
            "trait Drawable { | name: str; fun draw(): str; }\n"
            "type Screen[+] { fun this.draw(): str >> \"screen\"; }\n"
            "x: Drawable = Screen.[];\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing property name", result.combined)

    def test_property_type_mismatch(self) -> None:
        result = run_source(
            "trait Drawable { | name: str; }\n"
            "type Screen[+] { | name: int; }\n"
            "x: Drawable = Screen.[1];\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("property name has type int", result.combined)
        self.assertIn("requires str", result.combined)

    def test_method_signature_mismatch(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(width: int): str; }\n"
            "type Screen[+] { fun this.draw(width: str): str >> \"x\"; }\n"
            "x: Drawable = Screen.[];\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("method draw has an incompatible signature", result.combined)

    def test_default_body_uses_undeclared_member(self) -> None:
        result = run_source(
            "trait Bad {\n"
            "    fun draw(): str;\n"
            "    fun describe(): str {\n"
            "        return this.color;\n"
            "    }\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("trait method describe uses member color", result.combined)
        self.assertIn("not declared in the trait", result.combined)

    def test_unknown_trait_constraint(self) -> None:
        result = run_source(
            "fun render[T: Missing](value: T): str >> \"x\";\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown trait 'Missing'", result.combined)

    def test_constraint_satisfaction_failure(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "type Screen[+] { | name: str; }\n"
            "fun render[T: Drawable](value: T): str >> value.draw();\n"
            "screen := Screen.[\"main\"];\n"
            "print(render(screen));\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("type Screen cannot satisfy Drawable", result.combined)

    def test_generic_constraint_conflict(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "trait Named { fun draw(): int; }\n"
            "fun render[T: Drawable & Named](value: T): str {\n"
            "    return value.draw();\n"
            "}\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "generic parameter T is constrained by Drawable and Named",
            result.combined,
        )
        self.assertIn("incompatible signatures for draw", result.combined)

    def test_concrete_trait_conflict(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "trait Named { fun draw(): int; }\n"
            "type Screen[+] {\n"
            "    | name: str;\n"
            "    fun this.draw(): str >> \"screen\";\n"
            "}\n"
            "fun render[T: Drawable & Named](value: T): str >> \"ok\";\n"
            "screen := Screen.[\"main\"];\n"
            "print(render(screen));\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "type Screen cannot satisfy Drawable and Named",
            result.combined,
        )
        self.assertIn("Add fun Drawable.draw and fun Named.draw", result.combined)

    def test_ambiguous_direct_call(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "trait Named { fun draw(): int; }\n"
            "type Screen[+] {\n"
            "    | name: str;\n"
            "    fun Drawable.draw(): str >> \"screen\";\n"
            "    fun Named.draw(): int >> 1;\n"
            "}\n"
            "screen := Screen.[\"main\"];\n"
            "print(screen.draw());\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("call to draw is ambiguous", result.combined)

    def test_trait_qualified_definition_mismatch(self) -> None:
        result = run_source(
            "trait Named { fun draw(): str; }\n"
            "type Screen[+] { fun Named.draw(): int >> 1; }\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match the signature required by Named.draw()", result.combined)

    def test_qualified_call_receiver_failure(self) -> None:
        result = run_source(
            "trait Drawable { fun draw(): str; }\n"
            "type Screen[+] { | name: str; }\n"
            "screen := Screen.[\"main\"];\n"
            "print(Drawable.draw(screen));\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("type Screen cannot satisfy Drawable", result.combined)

    def test_unknown_qualified_trait(self) -> None:
        result = run_source(
            "type Screen[+] { fun Missing.draw(): str >> \"x\"; }\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown trait 'Missing'", result.combined)

    def test_unknown_qualified_method(self) -> None:
        result = run_source(
            "trait A { fun draw(): str; }\n"
            "type Screen[+] { fun A.color(): str >> \"x\"; }\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("trait 'A' has no method named 'color'", result.combined)

    def test_trait_qualified_method_outside_type_body(self) -> None:
        result = run_source(
            "trait Named { fun draw(): str; }\n"
            "fun Named.draw(): str >> \"x\";\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "trait-qualified methods must be declared inside a type body",
            result.combined,
        )

    def test_duplicate_trait_member(self) -> None:
        result = run_source(
            "trait A { fun draw(): str; fun draw(): str; }\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("trying to redefine: draw", result.combined)


if __name__ == "__main__":
    unittest.main()
