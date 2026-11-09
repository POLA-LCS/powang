"""Package manifests stored in ``powang.toml``."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..error import powang_error_format, powang_throw
from .semver import Constraint, Version

MANIFEST_NAME = 'powang.toml'
PACKAGE_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')


class InlineTable(dict):
    """A TOML value that must be written as an inline table."""


def validate_package_name(name: str, where: str = 'package') -> str:
    if not isinstance(name, str) or PACKAGE_NAME_RE.match(name) is None:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            where,
            f"invalid package name '{name}'",
            [
                'package names use lowercase letters, digits and underscores',
                'the first character must be a letter',
            ],
        ))
    return name


@dataclass
class DependencySpec:
    name: str
    constraint: Constraint | None = None
    path: str | None = None
    registry: str | None = None

    @property
    def is_path(self) -> bool:
        return self.path is not None

    @property
    def kind(self) -> str:
        return 'path' if self.is_path else 'registry'

    @classmethod
    def from_value(cls, name: str, value: Any) -> 'DependencySpec':
        validate_package_name(name, 'dependency')
        if isinstance(value, str):
            return cls(name=name, constraint=Constraint.parse(value))
        if not isinstance(value, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'dependency',
                f"invalid dependency '{name}'",
                ['use a version string or a table with path or version'],
            ))
        path = value.get('path')
        version = value.get('version')
        registry = value.get('registry')
        git = value.get('git')
        if git is not None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'dependency',
                f"git dependency '{name}' is not supported",
                ['use a path dependency or publish the package to a registry'],
            ))
        unknown = set(value) - {'path', 'version', 'registry'}
        if unknown:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'dependency',
                f"dependency '{name}' has unknown fields",
                [f"unknown fields: {', '.join(sorted(unknown))}"],
            ))
        if path is not None and version is not None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'dependency',
                f"dependency '{name}' cannot use both path and version",
                ['choose a path dependency or a registry dependency'],
            ))
        if path is not None:
            if not isinstance(path, str) or not path.strip():
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'dependency',
                    f"dependency '{name}' has an invalid path",
                ))
            if registry is not None:
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'dependency',
                    f"path dependency '{name}' cannot set a registry",
                    ['remove the registry field from the path dependency'],
                ))
            return cls(name=name, path=path)
        if version is not None:
            if not isinstance(version, str):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'dependency',
                    f"dependency '{name}' has an invalid version constraint",
                    ['write the constraint as a string'],
                ))
            return cls(
                name=name,
                constraint=Constraint.parse(version),
                registry=registry if isinstance(registry, str) else None,
            )
        return cls(name=name, constraint=Constraint.any())

    def to_value(self) -> Any:
        if self.is_path:
            return {'path': self.path}
        constraint = str(self.constraint) if self.constraint is not None else '*'
        if self.registry:
            return {'version': constraint, 'registry': self.registry}
        return constraint

    def to_lock_value(self) -> Any:
        return self.to_value()

    def __str__(self) -> str:
        if self.is_path:
            return f'{self.name} at {self.path}'
        return f'{self.name} {self.constraint or "*"}'


@dataclass
class Manifest:
    root: Path
    path: Path
    raw: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    version: Version | None = None
    description: str | None = None
    dependencies: dict[str, DependencySpec] = field(default_factory=dict)
    registry_url: str | None = None

    def dependencies_hash(self) -> str:
        payload = {
            'registry': self.registry_url,
            'dependencies': {
                name: spec.to_lock_value()
                for name, spec in sorted(self.dependencies.items())
            },
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False
        ).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def to_toml(self) -> str:
        data = dict(self.raw)
        package = dict(data.get('package') or {})
        if self.name is not None:
            package['name'] = self.name
        if self.version is not None:
            package['version'] = str(self.version)
        if self.description is not None:
            package['description'] = self.description
        if package:
            data['package'] = package
        if self.dependencies:
            dependencies: dict[str, Any] = {}
            for name, spec in sorted(self.dependencies.items()):
                value = spec.to_value()
                dependencies[name] = (
                    InlineTable(value) if isinstance(value, dict) else value
                )
            data['dependencies'] = dependencies
        else:
            data.pop('dependencies', None)
        if self.registry_url:
            registry = dict(data.get('registry') or {})
            registry['url'] = self.registry_url
            data['registry'] = registry
        else:
            registry = data.get('registry')
            if isinstance(registry, dict):
                registry.pop('url', None)
                if not registry:
                    data.pop('registry', None)
        return dump_toml(data)


def manifest_path(root: Path | str) -> Path:
    path = Path(root)
    if path.name == MANIFEST_NAME:
        return path
    return path / MANIFEST_NAME


def load_manifest(
    root: Path | str,
    *,
    required: bool = True,
) -> Manifest | None:
    path = manifest_path(root)
    if not path.exists():
        if required:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'manifest',
                f"missing {MANIFEST_NAME}",
                [
                    f"looked in {path}",
                    'run powang pkg init to create one',
                ],
            ))
        return None
    try:
        with path.open('rb') as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'manifest',
            f"invalid {MANIFEST_NAME}",
            [str(error)],
        )) from None
    except OSError as error:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'manifest',
            f"cannot read {MANIFEST_NAME}",
            [str(error)],
        )) from None
    if not isinstance(data, dict):
        raise powang_throw(powang_error_format(
            'PACKAGE', 'manifest', f"{MANIFEST_NAME} must contain a table",
        ))
    return _manifest_from_data(path.parent, path, data)


def _manifest_from_data(root: Path, path: Path, data: dict[str, Any]) -> Manifest:
    package = data.get('package')
    name = None
    version = None
    description = None
    if package is not None:
        if not isinstance(package, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'manifest', '[package] must be a table',
            ))
        raw_name = package.get('name')
        if raw_name is not None:
            name = validate_package_name(raw_name)
        raw_version = package.get('version')
        if raw_version is not None:
            version = Version.parse(raw_version)
        raw_description = package.get('description')
        if raw_description is not None:
            if not isinstance(raw_description, str):
                raise powang_throw(powang_error_format(
                    'PACKAGE', 'manifest', 'package description must be a string',
                ))
            description = raw_description

    dependencies: dict[str, DependencySpec] = {}
    raw_dependencies = data.get('dependencies')
    if raw_dependencies is not None:
        if not isinstance(raw_dependencies, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'manifest', '[dependencies] must be a table',
            ))
        for dependency_name, dependency_value in raw_dependencies.items():
            dependencies[dependency_name] = DependencySpec.from_value(
                dependency_name, dependency_value
            )

    registry_url = None
    registry = data.get('registry')
    if registry is not None:
        if not isinstance(registry, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'manifest', '[registry] must be a table',
            ))
        raw_url = registry.get('url')
        if raw_url is not None:
            if not isinstance(raw_url, str) or not raw_url.strip():
                raise powang_throw(powang_error_format(
                    'PACKAGE', 'manifest', 'registry url must be a non-empty string',
                ))
            registry_url = raw_url.strip()

    return Manifest(
        root=root,
        path=path,
        raw=data,
        name=name,
        version=version,
        description=description,
        dependencies=dependencies,
        registry_url=registry_url,
    )


def write_manifest(manifest: Manifest) -> None:
    manifest.path.parent.mkdir(parents=True, exist_ok=True)
    content = manifest.to_toml()
    manifest.path.write_text(content, encoding='utf-8', newline='\n')


def find_project_root(start: Path | str | None = None) -> Path | None:
    if start is None:
        current = Path.cwd().resolve()
    else:
        current = Path(start).resolve()
        if current.is_file() or current.suffix == '.po':
            current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    return None


def default_package_name(root: Path | str) -> str:
    raw = Path(root).resolve().name.lower()
    cleaned = re.sub(r'[^a-z0-9_]+', '_', raw).strip('_')
    if not cleaned or not cleaned[0].isalpha():
        cleaned = 'powang_package'
    return cleaned


def _toml_key(key: str) -> str:
    if re.match(r'^[A-Za-z0-9_-]+$', key):
        return key
    return json.dumps(key, ensure_ascii=False)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return '[' + ', '.join(_toml_value(item) for item in value) + ']'
    if isinstance(value, dict):
        pairs = ', '.join(
            f'{_toml_key(key)} = {_toml_value(item)}'
            for key, item in value.items()
        )
        return '{ ' + pairs + ' }'
    if value is None:
        return '""'
    return json.dumps(str(value), ensure_ascii=False)


def dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = ['# Managed by powang pkg.', '']
    _write_table(lines, data, [])
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines) + '\n'


def _write_table(lines: list[str], table: dict[str, Any], path: list[str]) -> None:
    scalars = {
        key: value for key, value in table.items()
        if not isinstance(value, dict) or not value or isinstance(value, InlineTable)
    }
    nested = {
        key: value for key, value in table.items()
        if isinstance(value, dict) and value and not isinstance(value, InlineTable)
    }
    if path and scalars:
        lines.append('[' + '.'.join(_toml_key(part) for part in path) + ']')
    for key, value in scalars.items():
        if key in nested:
            continue
        lines.append(f'{_toml_key(key)} = {_toml_value(value)}')
    if path and scalars:
        lines.append('')
    for key, value in nested.items():
        _write_table(lines, value, [*path, key])
