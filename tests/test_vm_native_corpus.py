"""Differential tests for the N1 native execution corpus."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.vm.compiler import compile_source
from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.loader import run_native
from tests.helpers import ROOT, run_source


class NativeCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_n1_corpus_matches(self) -> None:
        corpus = ROOT / "tests" / "native" / "corpus" / "n1"
        programs = sorted(corpus.glob("*.po"))
        self.assertTrue(programs)
        for path in programs:
            with self.subTest(program=path.name):
                source = path.read_text(encoding="utf-8")
                image = compile_source(
                    source,
                    path=str(path),
                    module_name=path.stem,
                    check=False,
                )
                native = run_native(image)
                python = run_source(source, engine="vm")
                self.assertEqual(
                    native.returncode, python.returncode, path.name,
                )
                self.assertEqual(native.stdout, python.stdout, path.name)
                self.assertEqual(native.stderr, python.stderr, path.name)


if __name__ == "__main__":
    unittest.main()
