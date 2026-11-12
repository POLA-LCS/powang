"""Native parity across the full example corpus."""

from __future__ import annotations

import unittest

from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.differential import run
from tests.helpers import ROOT


class NativeExamplesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_examples_match_python(self) -> None:
        code = run([], [ROOT / "examples"], fail_fast=True)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
