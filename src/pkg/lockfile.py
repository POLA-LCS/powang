"""The ``powang.lock`` dependency lock file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..error import powang_error_format, powang_throw
from .manifest import Manifest
from .semver import Version

LOCK_NAME = 'powang.lock'
LOCK_FORMAT = 1


@dataclass
class LockedPackage:
    name: str
    version: Version
    source: dict[str, Any]
    dependencies: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return str(self.source.get('kind', ''))

    @property
    def registry(self) -> str | None:
        value = self.source.get('registry')
        return value if isinstance(value, str) else None

    @property
    def archive(self) -> str | None:
        value = self.source.get('archive')
        return value if isinstance(value, str) else None

    @property
    def sha256(self) -> str | None:
        value = self.source.get('sha256')
        return value if isinstance(value, str) else None

    @property
    def path(self) -> str | None:
        value = self.source.get('path')
        return value if isinstance(value, str) else None


@dataclass
class LockFile:
    manifest_hash: str
    packages: dict[str, LockedPackage] = field(default_factory=dict)
    format: int = LOCK_FORMAT

    def is_current(self, manifest: Manifest) -> bool:
        return self.manifest_hash == manifest.dependencies_hash()

    def to_dict(self) -> dict[str, Any]:
        return {
            'format': self.format,
            'manifestHash': self.manifest_hash,
            'packages': {
                name: {
                    'version': str(package.version),
                    'source': package.source,
                    'dependencies': package.dependencies,
                }
                for name, package in sorted(self.packages.items())
            },
        }


def lock_path(root: Path | str) -> Path:
    return Path(root) / LOCK_NAME


def load_lock(root: Path | str, *, required: bool = False) -> LockFile | None:
    path = lock_path(root)
    if not path.exists():
        if required:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'lock',
                f"missing {LOCK_NAME}",
                [
                    f"looked in {path}",
                    'run powang pkg install to resolve dependencies',
                ],
            ))
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as error:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'lock',
            f"invalid {LOCK_NAME}",
            [str(error)],
        )) from None
    except OSError as error:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'lock',
            f"cannot read {LOCK_NAME}",
            [str(error)],
        )) from None
    if not isinstance(data, dict):
        raise powang_throw(powang_error_format(
            'PACKAGE', 'lock', f"{LOCK_NAME} must contain an object",
        ))
    format_version = data.get('format')
    if format_version != LOCK_FORMAT:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'lock',
            f"unsupported lock format '{format_version}'",
            [f"this powang build expects format {LOCK_FORMAT}"],
        ))
    manifest_hash = data.get('manifestHash')
    if not isinstance(manifest_hash, str):
        raise powang_throw(powang_error_format(
            'PACKAGE', 'lock', 'lock file has no manifest hash',
        ))
    raw_packages = data.get('packages')
    if not isinstance(raw_packages, dict):
        raise powang_throw(powang_error_format(
            'PACKAGE', 'lock', 'lock file has no packages table',
        ))
    packages: dict[str, LockedPackage] = {}
    for name, raw_package in raw_packages.items():
        if not isinstance(name, str) or not isinstance(raw_package, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'lock', 'invalid package entry in lock file',
            ))
        version_text = raw_package.get('version')
        if not isinstance(version_text, str):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'lock', f"package '{name}' has no version",
            ))
        source = raw_package.get('source')
        if not isinstance(source, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'lock', f"package '{name}' has no source",
            ))
        kind = source.get('kind')
        if kind == 'registry':
            if not isinstance(source.get('registry'), str) or \
                    not isinstance(source.get('archive'), str) or \
                    not isinstance(source.get('sha256'), str):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'lock',
                    f"registry package '{name}' has an incomplete source",
                ))
        elif kind == 'path':
            if not isinstance(source.get('path'), str):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'lock',
                    f"path package '{name}' has no path",
                ))
        else:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'lock',
                f"package '{name}' has unknown source kind '{kind}'",
            ))
        dependencies = raw_package.get('dependencies')
        if dependencies is None:
            dependencies = {}
        if not isinstance(dependencies, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'lock', f"package '{name}' has invalid dependencies",
            ))
        packages[name] = LockedPackage(
            name=name,
            version=Version.parse(version_text),
            source=dict(source),
            dependencies=dict(dependencies),
        )
    return LockFile(
        manifest_hash=manifest_hash,
        packages=packages,
        format=LOCK_FORMAT,
    )


def write_lock(root: Path | str, lock: LockFile) -> Path:
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        lock.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
    ) + '\n'
    path.write_text(content, encoding='utf-8', newline='\n')
    return path
