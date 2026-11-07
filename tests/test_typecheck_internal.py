"""Internal checker behavior that must not silently hide programming errors."""

from __future__ import annotations

import unittest

from src.error import PowangError
from src.typecheck import ANY, _TypeChecker


class CheckerInternalTests(unittest.TestCase):
    def test_unexpected_name_error_propagates(self):
        checker = _TypeChecker()

        def boom(_node):
            raise NameError("type_name")

        checker._infer_inner = boom
        with self.assertRaises(NameError):
            checker._infer({"type": "test"})

    def test_malformed_shape_returns_any(self):
        checker = _TypeChecker()

        def boom(_node):
            raise KeyError("missing")

        checker._infer_inner = boom
        self.assertEqual(checker._infer({"type": "test"}), ANY)

    def test_powang_error_is_collected(self):
        checker = _TypeChecker()
        error = PowangError("TYPE", "boom")

        def boom(_node):
            raise error

        checker._infer_inner = boom
        self.assertEqual(checker._infer({"type": "test"}), ANY)
        self.assertEqual(checker.errors, [error])


if __name__ == "__main__":
    unittest.main()
