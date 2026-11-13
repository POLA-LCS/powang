"""Native parity for runtime access control and operator ambiguity."""

from __future__ import annotations

import unittest

from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from tests.helpers import run_source


CASES = {
    "same type private access": (
        "type Box[+] {\n"
        "    - secret: int = 7;\n"
        "    fun this.reveal(): int { return this.secret; }\n"
        "}\n"
        "b := Box.[];\n"
        'print(b.reveal()); print("\\n");\n'
    ),
    "other type private access": (
        "type A[+] {\n"
        "    fun this.peek(other: B): int { return other.secret; }\n"
        "}\n"
        "type B[+] {\n"
        "    - secret: int = 9;\n"
        "}\n"
        "a := A.[];\n"
        "b := B.[];\n"
        'print(a.peek(b)); print("\\n");\n'
    ),
    "same type private static": (
        "type A[+] {\n"
        "    - fun secret(): int { return 7; }\n"
        "    fun reveal(): int { return A.secret(); }\n"
        "}\n"
        'print(A.reveal()); print("\\n");\n'
    ),
    "outside private static": (
        "type A[+] {\n"
        "    - fun secret(): int { return 7; }\n"
        "}\n"
        'print(A.secret()); print("\\n");\n'
    ),
    "failed method leaves no access": (
        "type A[+] {\n"
        "    - secret: int = 7;\n"
        '    fun this.fail(): int { error("boom"); }\n'
        "}\n"
        "a := A.[];\n"
        "try { a.fail(); } catch problem { }\n"
        'print(a.secret); print("\\n");\n'
    ),
    "ambiguous operator trait": (
        "trait Arithmetic {\n"
        "    fun add(other: any): any;\n"
        "}\n"
        "type Point[+] {\n"
        "    | x: int;\n"
        "    fun Add.add(other: Point): Point "
        ">> Point.[this.x + other.x];\n"
        "    fun Arithmetic.add(other: Point): Point "
        ">> Point.[this.x - other.x];\n"
        "}\n"
        "fun dynamic(value: any, other: Point): any >> value + other;\n"
        "point := Point.[2];\n"
        "print(dynamic(point, point).x);\n"
    ),
    "locked array set": (
        "values: arr[int!] = [1, 2];\n"
        "values &> arr.set(0, 5);\n"
        'print(values[0]); print("\\n");\n'
    ),
    "locked array push allowed": (
        "values: arr[int!] = [1, 2];\n"
        "values &> arr.push(3);\n"
        'print(size(values)); print("\\n");\n'
    ),
    "constant array push": (
        "values: arr[int]! = [1, 2];\n"
        "values &> arr.push(3);\n"
        'print(size(values)); print("\\n");\n'
    ),
    "constant array reference": (
        "values: arr[int]! = [1, 2];\n"
        "arr.push(values, 3);\n"
        'print(size(values)); print("\\n");\n'
    ),
    "constant map merge": (
        "values: map[str, int]! = [\"a\" >> 1];\n"
        'map.merge(values, ["b" >> 2]);\n'
        'print(size(values)); print("\\n");\n'
    ),
    "constant set add": (
        "values: set[int]! = [/1];\n"
        "set.add(values, 2);\n"
        'print(size(values)); print("\\n");\n'
    ),
}


class NativeAccessControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_access_control_matches(self) -> None:
        for name, source in CASES.items():
            with self.subTest(case=name):
                python = run_source(source, engine="vm")
                native = run_source(source, engine="native")
                self.assertEqual(
                    (native.returncode, native.stdout, native.stderr),
                    (python.returncode, python.stdout, python.stderr),
                    name,
                )

    def test_trait_method_ambiguity_matches(self) -> None:
        source = (
            "trait Drawable { fun draw(): str; }\n"
            "trait Named { fun draw(): int; }\n"
            "type Screen[+] {\n"
            "    | name: str;\n"
            '    fun Drawable.draw(): str >> "screen";\n'
            "    fun Named.draw(): int >> 1;\n"
            "}\n"
            'screen := Screen.["main"];\n'
            "print(screen.draw());\n"
        )
        arguments = ("--no-check",)
        python = run_source(source, engine="vm", args=arguments)
        native = run_source(source, engine="native", args=arguments)
        self.assertEqual(
            (native.returncode, native.stdout, native.stderr),
            (python.returncode, python.stdout, python.stderr),
        )


if __name__ == "__main__":
    unittest.main()
