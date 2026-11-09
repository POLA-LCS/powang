"""Dependency resolution with backtracking and a single version per package."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..error import powang_error_format, powang_throw
from .lockfile import LockedPackage, LockFile
from .manifest import DependencySpec, Manifest, load_manifest
from .registry import RegistryClient, VersionEntry, configured_registry_url
from .semver import Constraint, Version


@dataclass(frozen=True)
class SourceSpec:
    kind: str
    constraint: Constraint | None = None
    path: Path | None = None
    registry: str | None = None

    def compatible(self, other: 'SourceSpec') -> bool:
        if self.kind != other.kind:
            return False
        if self.kind == 'path':
            return self.path == other.path
        return self.registry == other.registry


@dataclass
class ResolvedPackage:
    name: str
    version: Version
    source: dict[str, Any]
    dependencies: dict[str, Any] = field(default_factory=dict)
    root: Path | None = None
    entry: VersionEntry | None = None

    @property
    def kind(self) -> str:
        return str(self.source.get('kind', ''))

    def to_locked(self) -> LockedPackage:
        return LockedPackage(
            name=self.name,
            version=self.version,
            source=dict(self.source),
            dependencies=dict(self.dependencies),
        )


@dataclass
class Requirement:
    constraint: Constraint
    requester: str


@dataclass
class PackageMetadata:
    resolved: ResolvedPackage
    dependencies: dict[str, Any]
    root: Path | None


class Resolver:
    def __init__(
        self,
        manifest: Manifest,
        client: RegistryClient,
        *,
        lock: LockFile | None = None,
        update: set[str] | None = None,
        update_all: bool = False,
    ):
        self.manifest = manifest
        self.client = client
        self.lock = lock
        self.update = set(update or ())
        self.update_all = update_all
        self._clients: dict[str, RegistryClient] = {}
        if client.url is not None:
            self._clients[client.url] = client

    def resolve(self) -> dict[str, ResolvedPackage]:
        constraints: dict[str, list[Requirement]] = {}
        sources: dict[str, SourceSpec] = {}
        for name, spec in self.manifest.dependencies.items():
            if self.manifest.name is not None and name == self.manifest.name:
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'resolver',
                    f"package '{name}' depends on itself",
                    ['remove the self dependency from powang.toml'],
                ))
            source = self._source_for_spec(spec, self.manifest.root)
            sources[name] = source
            constraints.setdefault(name, []).append(
                Requirement(source.constraint or Constraint.any(), 'root')
            )
        result = self._solve(constraints, sources, {})
        if result is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'resolver',
                'could not resolve dependencies',
                ['check the version constraints in powang.toml'],
            ))
        return result

    def _solve(
        self,
        constraints: dict[str, list[Requirement]],
        sources: dict[str, SourceSpec],
        chosen: dict[str, ResolvedPackage],
    ) -> dict[str, ResolvedPackage] | None:
        if not self._constraints_hold(chosen, constraints):
            return None
        pending = sorted(name for name in constraints if name not in chosen)
        if not pending:
            return chosen
        name = pending[0]
        source = sources[name]
        candidates = self._candidate_versions(name, source, constraints[name])
        if not candidates:
            self._raise_no_candidates(name, source, constraints[name])
        for version in candidates:
            metadata = self._metadata(name, version, source)
            new_constraints = {
                key: list(value) for key, value in constraints.items()
            }
            new_sources = dict(sources)
            new_chosen = dict(chosen)
            new_chosen[name] = metadata.resolved
            conflict = False
            for dependency_name, dependency_value in metadata.dependencies.items():
                if self.manifest.name is not None and \
                        dependency_name == self.manifest.name:
                    raise powang_throw(powang_error_format(
                        'PACKAGE',
                        'resolver',
                        f"package '{name}' depends on the root package '{dependency_name}'",
                        ['remove the dependency cycle from the package metadata'],
                    ))
                dependency_spec = DependencySpec.from_value(
                    dependency_name, dependency_value
                )
                dependency_source = self._source_for_spec(
                    dependency_spec, metadata.root
                )
                existing = new_sources.get(dependency_name)
                if existing is not None and not existing.compatible(dependency_source):
                    conflict = True
                    break
                new_sources[dependency_name] = existing or dependency_source
                new_constraints.setdefault(dependency_name, []).append(
                    Requirement(
                        dependency_source.constraint or Constraint.any(),
                        f"{name} {version}",
                    )
                )
            if conflict:
                continue
            result = self._solve(new_constraints, new_sources, new_chosen)
            if result is not None:
                return result
        return None

    @staticmethod
    def _constraints_hold(
        chosen: dict[str, ResolvedPackage],
        constraints: dict[str, list[Requirement]],
    ) -> bool:
        for name, package in chosen.items():
            for requirement in constraints.get(name, []):
                if not requirement.constraint.matches(package.version):
                    return False
        return True

    def _candidate_versions(
        self,
        name: str,
        source: SourceSpec,
        requirements: list[Requirement],
    ) -> list[Version]:
        constraints = [requirement.constraint for requirement in requirements]
        if source.kind == 'path':
            if source.path is None:
                return []
            manifest = load_manifest(source.path)
            assert manifest is not None
            version = manifest.version or Version(0, 0, 0)
            if all(constraint.matches(version) for constraint in constraints):
                return [version]
            return []
        client = self._client_for(source.registry)
        versions = [
            version for version in client.versions(name)
            if all(constraint.matches(version) for constraint in constraints)
        ]
        entries = [
            version for version in versions
            if (entry := client.entry(name, version)) is not None
            and not entry.yanked
        ]
        locked = self._locked_candidate(name)
        if locked is not None and locked in entries \
                and not self.update_all and name not in self.update:
            entries.remove(locked)
            entries.insert(0, locked)
        return entries

    def _locked_candidate(self, name: str) -> Version | None:
        if self.lock is None:
            return None
        package = self.lock.packages.get(name)
        return package.version if package is not None else None

    def _metadata(
        self,
        name: str,
        version: Version,
        source: SourceSpec,
    ) -> PackageMetadata:
        if source.kind == 'path':
            if source.path is None:
                raise powang_throw(powang_error_format(
                    'PACKAGE', 'resolver', f"path dependency '{name}' has no path",
                ))
            manifest = load_manifest(source.path)
            assert manifest is not None
            if manifest.name is not None and manifest.name != name:
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'resolver',
                    f"path dependency '{name}' has a different package name",
                    [f"manifest name: {manifest.name}"],
                ))
            dependencies = {
                dependency_name: dependency_spec.to_value()
                for dependency_name, dependency_spec in manifest.dependencies.items()
            }
            portable = _portable_path(self.manifest.root, source.path)
            return PackageMetadata(
                resolved=ResolvedPackage(
                    name=name,
                    version=version,
                    source={'kind': 'path', 'path': portable},
                    dependencies=dependencies,
                    root=source.path,
                ),
                dependencies=dependencies,
                root=source.path,
            )
        client = self._client_for(source.registry)
        entry = client.entry(name, version)
        if entry is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'resolver',
                f"package '{name}' {version} is missing from the registry",
            ))
        return PackageMetadata(
            resolved=ResolvedPackage(
                name=name,
                version=version,
                source={
                    'kind': 'registry',
                    'registry': client.url,
                    'archive': entry.archive,
                    'sha256': entry.sha256,
                },
                dependencies=dict(entry.dependencies),
                entry=entry,
            ),
            dependencies=dict(entry.dependencies),
            root=None,
        )

    def _source_for_spec(
        self,
        spec: DependencySpec,
        base: Path | None,
    ) -> SourceSpec:
        if spec.is_path:
            path = Path(spec.path or '')
            if not path.is_absolute():
                path = (base or self.manifest.root) / path
            return SourceSpec(
                kind='path',
                path=path.expanduser().resolve(),
            )
        registry = configured_registry_url(
            spec.registry or self.manifest.registry_url
        )
        return SourceSpec(
            kind='registry',
            constraint=spec.constraint or Constraint.any(),
            registry=registry,
        )

    def _client_for(self, registry: str | None) -> RegistryClient:
        url = configured_registry_url(registry or self.manifest.registry_url)
        if url is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'registry',
                'no registry is configured',
                [
                    'add [registry] url = "..." to powang.toml',
                    'or set POWANG_REGISTRY_URL',
                ],
            ))
        if url not in self._clients:
            self._clients[url] = RegistryClient(url)
        return self._clients[url]

    def _raise_no_candidates(
        self,
        name: str,
        source: SourceSpec,
        requirements: list[Requirement],
    ) -> None:
        details = [
            f"requested by {requirement.requester}: {requirement.constraint}"
            for requirement in requirements
        ]
        if source.kind == 'path':
            details.append(f"path: {source.path}")
        else:
            client = self._client_for(source.registry)
            available = client.versions(name)
            details.append(
                'available versions: '
                + (', '.join(str(version) for version in available) or 'none')
            )
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'resolver',
            f"cannot resolve package '{name}'",
            details,
        ))


def _portable_path(root: Path, path: Path) -> str:
    try:
        relative = Path(os.path.relpath(path, root))
    except ValueError:
        return str(path)
    return relative.as_posix()


def resolve_lock(
    manifest: Manifest,
    lock: LockFile,
) -> dict[str, ResolvedPackage]:
    """Rebuild resolved packages from an existing lock without re-resolving."""
    packages: dict[str, ResolvedPackage] = {}
    for name, locked in lock.packages.items():
        root = None
        entry = None
        if locked.kind == 'path':
            path = Path(locked.path or '')
            if not path.is_absolute():
                path = manifest.root / path
            root = path.resolve()
        else:
            if locked.registry is None:
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'lock',
                    f"registry package '{name}' has no registry url",
                ))
            entry = VersionEntry(
                version=locked.version,
                archive=locked.archive or '',
                sha256=locked.sha256 or '',
                dependencies={},
            )
        packages[name] = ResolvedPackage(
            name=name,
            version=locked.version,
            source=dict(locked.source),
            dependencies=dict(locked.dependencies),
            root=root,
            entry=entry,
        )
    return packages
