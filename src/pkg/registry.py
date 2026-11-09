"""Registry index loading, package downloads and safe archive extraction."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from ..error import powang_error_format, powang_throw
from .manifest import Manifest, load_manifest
from .semver import Constraint, Version

REGISTRY_INDEX_NAME = 'index.json'
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30


def powang_home() -> Path:
    raw = os.environ.get('POWANG_HOME')
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / '.powang').resolve()


def cache_root() -> Path:
    return powang_home() / 'cache'


def registry_cache_dir(url: str) -> Path:
    digest = hashlib.sha256(url.encode('utf-8')).hexdigest()
    return cache_root() / 'registries' / digest


def archive_cache_path(sha256: str) -> Path:
    return cache_root() / 'archives' / f'{sha256}.tar.gz'


def configured_registry_url(value: str | None) -> str | None:
    if value:
        return value
    return os.environ.get('POWANG_REGISTRY_URL') or None


def normalize_registry_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise powang_throw(powang_error_format(
            'PACKAGE', 'registry', 'registry url must be a non-empty string',
        ))
    value = url.strip()
    if value.startswith('file://'):
        parsed = urllib.parse.urlparse(value)
        return Path(urllib.request.url2pathname(parsed.path)).expanduser().resolve().as_uri()
    if value.startswith('http://') or value.startswith('https://'):
        return value.rstrip('/')
    return str(Path(value).expanduser().resolve())


def _is_http(url: str) -> bool:
    return url.startswith('http://') or url.startswith('https://')


def _local_path(url: str) -> Path:
    if url.startswith('file://'):
        parsed = urllib.parse.urlparse(url)
        return Path(urllib.request.url2pathname(parsed.path))
    return Path(url)


def _index_location(url: str) -> tuple[str, str]:
    """Return ``(index_url, base_url)`` for a registry URL."""
    if _is_http(url):
        if url.endswith('.json'):
            base = url.rsplit('/', 1)[0]
            return url, base
        return url.rstrip('/') + '/' + REGISTRY_INDEX_NAME, url.rstrip('/')
    path = _local_path(url)
    if path.is_file():
        return str(path), str(path.parent)
    return str(path / REGISTRY_INDEX_NAME), str(path)


def _read_bytes(url: str) -> bytes:
    if _is_http(url):
        request = urllib.request.Request(
            url,
            headers={'User-Agent': 'powang-pkg/0.16.0'},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=DOWNLOAD_TIMEOUT_SECONDS
            ) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
        except urllib.error.URLError as error:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'registry',
                f"cannot fetch {url}",
                [str(error.reason if hasattr(error, 'reason') else error)],
            )) from None
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'registry',
                f"response is too large: {url}",
                [f"limit: {MAX_DOWNLOAD_BYTES} bytes"],
            ))
        return data
    path = _local_path(url)
    try:
        if path.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'registry',
                f"file is too large: {path}",
                [f"limit: {MAX_DOWNLOAD_BYTES} bytes"],
            ))
        return path.read_bytes()
    except OSError as error:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'registry',
            f"cannot read {path}",
            [str(error)],
        )) from None


@dataclass(frozen=True)
class VersionEntry:
    version: Version
    archive: str
    sha256: str
    dependencies: dict[str, str] = field(default_factory=dict)
    yanked: bool = False


@dataclass
class PackageIndex:
    name: str
    latest: Version | None
    versions: dict[Version, VersionEntry] = field(default_factory=dict)
    description: str = ''


@dataclass
class RegistryIndex:
    url: str
    packages: dict[str, PackageIndex] = field(default_factory=dict)

    def package(self, name: str) -> PackageIndex | None:
        return self.packages.get(name)

    def versions(self, name: str) -> list[Version]:
        package = self.packages.get(name)
        if package is None:
            return []
        return sorted(package.versions, reverse=True)

    def entry(self, name: str, version: Version) -> VersionEntry | None:
        package = self.packages.get(name)
        if package is None:
            return None
        return package.versions.get(version)


def _parse_index(url: str, data: bytes) -> RegistryIndex:
    try:
        payload = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'registry',
            f"invalid registry index at {url}",
            [str(error)],
        )) from None
    if not isinstance(payload, dict):
        raise powang_throw(powang_error_format(
            'PACKAGE', 'registry', 'registry index must contain an object',
        ))
    if payload.get('format') != 1:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'registry',
            "unsupported registry format",
            [f"expected format 1, found {payload.get('format')!r}"],
        ))
    raw_packages = payload.get('packages')
    if not isinstance(raw_packages, dict):
        raise powang_throw(powang_error_format(
            'PACKAGE', 'registry', 'registry index has no packages table',
        ))
    packages: dict[str, PackageIndex] = {}
    for name, raw_package in raw_packages.items():
        if not isinstance(name, str) or not isinstance(raw_package, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'registry', 'invalid package entry in registry index',
            ))
        description = raw_package.get('description')
        if not isinstance(description, str):
            description = ''
        raw_versions = raw_package.get('versions')
        if not isinstance(raw_versions, dict):
            raise powang_throw(powang_error_format(
                'PACKAGE', 'registry', f"package '{name}' has no versions table",
            ))
        versions: dict[Version, VersionEntry] = {}
        for version_text, raw_entry in raw_versions.items():
            if not isinstance(raw_entry, dict):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'registry',
                    f"package '{name}' has an invalid version entry",
                ))
            version = Version.parse(version_text)
            archive = raw_entry.get('archive')
            sha256 = raw_entry.get('sha256')
            if not isinstance(archive, str) or not archive.strip():
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'registry',
                    f"package '{name}' {version} has no archive",
                ))
            if not isinstance(sha256, str) or not _valid_sha256(sha256):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'registry',
                    f"package '{name}' {version} has an invalid sha256",
                    ['write the archive integrity as 64 hexadecimal characters'],
                ))
            dependencies = raw_entry.get('dependencies') or {}
            if not isinstance(dependencies, dict) or any(
                not isinstance(dep_name, str) or not isinstance(dep_value, str)
                for dep_name, dep_value in dependencies.items()
            ):
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'registry',
                    f"package '{name}' {version} has invalid dependencies",
                ))
            for dep_value in dependencies.values():
                Constraint.parse(dep_value)
            yanked = bool(raw_entry.get('yanked', False))
            versions[version] = VersionEntry(
                version=version,
                archive=archive.strip(),
                sha256=sha256.lower(),
                dependencies=dict(dependencies),
                yanked=yanked,
            )
        latest_text = raw_package.get('latest')
        latest = Version.parse(latest_text) if isinstance(latest_text, str) else None
        if latest is None and versions:
            latest = max(versions)
        packages[name] = PackageIndex(
            name=name,
            latest=latest,
            versions=versions,
            description=description,
        )
    return RegistryIndex(url=url, packages=packages)


def _valid_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(character in '0123456789abcdefABCDEF' for character in value)


def load_registry_index(
    url: str,
    *,
    offline: bool = False,
    refresh: bool = False,
) -> RegistryIndex:
    normalized = normalize_registry_url(url)
    index_url, base_url = _index_location(normalized)
    cache_dir = registry_cache_dir(normalized)
    cache_file = cache_dir / REGISTRY_INDEX_NAME

    if offline:
        if not cache_file.is_file():
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'registry',
                'offline mode has no cached registry index',
                [f"registry: {normalized}", f"cache: {cache_file}"],
            ))
        return _parse_index(base_url, cache_file.read_bytes())

    if _is_http(normalized) and not refresh and cache_file.is_file():
        ## The cache is a fallback, not the primary source. Try the network
        ## first so updates become visible, then fall back on transport errors.
        pass

    try:
        data = _read_bytes(index_url)
    except Exception:
        if cache_file.is_file():
            return _parse_index(base_url, cache_file.read_bytes())
        raise
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = cache_file.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(cache_file)
    return _parse_index(base_url, data)


class RegistryClient:
    def __init__(self, url: str | None, *, offline: bool = False):
        self.url = normalize_registry_url(url) if url else None
        self.offline = offline
        self._index: RegistryIndex | None = None

    @property
    def index(self) -> RegistryIndex:
        if self.url is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'registry',
                'no registry is configured',
                [
                    'add [registry] url = "..." to powang.toml',
                    'or set POWANG_REGISTRY_URL',
                ],
            ))
        if self._index is None:
            self._index = load_registry_index(
                self.url, offline=self.offline, refresh=True
            )
        return self._index

    def package(self, name: str) -> PackageIndex | None:
        return self.index.package(name)

    def versions(self, name: str) -> list[Version]:
        return self.index.versions(name)

    def entry(self, name: str, version: Version) -> VersionEntry | None:
        return self.index.entry(name, version)

    def resolve_archive_url(self, archive: str) -> str:
        if archive.startswith('file://'):
            return archive
        if archive.startswith('http://') or archive.startswith('https://'):
            return archive
        base = self.index.url
        if _is_http(base):
            return urllib.parse.urljoin(base.rstrip('/') + '/', archive)
        return str((_local_path(base) / archive).resolve())

    def fetch_archive(self, entry: VersionEntry) -> Path:
        destination = archive_cache_path(entry.sha256)
        if destination.is_file():
            if _sha256_file(destination) == entry.sha256:
                return destination
            destination.unlink(missing_ok=True)
        archive_url = self.resolve_archive_url(entry.archive)
        data = _read_bytes(archive_url)
        actual = hashlib.sha256(data).hexdigest()
        if actual != entry.sha256:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'integrity',
                f"integrity check failed for {entry.version}",
                [
                    f"expected sha256: {entry.sha256}",
                    f"actual sha256:   {actual}",
                    f"archive: {archive_url}",
                ],
            ))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(destination)
        return destination


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def extract_package_archive(
    archive: Path,
    destination: Path,
    *,
    expected_name: str | None = None,
    expected_version: Version | None = None,
) -> Manifest:
    destination = destination.resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar.getmembers():
                if member.issym() or member.islnk() or member.isdev():
                    raise powang_throw(powang_error_format(
                        'PACKAGE',
                        'archive',
                        'package archive contains an unsupported link or device',
                        [f"member: {member.name}"],
                    ))
                member_path = Path(member.name)
                if member_path.is_absolute() or '..' in member_path.parts:
                    raise powang_throw(powang_error_format(
                        'PACKAGE',
                        'archive',
                        'package archive contains an unsafe path',
                        [f"member: {member.name}"],
                    ))
                target = (destination / member_path).resolve()
                if not target.is_relative_to(destination):
                    raise powang_throw(powang_error_format(
                        'PACKAGE',
                        'archive',
                        'package archive escapes the install directory',
                        [f"member: {member.name}"],
                    ))
            tar.extractall(destination, filter='data')
    except tarfile.TarError as error:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'archive',
            f"cannot extract package archive: {archive}",
            [str(error)],
        )) from None
    manifest = load_manifest(destination)
    assert manifest is not None
    if expected_name is not None and manifest.name is not None \
            and manifest.name != expected_name:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'archive',
            'package name does not match the registry entry',
            [
                f"expected: {expected_name}",
                f"found:    {manifest.name}",
            ],
        ))
    if expected_version is not None and manifest.version is not None \
            and manifest.version != expected_version:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'archive',
            'package version does not match the registry entry',
            [
                f"expected: {expected_version}",
                f"found:    {manifest.version}",
            ],
        ))
    modules_dir = destination / 'modules'
    if not modules_dir.is_dir() or not any(modules_dir.rglob('*.po')):
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'archive',
            'package has no modules',
            ['packages must contain a modules directory with at least one .po file'],
        ))
    return manifest


def clear_cache() -> None:
    root = cache_root()
    if root.exists():
        shutil.rmtree(root)
