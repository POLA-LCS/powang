"""PWBB bundle builder, parser and integrated build tests for N4.1a."""

from __future__ import annotations

import dataclasses
import hashlib
import struct
import unittest

from src.state import set_state
from src.vm.compiler import compile_source
from src.vm.native.bundle import (
    build_bundle,
    build_bundle_from_image,
    parse_bundle,
)
from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from src.vm.native.loader import run_native
from src.vm.native.meta import build_meta
from src.vm.native.session import (
    compile_native_file,
    prepare_state,
)
from src.vm.native.source_gen import (
    render_bundle_cpp,
    render_temp_cpp,
)
from tests.helpers import ROOT


SOURCE = "print(1 + 2);\n"


class NativeBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def _image(self, source: str = SOURCE):
        return compile_source(
            source,
            path="program.po",
            module_name="program",
            check=False,
        )

    def test_bundle_magic_and_version(self) -> None:
        data = build_bundle(self._image())
        self.assertEqual(data[:4], b"PWBB")
        self.assertEqual(struct.unpack_from("<H", data, 4)[0], 1)

    def test_bundle_entry_only_round_trip(self) -> None:
        image = self._image()
        bundle = parse_bundle(build_bundle(image))
        self.assertEqual(bundle.entry_module, 0)
        self.assertEqual(len(bundle.modules), 1)
        module = bundle.modules[0]
        self.assertEqual(module.module_id, 0)
        self.assertEqual(module.name, "program")
        self.assertEqual(module.image, image.to_bytes())
        self.assertEqual(module.meta, build_meta(image))
        self.assertEqual(module.status, 0)
        self.assertEqual(module.imports, ())
        self.assertEqual(module.exports, ())

    def test_bundle_digest(self) -> None:
        data = build_bundle(self._image())
        self.assertEqual(
            data[-32:], hashlib.sha256(data[:-32]).digest()
        )
        self.assertEqual(parse_bundle(data).digest, data[-32:])

    def test_bundle_deterministic(self) -> None:
        image = self._image()
        self.assertEqual(build_bundle(image), build_bundle(image))

    def test_bundle_rejects_bad_magic(self) -> None:
        data = bytearray(build_bundle(self._image()))
        data[0:4] = b"XWBB"
        data[-32:] = hashlib.sha256(bytes(data[:-32])).digest()
        with self.assertRaises(ValueError):
            parse_bundle(bytes(data))

    def test_bundle_rejects_bad_digest(self) -> None:
        data = bytearray(build_bundle(self._image()))
        data[-1] ^= 0xFF
        with self.assertRaises(ValueError):
            parse_bundle(bytes(data))

    def test_bundle_rejects_bad_module_id(self) -> None:
        image = self._image()
        bundle = build_bundle_from_image(image)
        module = dataclasses.replace(bundle.modules[0], module_id=1)
        broken = dataclasses.replace(bundle, modules=(module,))
        with self.assertRaises(ValueError):
            parse_bundle(broken.to_bytes())

    def test_bundle_rejects_truncated_image(self) -> None:
        image = self._image()
        bundle = build_bundle_from_image(image)
        module = dataclasses.replace(bundle.modules[0], image=b"\x00")
        broken = dataclasses.replace(bundle, modules=(module,))
        with self.assertRaises(ValueError):
            parse_bundle(broken.to_bytes())

    def test_bundle_rejects_bad_meta_hash(self) -> None:
        image = self._image()
        bundle = build_bundle_from_image(image)
        meta = bytearray(bundle.modules[0].meta)
        # PWBM header is 16 bytes before the 32 byte image hash.
        meta[16] ^= 0xFF
        module = dataclasses.replace(bundle.modules[0], meta=bytes(meta))
        broken = dataclasses.replace(bundle, modules=(module,))
        with self.assertRaises(ValueError):
            parse_bundle(broken.to_bytes())

    def test_generated_source_contains_bundle(self) -> None:
        image = self._image()
        data = build_bundle(image)
        generated = render_temp_cpp(image)
        self.assertIn("kPwbBundle", generated)
        self.assertIn("run_embedded_bundle_with_meta", generated)
        direct = render_bundle_cpp(data)
        self.assertIn("kPwbBundle", direct)
        self.assertIn("run_embedded_bundle_with_meta", direct)

    def test_native_bundle_runs_entry(self) -> None:
        result = run_native(self._image())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "3")
        self.assertEqual(result.stderr, "")

    def test_bundle_module_graph(self) -> None:
        path = ROOT / "tests" / "native" / "corpus" / "n4" / "modules.po"
        state = prepare_state(path)
        set_state(state)
        try:
            image = compile_source(
                path.read_text(encoding="utf-8"),
                path=str(path),
                module_name="modules",
                check=False,
                state=state,
            )
            bundle = build_bundle_from_image(image, state)
            again = build_bundle_from_image(image, state)
        finally:
            state.close()
        self.assertEqual(bundle.entry_module, 0)
        names = {module.name: module for module in bundle.modules}
        self.assertIn("mathlib", names)
        self.assertIn("legacy", names)
        mathlib = names["mathlib"]
        self.assertEqual(mathlib.status, 0)
        self.assertEqual(
            mathlib.exports,
            (
                ("version", "variable"),
                ("add", "function"),
                ("scaled", "function"),
            ),
        )
        entry = bundle.modules[0]
        targets = {item.target_module_id for item in entry.imports}
        self.assertIn(mathlib.module_id, targets)
        self.assertIn(names["legacy"].module_id, targets)
        self.assertEqual(bundle.to_bytes(), again.to_bytes())
        parsed = parse_bundle(bundle.to_bytes())
        self.assertEqual(parsed.modules[0].imports, entry.imports)
        self.assertEqual(parsed.modules[1].exports, mathlib.exports)

    def test_bundle_project_block(self) -> None:
        path = (
            ROOT / "tests" / "native" / "corpus" / "n4"
            / "project" / "main.po"
        )
        session = compile_native_file(path)
        bundle = parse_bundle(session.bundle)
        self.assertIsNotNone(bundle.project)
        assert bundle.project is not None
        self.assertEqual(bundle.project.log_level, "warning")
        self.assertEqual(bundle.project.paths, (".",))
        self.assertTrue(bundle.modules[0].bind_project)
        self.assertTrue(bundle.modules[1].bind_project)

    def test_sha256_vectors(self) -> None:
        self.assertEqual(
            hashlib.sha256(b"").hexdigest(),
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
        )
        self.assertEqual(
            hashlib.sha256(b"abc").hexdigest(),
            "ba7816bf8f01cfea414140de5dae2223"
            "b00361a396177a9cb410ff61f20015ad",
        )


if __name__ == "__main__":
    unittest.main()
