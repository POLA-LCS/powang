"""Private members are visible only to methods of the owning type."""

from __future__ import annotations

import unittest

from helpers import run_source


class AccessControlTests(unittest.TestCase):
    def test_same_type_private_access_allowed(self) -> None:
        result = run_source(
            "type Box[+] {\n"
            "    - secret: int = 7;\n"
            "    fun this.reveal(): int { return this.secret; }\n"
            "}\n"
            "b := Box.[];\n"
            'print(b.reveal()); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "7\n")

    def test_other_type_private_access_rejected(self) -> None:
        result = run_source(
            "type A[+] {\n"
            "    fun this.peek(other: B): int { return other.secret; }\n"
            "}\n"
            "type B[+] {\n"
            "    - secret: int = 9;\n"
            "}\n"
            "a := A.[];\n"
            "b := B.[];\n"
            'print(a.peek(b)); print("\\n");\n'
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("private property", result.combined)

    def test_static_private_from_same_type_allowed(self) -> None:
        result = run_source(
            "type A[+] {\n"
            "    - fun secret(): int { return 7; }\n"
            "    fun reveal(): int { return A.secret(); }\n"
            "}\n"
            'print(A.reveal()); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "7\n")

    def test_static_private_denied_outside(self) -> None:
        result = run_source(
            "type A[+] {\n"
            "    - fun secret(): int { return 7; }\n"
            "}\n"
            'print(A.secret()); print("\\n");\n'
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("private static method", result.combined)

    def test_failed_method_does_not_leave_private_access_enabled(self) -> None:
        result = run_source(
            "type A[+] {\n"
            "    - secret: int = 7;\n"
            '    fun this.fail(): int { error("boom"); }\n'
            "}\n"
            "a := A.[];\n"
            "try { a.fail(); } catch problem { }\n"
            'print(a.secret); print("\\n");\n'
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("7", result.stdout)
        self.assertIn("private property", result.combined)


if __name__ == "__main__":
    unittest.main()
