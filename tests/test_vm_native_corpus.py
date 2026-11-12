"""Differential tests for the native execution corpora."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.error import PowangError
from src.vm.compiler import compile_source
from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.loader import run_native
from src.vm.native.session import run_native_file
from tests.helpers import ROOT, run_file, run_source


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

    def _run_file_corpus(self, corpus: Path) -> None:
        programs = sorted(corpus.glob("*.po"))
        self.assertTrue(programs)
        for path in programs:
            with self.subTest(program=path.name):
                python = run_file(path, engine="vm")
                try:
                    native = run_native_file(path)
                    native_stdout = native.stdout
                    native_stderr = native.stderr
                    native_code = native.returncode
                except PowangError as error:
                    ## The native file path surfaces an entry compile or
                    ## check error before a runnable bundle exists.
                    native_stdout = str(error) + "\n"
                    native_stderr = ""
                    native_code = 1
                self.assertEqual(
                    native_code, python.returncode, path.name,
                )
                self.assertEqual(
                    native_stdout, python.stdout, path.name,
                )
                self.assertEqual(
                    native_stderr, python.stderr, path.name,
                )

    def test_n4_corpus_matches(self) -> None:
        corpus = ROOT / "tests" / "native" / "corpus" / "n4"
        self._run_file_corpus(corpus)
        project = corpus / "project" / "main.po"
        with self.subTest(program="project/main.po"):
            python = run_file(project, engine="vm")
            native = run_native_file(project)
            self.assertEqual(native.returncode, python.returncode)
            self.assertEqual(native.stdout, python.stdout)
            self.assertEqual(native.stderr, python.stderr)

    def test_n5_corpus_matches(self) -> None:
        self._run_file_corpus(
            ROOT / "tests" / "native" / "corpus" / "n5")


if __name__ == "__main__":
    unittest.main()
