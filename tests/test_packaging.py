"""Packaging metadata must cover every standard library module."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def _package_data(self) -> dict[str, list[str]]:
        with open(ROOT / "pyproject.toml", "rb") as handle:
            config = tomllib.load(handle)
        return config["tool"]["setuptools"]["package-data"]

    def test_every_module_directory_has_package_data(self) -> None:
        package_data = self._package_data()
        module_dirs = sorted(
            path.name for path in (ROOT / "modules").iterdir() if path.is_dir()
        )
        for name in module_dirs:
            with self.subTest(module=name):
                self.assertIn(f"modules.{name}", package_data)

    def test_every_po_file_is_covered(self) -> None:
        package_data = self._package_data()
        for module_dir in sorted((ROOT / "modules").iterdir()):
            if not module_dir.is_dir():
                continue
            patterns = package_data.get(f"modules.{module_dir.name}", [])
            for po_file in module_dir.glob("*.po"):
                with self.subTest(file=str(po_file.relative_to(ROOT))):
                    self.assertTrue(
                        any(po_file.match(pattern) for pattern in patterns),
                        f"{po_file} is not matched by {patterns}",
                    )

    def test_host_module_is_present(self) -> None:
        self.assertTrue((ROOT / "modules" / "host" / "use.po").is_file())


if __name__ == "__main__":
    unittest.main()
