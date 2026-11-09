"""Package installation, project module paths and lock validation."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..error import powang_error_format, powang_throw
from .lockfile import LockFile, load_lock, write_lock
from .manifest import Manifest, find_project_root, load_manifest
from .registry import (
    RegistryClient,
    VersionEntry,
    clear_cache,
    configured_registry_url,
    extract_package_archive,
)
from .resolver import ResolvedPackage, Resolver, resolve_lock

PACKAGE_DIR_NAME = '.powang'
PACKAGES_DIR_NAME = 'packages'


def package_dir(root: Path | str) -> Path:
    return Path(root) / PACKAGE_DIR_NAME


def packages_dir(root: Path | str) -> Path:
    return package_dir(root) / PACKAGES_DIR_NAME


def installed_package_dir(root: Path | str, name: str, version) -> Path:
    return packages_dir(root) / name / str(version)


@dataclass
class InstallResult:
    manifest: Manifest
    lock: LockFile
    packages: dict[str, ResolvedPackage]
    installed: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)


def install_project(
    root: Path | str,
    *,
    update: set[str] | None = None,
    update_all: bool = False,
    locked: bool = False,
    offline: bool = False,
    force: bool = False,
) -> InstallResult:
    root = Path(root).resolve()
    manifest = load_manifest(root, required=True)
    assert manifest is not None
    client = RegistryClient(
        configured_registry_url(manifest.registry_url), offline=offline
    )
    existing_lock = load_lock(root)

    if locked:
        if existing_lock is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'lock',
                'locked install requires powang.lock',
                ['run powang pkg install to create it'],
            ))
        if not existing_lock.is_current(manifest):
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'lock',
                'powang.lock is out of date',
                ['run powang pkg install to update it'],
            ))
        resolved = resolve_lock(manifest, existing_lock)
    elif existing_lock is not None and existing_lock.is_current(manifest) \
            and not update and not update_all and not force:
        _validate_lock_against_manifest(manifest, existing_lock)
        if any(package.kind == 'path' for package in existing_lock.packages.values()):
            resolved = Resolver(
                manifest, client, lock=existing_lock, update=set()
            ).resolve()
        else:
            resolved = resolve_lock(manifest, existing_lock)
    else:
        resolved = Resolver(
            manifest,
            client,
            lock=existing_lock,
            update=update,
            update_all=update_all,
        ).resolve()

    installed: list[str] = []
    reused: list[str] = []
    clients: dict[str, RegistryClient] = {}
    if client.url is not None:
        clients[client.url] = client
    for name, package in sorted(resolved.items()):
        if package.kind == 'path':
            _validate_path_package(manifest, package)
            reused.append(name)
            continue
        destination = installed_package_dir(root, name, package.version)
        if not force and _installed_package_is_valid(
            destination, name, package.version
        ):
            reused.append(name)
            continue
        registry = package.source.get('registry')
        if not isinstance(registry, str):
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'install',
                f"registry package '{name}' has no registry url",
            ))
        package_client = clients.get(registry)
        if package_client is None:
            package_client = RegistryClient(registry, offline=offline)
            clients[registry] = package_client
        entry = package.entry
        if entry is None:
            archive = package.source.get('archive')
            sha256 = package.source.get('sha256')
            if not isinstance(archive, str) or not isinstance(sha256, str):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'install',
                    f"package '{name}' has no archive in the lock file",
                ))
            entry = VersionEntry(
                version=package.version,
                archive=archive,
                sha256=sha256,
            )
        archive_path = package_client.fetch_archive(entry)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.tmp')
        try:
            extract_package_archive(
                archive_path,
                temporary,
                expected_name=name,
                expected_version=package.version,
            )
            if destination.exists():
                shutil.rmtree(destination)
            temporary.replace(destination)
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
            raise
        installed.append(name)

    lock = LockFile(
        manifest_hash=manifest.dependencies_hash(),
        packages={
            name: package.to_locked()
            for name, package in resolved.items()
        },
    )
    if not locked:
        write_lock(root, lock)
    _write_package_gitignore(root)
    return InstallResult(
        manifest=manifest,
        lock=lock,
        packages=resolved,
        installed=installed,
        reused=reused,
    )


def _validate_lock_against_manifest(manifest: Manifest, lock: LockFile) -> None:
    for name, spec in manifest.dependencies.items():
        locked = lock.packages.get(name)
        if locked is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'lock',
                f"package '{name}' is missing from powang.lock",
                ['run powang pkg install to update the lock file'],
            ))
        if spec.is_path:
            if locked.kind != 'path':
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'lock',
                    f"package '{name}' changed from a registry dependency to a path dependency",
                    ['run powang pkg install to update the lock file'],
                ))
            expected = (manifest.root / (spec.path or '')).resolve()
            actual = (manifest.root / (locked.path or '')).resolve()
            if expected != actual:
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'lock',
                    f"path dependency '{name}' changed",
                    ['run powang pkg install to update the lock file'],
                ))
        else:
            if locked.kind != 'registry':
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'lock',
                    f"package '{name}' changed from a path dependency to a registry dependency",
                    ['run powang pkg install to update the lock file'],
                ))
            if spec.constraint is not None and \
                    not spec.constraint.matches(locked.version):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'lock',
                    f"package '{name}' {locked.version} does not satisfy its constraint",
                    ['run powang pkg install to update the lock file'],
                ))


def _validate_path_package(manifest: Manifest, package: ResolvedPackage) -> None:
    if package.root is None or not package.root.is_dir():
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'install',
            f"path dependency '{package.name}' does not exist",
            [f"path: {package.root}"],
        ))
    dependency_manifest = load_manifest(package.root, required=True)
    assert dependency_manifest is not None
    if dependency_manifest.name is not None and \
            dependency_manifest.name != package.name:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'install',
            f"path dependency '{package.name}' has a different package name",
            [f"found: {dependency_manifest.name}"],
        ))


def _installed_package_is_valid(
    destination: Path,
    name: str,
    version,
) -> bool:
    if not destination.is_dir():
        return False
    try:
        manifest = load_manifest(destination, required=False)
    except Exception:
        return False
    if manifest is None:
        return False
    if manifest.name is not None and manifest.name != name:
        return False
    if manifest.version is not None and manifest.version != version:
        return False
    modules = destination / 'modules'
    return modules.is_dir() and any(modules.rglob('*.po'))


def _write_package_gitignore(root: Path) -> None:
    directory = package_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    ignore = directory / '.gitignore'
    if not ignore.exists():
        ignore.write_text('*\n', encoding='utf-8', newline='\n')


def module_paths_for_lock(
    root: Path | str,
    lock: LockFile,
) -> list[Path]:
    root = Path(root).resolve()
    paths: list[Path] = []
    for name, package in sorted(lock.packages.items()):
        if package.kind == 'path':
            path = Path(package.path or '')
            if not path.is_absolute():
                path = root / path
            paths.append(path.resolve())
        elif package.kind == 'registry':
            paths.append(installed_package_dir(root, name, package.version))
    return paths


def load_package_config(state: Any, base_path: Path | str | None = None) -> bool:
    root = find_project_root(base_path)
    if root is None:
        return False
    manifest = load_manifest(root, required=False)
    if manifest is None:
        return False
    state.package_root = root
    state.package_manifest = manifest
    lock = load_lock(root)
    state.package_lock = lock
    if lock is None:
        state.package_status = 'missing-lock' if manifest.dependencies else 'ok'
        return True
    if not lock.is_current(manifest):
        state.package_status = 'out-of-date'
    else:
        state.package_status = 'ok'
    for path in module_paths_for_lock(root, lock):
        if path.is_dir() and path not in state.module_search_paths:
            state.module_search_paths.append(path)
        elif not path.is_dir() and state.package_status == 'ok':
            state.package_status = 'missing-package'
    return True


def require_packages_ready(state: Any) -> None:
    status = getattr(state, 'package_status', 'none')
    if status == 'ok':
        return
    if status == 'missing-lock':
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'run',
            'project dependencies are not installed',
            [
                'run powang pkg install in the project directory',
                'then run the project again',
            ],
        ))
    if status == 'out-of-date':
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'run',
            'powang.lock is out of date',
            ['run powang pkg install to update the lock file'],
        ))
    if status == 'missing-package':
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'run',
            'installed package files are missing',
            ['run powang pkg install to restore them'],
        ))


def clean_project(root: Path | str, *, cache: bool = False) -> None:
    root = Path(root).resolve()
    directory = package_dir(root)
    if directory.exists():
        shutil.rmtree(directory)
    if cache:
        clear_cache()



