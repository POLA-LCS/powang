"""Differential tests for the native execution corpora."""

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

    def _run_corpus(self, corpus: Path) -> None:
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
                python_stderr = "".join(
                    line + "\n" for line in python.stderr.splitlines()
                    if not line.startswith("[WARNING]")
                )
                self.assertEqual(native.stderr, python_stderr, path.name)

    def test_n1_corpus_matches(self) -> None:
        self._run_corpus(ROOT / "tests" / "native" / "corpus" / "n1")

    def test_n2_corpus_matches(self) -> None:
        self._run_corpus(ROOT / "tests" / "native" / "corpus" / "n2")

    def test_n3_corpus_matches(self) -> None:
        self._run_corpus(ROOT / "tests" / "native" / "corpus" / "n3")


if __name__ == "__main__":
    unittest.main()
