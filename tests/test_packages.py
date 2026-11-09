"""Package manifests, semver, registry resolution, installation and CLI tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_command  # noqa: E402

from src.pkg.installer import (  # noqa: E402
    install_project,
    installed_package_dir,
    load_package_config,
)
from src.pkg.lockfile import load_lock  # noqa: E402
from src.pkg.manifest import (  # noqa: E402
    DependencySpec,
    Manifest,
    load_manifest,
    write_manifest,
)
from src.pkg.registry import RegistryClient  # noqa: E402
from src.pkg.semver import Constraint, Version  # noqa: E402
from src.state import fresh_state  # noqa: E402


def write_package(
    registry: Path,
    name: str,
    version: str,
    source: str,
    dependencies: dict[str, str] | None = None,
) -> dict:
    work = registry / 'work' / f'{name}-{version}'
    work.mkdir(parents=True, exist_ok=True)
    dependency_text = ''
    if dependencies:
        dependency_text = '\n[dependencies]\n' + '\n'.join(
            f'{key} = "{value}"' for key, value in sorted(dependencies.items())
        ) + '\n'
    (work / 'powang.toml').write_text(
        f'[package]\nname = "{name}"\nversion = "{version}"\n{dependency_text}',
        encoding='utf-8',
        newline='\n',
    )
    module = work / 'modules' / f'{name}.po'
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(source, encoding='utf-8', newline='\n')
    archive = registry / 'archives' / f'{name}-{version}.tar.gz'
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sorted(work.rglob('*')):
            tar.add(path, arcname=str(path.relative_to(work)))
    return {
        'archive': f'archives/{name}-{version}.tar.gz',
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'dependencies': dependencies or {},
    }


def write_registry(
    registry: Path,
    packages: dict[str, dict[str, dict]],
    descriptions: dict[str, str] | None = None,
) -> None:
    index_packages = {}
    for name, versions in packages.items():
        latest = max(Version.parse(version) for version in versions)
        index_packages[name] = {
            'latest': str(latest),
            'description': (descriptions or {}).get(name, ''),
            'versions': versions,
        }
    registry.mkdir(parents=True, exist_ok=True)
    (registry / 'index.json').write_text(
        json.dumps({'format': 1, 'packages': index_packages}),
        encoding='utf-8',
        newline='\n',
    )


def write_project(
    root: Path,
    registry: Path | None,
    dependencies: str = '',
    name: str = 'app',
    version: str = '0.1.0',
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    registry_line = (
        f'\n[registry]\nurl = "{registry.as_posix()}"\n' if registry else ''
    )
    dependency_block = (
        f'\n[dependencies]\n{dependencies}\n' if dependencies else ''
    )
    (root / 'powang.toml').write_text(
        f'[package]\nname = "{name}"\nversion = "{version}"\n'
        f'{registry_line}{dependency_block}',
        encoding='utf-8',
        newline='\n',
    )
    return root


class SemverTests(unittest.TestCase):
    def test_versions_parse_and_sort(self) -> None:
        self.assertEqual(Version.parse('v1.2'), Version(1, 2, 0))
        self.assertLess(Version(1, 2, 0), Version(1, 10, 0))
        self.assertGreater(Version(2, 0, 0), Version(1, 9, 9))

    def test_caret_constraints(self) -> None:
        constraint = Constraint.parse('^1.2.3')
        self.assertTrue(constraint.matches(Version(1, 2, 3)))
        self.assertTrue(constraint.matches(Version(1, 9, 0)))
        self.assertFalse(constraint.matches(Version(2, 0, 0)))
        zero = Constraint.parse('^0.2.3')
        self.assertTrue(zero.matches(Version(0, 2, 9)))
        self.assertFalse(zero.matches(Version(0, 3, 0)))

    def test_tilde_and_ranges(self) -> None:
        tilde = Constraint.parse('~1.2.3')
        self.assertTrue(tilde.matches(Version(1, 2, 9)))
        self.assertFalse(tilde.matches(Version(1, 3, 0)))
        ranged = Constraint.parse('>=1.0.0 <2.0.0')
        self.assertTrue(ranged.matches(Version(1, 5, 0)))
        self.assertFalse(ranged.matches(Version(2, 0, 0)))

    def test_invalid_constraint(self) -> None:
        with self.assertRaises(Exception):
            Constraint.parse('not-a-version')


class ManifestTests(unittest.TestCase):
    def test_manifest_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix='powang-manifest-') as directory:
            root = Path(directory)
            manifest = Manifest(
                root=root,
                path=root / 'powang.toml',
                raw={'extern': {'modules': ['math']}},
                name='app',
                version=Version(1, 2, 3),
                description='demo',
                dependencies={
                    'mathlib': DependencySpec(
                        name='mathlib',
                        constraint=Constraint.parse('^1.0.0'),
                    ),
                    'local': DependencySpec(name='local', path='../local'),
                },
                registry_url='https://example.test/registry',
            )
            write_manifest(manifest)
            loaded = load_manifest(root)
            assert loaded is not None
            self.assertEqual(loaded.name, 'app')
            self.assertEqual(loaded.version, Version(1, 2, 3))
            self.assertEqual(loaded.dependencies['local'].path, '../local')
            self.assertEqual(
                str(loaded.dependencies['mathlib'].constraint), '^1.0.0'
            )
            self.assertEqual(loaded.raw['extern']['modules'], ['math'])

    def test_manifest_hash_changes_with_dependencies(self) -> None:
        with tempfile.TemporaryDirectory(prefix='powang-manifest-') as directory:
            root = Path(directory)
            manifest = Manifest(root=root, path=root / 'powang.toml')
            first = manifest.dependencies_hash()
            manifest.dependencies['mathlib'] = DependencySpec(
                name='mathlib', constraint=Constraint.parse('^1.0.0')
            )
            self.assertNotEqual(first, manifest.dependencies_hash())

    def test_path_and_version_are_rejected(self) -> None:
        with self.assertRaises(Exception):
            DependencySpec.from_value(
                'local', {'path': '../local', 'version': '^1.0.0'}
            )


class PackageInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='powang-pkg-')
        self.root = Path(self.temporary.name)
        self.registry = self.root / 'registry'
        self.home = self.root / 'home'
        self.environment = {'POWANG_HOME': str(self.home)}
        self.old_home = os.environ.get('POWANG_HOME')
        os.environ['POWANG_HOME'] = str(self.home)

    def tearDown(self) -> None:
        if self.old_home is None:
            os.environ.pop('POWANG_HOME', None)
        else:
            os.environ['POWANG_HOME'] = self.old_home
        self.temporary.cleanup()

    def build_basic_registry(self) -> None:
        mathlib = write_package(
            self.registry,
            'mathlib',
            '1.0.0',
            'module mathlib;\nexport fun add(a: int, b: int): int >> a + b;\n',
            {'utils': '^1.0.0'},
        )
        utils10 = write_package(
            self.registry,
            'utils',
            '1.0.0',
            'module utils;\nexport fun id(value: int): int >> value;\n',
        )
        utils11 = write_package(
            self.registry,
            'utils',
            '1.1.0',
            'module utils;\nexport fun id(value: int): int >> value;\n',
        )
        write_registry(
            self.registry,
            {
                'mathlib': {'1.0.0': mathlib},
                'utils': {'1.0.0': utils10, '1.1.0': utils11},
            },
            {'mathlib': 'math helpers', 'utils': 'utility helpers'},
        )

    def test_registry_install_resolves_transitive_dependencies(self) -> None:
        self.build_basic_registry()
        project = write_project(
            self.root / 'app',
            self.registry,
            'mathlib = "^1.0.0"\n',
        )
        result = install_project(project)
        self.assertEqual(
            {name: str(package.version) for name, package in result.packages.items()},
            {'mathlib': '1.0.0', 'utils': '1.1.0'},
        )
        lock = load_lock(project)
        assert lock is not None
        self.assertEqual(str(lock.packages['utils'].version), '1.1.0')
        self.assertTrue(
            (installed_package_dir(project, 'utils', '1.1.0') / 'powang.toml').is_file()
        )
        self.assertTrue((project / 'powang.lock').is_file())
        self.assertTrue((project / '.powang' / '.gitignore').is_file())

    def test_lock_is_reused_until_update(self) -> None:
        self.build_basic_registry()
        project = write_project(
            self.root / 'app',
            self.registry,
            'mathlib = "^1.0.0"\n',
        )
        install_project(project)
        utils12 = write_package(
            self.registry,
            'utils',
            '1.2.0',
            'module utils;\nexport fun id(value: int): int >> value;\n',
        )
        packages = json.loads(
            (self.registry / 'index.json').read_text(encoding='utf-8')
        )['packages']
        packages['utils']['versions']['1.2.0'] = utils12
        packages['utils']['latest'] = '1.2.0'
        (self.registry / 'index.json').write_text(
            json.dumps({'format': 1, 'packages': packages}),
            encoding='utf-8',
            newline='\n',
        )
        install_project(project)
        lock = load_lock(project)
        assert lock is not None
        self.assertEqual(str(lock.packages['utils'].version), '1.1.0')
        install_project(project, update={'utils'})
        lock = load_lock(project)
        assert lock is not None
        self.assertEqual(str(lock.packages['utils'].version), '1.2.0')

    def test_update_all_ignores_the_lock(self) -> None:
        self.build_basic_registry()
        project = write_project(
            self.root / 'app',
            self.registry,
            'utils = "^1.0.0"\n',
        )
        install_project(project)
        utils12 = write_package(
            self.registry,
            'utils',
            '1.2.0',
            'module utils;\nexport fun id(value: int): int >> value;\n',
        )
        packages = json.loads(
            (self.registry / 'index.json').read_text(encoding='utf-8')
        )['packages']
        packages['utils']['versions']['1.2.0'] = utils12
        packages['utils']['latest'] = '1.2.0'
        (self.registry / 'index.json').write_text(
            json.dumps({'format': 1, 'packages': packages}),
            encoding='utf-8',
            newline='\n',
        )
        install_project(project, update_all=True)
        lock = load_lock(project)
        assert lock is not None
        self.assertEqual(str(lock.packages['utils'].version), '1.2.0')

    def test_conflicting_versions_fail(self) -> None:
        self.build_basic_registry()
        project = write_project(
            self.root / 'app',
            self.registry,
            'mathlib = "^1.0.0"\nutils = "^2.0.0"\n',
        )
        with self.assertRaises(Exception) as caught:
            install_project(project)
        self.assertIn('cannot resolve package', str(caught.exception))

    def test_path_dependency_and_transitive_registry_dependency(self) -> None:
        self.build_basic_registry()
        local = self.root / 'local'
        (local / 'modules').mkdir(parents=True)
        (local / 'powang.toml').write_text(
            f'[package]\nname = "local"\nversion = "0.1.0"\n'
            f'\n[dependencies]\nutils = "^1.0.0"\n'
            f'\n[registry]\nurl = "{self.registry.as_posix()}"\n',
            encoding='utf-8',
            newline='\n',
        )
        (local / 'modules' / 'local.po').write_text(
            'module local;\n'
            'use utils as *;\n'
            'export fun value(): int >> id(42);\n',
            encoding='utf-8',
            newline='\n',
        )
        project = write_project(
            self.root / 'app',
            self.registry,
            'local = { path = "../local" }\n',
        )
        result = install_project(project)
        self.assertEqual(
            {name: str(package.version) for name, package in result.packages.items()},
            {'local': '0.1.0', 'utils': '1.1.0'},
        )
        lock = load_lock(project)
        assert lock is not None
        self.assertEqual(lock.packages['local'].kind, 'path')
        self.assertEqual(lock.packages['local'].path, '../local')

    def test_integrity_mismatch_fails(self) -> None:
        self.build_basic_registry()
        archive = self.registry / 'archives' / 'utils-1.1.0.tar.gz'
        archive.write_bytes(b'not the archive from the index')
        project = write_project(
            self.root / 'app',
            self.registry,
            'utils = "^1.0.0"\n',
        )
        with self.assertRaises(Exception) as caught:
            install_project(project)
        self.assertIn('integrity check failed', str(caught.exception))

    def test_unsafe_archive_path_is_rejected(self) -> None:
        archive = self.registry / 'archives' / 'evil-1.0.0.tar.gz'
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, 'w:gz') as tar:
            info = tarfile.TarInfo('../escape.txt')
            payload = b'escaped'
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        write_registry(
            self.registry,
            {
                'evil': {
                    '1.0.0': {
                        'archive': 'archives/evil-1.0.0.tar.gz',
                        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                        'dependencies': {},
                    }
                }
            },
        )
        project = write_project(
            self.root / 'app',
            self.registry,
            'evil = "1.0.0"\n',
        )
        with self.assertRaises(Exception) as caught:
            install_project(project)
        self.assertIn('unsafe path', str(caught.exception))
        self.assertFalse((self.root / 'escape.txt').exists())

    def test_locked_install_requires_a_lock(self) -> None:
        self.build_basic_registry()
        project = write_project(
            self.root / 'app',
            self.registry,
            'utils = "^1.0.0"\n',
        )
        with self.assertRaises(Exception) as caught:
            install_project(project, locked=True)
        self.assertIn('locked install requires powang.lock', str(caught.exception))

    def test_offline_install_uses_cached_archive(self) -> None:
        self.build_basic_registry()
        project = write_project(
            self.root / 'app',
            self.registry,
            'utils = "^1.0.0"\n',
        )
        install_project(project)
        import shutil
        shutil.rmtree(project / '.powang')
        shutil.rmtree(self.home / 'cache' / 'registries', ignore_errors=True)
        install_project(project, offline=True)
        self.assertTrue(
            (installed_package_dir(project, 'utils', '1.1.0') / 'powang.toml').is_file()
        )

    def test_load_package_config(self) -> None:
        self.build_basic_registry()
        project = write_project(
            self.root / 'app',
            self.registry,
            'utils = "^1.0.0"\n',
        )
        install_project(project)
        state = fresh_state()
        state.module_search_paths = [project]
        self.assertTrue(load_package_config(state, project / 'main.po'))
        self.assertEqual(state.package_status, 'ok')
        self.assertIn(
            installed_package_dir(project, 'utils', '1.1.0'),
            state.module_search_paths,
        )


class PackageCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='powang-pkg-cli-')
        self.root = Path(self.temporary.name)
        self.registry = self.root / 'registry'
        self.home = self.root / 'home'
        self.environment = {'POWANG_HOME': str(self.home)}
        mathlib = write_package(
            self.registry,
            'mathlib',
            '1.0.0',
            'module mathlib;\nexport fun add(a: int, b: int): int >> a + b;\n',
            {'utils': '^1.0.0'},
        )
        utils = write_package(
            self.registry,
            'utils',
            '1.0.0',
            'module utils;\nexport fun id(value: int): int >> value;\n',
        )
        write_registry(
            self.registry,
            {'mathlib': {'1.0.0': mathlib}, 'utils': {'1.0.0': utils}},
            {'mathlib': 'math helpers', 'utils': 'utility helpers'},
        )
        self.project = self.root / 'app'
        self.project.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_pkg(self, *args: str):
        return run_command(
            ['pkg', *args],
            cwd=self.project,
            env=self.environment,
        )

    def test_init_add_list_tree_search_remove(self) -> None:
        result = self.run_pkg(
            'init',
            '--name',
            'app',
            '--version',
            '0.1.0',
            '--registry',
            str(self.registry),
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn('created powang.toml', result.stdout)
        result = self.run_pkg('add', 'mathlib')
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn('installed mathlib 1.0.0', result.stdout)
        self.assertIn('installed utils 1.0.0', result.stdout)
        manifest = (self.project / 'powang.toml').read_text(encoding='utf-8')
        self.assertIn('mathlib = "^1.0.0"', manifest)
        result = self.run_pkg('list')
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn('mathlib 1.0.0', result.stdout)
        result = self.run_pkg('tree')
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn('mathlib 1.0.0', result.stdout)
        self.assertIn('utils 1.0.0', result.stdout)
        result = self.run_pkg('search', 'math')
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn('mathlib 1.0.0 - math helpers', result.stdout)
        result = self.run_pkg('remove', 'mathlib')
        self.assertEqual(result.returncode, 0, result.combined)
        manifest = (self.project / 'powang.toml').read_text(encoding='utf-8')
        self.assertNotIn('mathlib', manifest)

    def test_init_rejects_existing_manifest(self) -> None:
        self.run_pkg('init', '--name', 'app')
        result = self.run_pkg('init', '--name', 'other')
        self.assertEqual(result.returncode, 1)
        self.assertIn('already exists', result.combined)

    def test_add_unknown_package_fails(self) -> None:
        self.run_pkg('init', '--name', 'app', '--registry', str(self.registry))
        result = self.run_pkg('add', 'missing')
        self.assertEqual(result.returncode, 1)
        self.assertIn('is not in the registry', result.combined)

    def test_add_path_dependency(self) -> None:
        local = self.root / 'local'
        (local / 'modules').mkdir(parents=True)
        (local / 'powang.toml').write_text(
            '[package]\nname = "local"\nversion = "0.1.0"\n',
            encoding='utf-8',
            newline='\n',
        )
        (local / 'modules' / 'local.po').write_text(
            'module local;\nexport fun value(): int >> 7;\n',
            encoding='utf-8',
            newline='\n',
        )
        self.run_pkg('init', '--name', 'app', '--registry', str(self.registry))
        result = self.run_pkg('add', '--path', '../local')
        self.assertEqual(result.returncode, 0, result.combined)
        manifest = (self.project / 'powang.toml').read_text(encoding='utf-8')
        self.assertIn('local = { path = "../local" }', manifest)

    def test_install_locked_and_clean(self) -> None:
        self.run_pkg('init', '--name', 'app', '--registry', str(self.registry))
        result = self.run_pkg('install', '--locked')
        self.assertEqual(result.returncode, 1)
        self.run_pkg('add', 'utils')
        result = self.run_pkg('install', '--locked')
        self.assertEqual(result.returncode, 0, result.combined)
        result = self.run_pkg('clean')
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertFalse((self.project / '.powang').exists())
        result = self.run_pkg('install', '--offline')
        self.assertEqual(result.returncode, 0, result.combined)


class PackageRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='powang-pkg-runtime-')
        self.root = Path(self.temporary.name)
        self.registry = self.root / 'registry'
        mathlib = write_package(
            self.registry,
            'mathlib',
            '1.0.0',
            'module mathlib;\nexport fun add(a: int, b: int): int >> a + b;\n',
        )
        write_registry(self.registry, {'mathlib': {'1.0.0': mathlib}})
        self.home = self.root / 'home'
        self.environment = {'POWANG_HOME': str(self.home)}
        self.project = self.root / 'app'
        self.project.mkdir()
        result = run_command(
            ['pkg', 'init', '--name', 'app', '--registry', str(self.registry)],
            cwd=self.project,
            env=self.environment,
        )
        self.assertEqual(result.returncode, 0, result.combined)
        result = run_command(
            ['pkg', 'add', 'mathlib'],
            cwd=self.project,
            env=self.environment,
        )
        self.assertEqual(result.returncode, 0, result.combined)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_file_run_with_wildcard_import(self) -> None:
        (self.project / 'main.po').write_text(
            'use mathlib as *;\nprint(add(1, 2));\nprint("\\n");\n',
            encoding='utf-8',
            newline='\n',
        )
        result = run_command(
            ['main.po'], cwd=self.project, env=self.environment
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, '3\n')

    def test_file_run_with_module_alias(self) -> None:
        (self.project / 'main.po').write_text(
            'use mathlib as m;\nprint(m.add(4, 5));\nprint("\\n");\n',
            encoding='utf-8',
            newline='\n',
        )
        result = run_command(
            ['main.po'], cwd=self.project, env=self.environment
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, '9\n')

    def test_check_reports_package_call_type_error(self) -> None:
        (self.project / 'main.po').write_text(
            'use mathlib as *;\nadd("x", 1);\n',
            encoding='utf-8',
            newline='\n',
        )
        result = run_command(
            ['--check', 'main.po'], cwd=self.project, env=self.environment
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("No overload of 'add' accepts", result.combined)

    def test_powang_run_with_project_file(self) -> None:
        (self.project / 'project.po').write_text(
            'module project;\n'
            'project: Project = Project.['
            'modules >> [], paths >> ["./"], '
            'logLevel >> "info", allowSystem >> false];\n',
            encoding='utf-8',
            newline='\n',
        )
        (self.project / 'main.po').write_text(
            'module main;\nuse mathlib as *;\nprint(add(2, 3));\nprint("\\n");\n',
            encoding='utf-8',
            newline='\n',
        )
        result = run_command(['run'], cwd=self.project, env=self.environment)
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, '5\n')

    def test_missing_lock_blocks_run(self) -> None:
        (self.project / 'powang.lock').unlink()
        (self.project / 'main.po').write_text(
            'use mathlib as *;\nprint(add(1, 2));\n',
            encoding='utf-8',
            newline='\n',
        )
        result = run_command(
            ['main.po'], cwd=self.project, env=self.environment
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('dependencies are not installed', result.combined)


class HttpRegistryTests(unittest.TestCase):
    def test_http_registry_install(self) -> None:
        with tempfile.TemporaryDirectory(prefix='powang-pkg-http-') as directory:
            root = Path(directory)
            registry = root / 'registry'
            package = write_package(
                registry,
                'httplib',
                '1.0.0',
                'module httplib;\nexport fun value(): int >> 11;\n',
            )
            write_registry(registry, {'httplib': {'1.0.0': package}})

            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self, format, *args):  # noqa: A002
                    return

            handler = partial(QuietHandler, directory=str(registry))
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f'http://127.0.0.1:{server.server_address[1]}'
                project = write_project(
                    root / 'app', None, 'httplib = "1.0.0"\n'
                )
                manifest_path = project / 'powang.toml'
                manifest_path.write_text(
                    manifest_path.read_text(encoding='utf-8')
                    + f'\n[registry]\nurl = "{url}"\n',
                    encoding='utf-8',
                    newline='\n',
                )
                install_project(project)
                self.assertTrue(
                    (
                        installed_package_dir(project, 'httplib', '1.0.0')
                        / 'powang.toml'
                    ).is_file()
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
