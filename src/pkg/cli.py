"""Command line interface for ``powang pkg``."""

from __future__ import annotations

import os
from pathlib import Path

from ..error import powang_error_format, powang_throw
from .installer import clean_project, install_project
from .lockfile import load_lock
from .manifest import (
    DependencySpec,
    Manifest,
    default_package_name,
    load_manifest,
    validate_package_name,
    write_manifest,
)
from .registry import RegistryClient, configured_registry_url
from .semver import Constraint, Version

USAGE = """Powang package manager usage:
    powang pkg init [--name NAME] [--version VERSION] [--registry URL]
    powang pkg add NAME[@CONSTRAINT] [--path PATH] [--name NAME] [--no-install]
    powang pkg remove NAME [NAME...] [--no-install]
    powang pkg install [--locked] [--offline] [--force]
    powang pkg update [NAME...]
    powang pkg list
    powang pkg tree
    powang pkg search QUERY
    powang pkg clean [--cache]"""


def package_main(args: list[str]) -> int:
    if not args or args[0] in {'help', '--help', '-h'}:
        print(USAGE)
        return 0
    command = args[0]
    rest = args[1:]
    if command == 'init':
        return _command_init(rest)
    if command == 'add':
        return _command_add(rest)
    if command == 'remove':
        return _command_remove(rest)
    if command == 'install':
        return _command_install(rest)
    if command == 'update':
        return _command_update(rest)
    if command == 'list':
        return _command_list(rest)
    if command == 'tree':
        return _command_tree(rest)
    if command == 'search':
        return _command_search(rest)
    if command == 'clean':
        return _command_clean(rest)
    raise powang_throw(powang_error_format(
        'USAGE',
        'pkg',
        f"unknown package command '{command}'",
        ['run powang pkg --help to see the available commands'],
    ))


def _root() -> Path:
    return Path.cwd().resolve()


def _manifest_or_error(root: Path) -> Manifest:
    manifest = load_manifest(root, required=False)
    if manifest is None:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'manifest',
            'no powang.toml found',
            ['run powang pkg init to create one'],
        ))
    return manifest


def _command_init(args: list[str]) -> int:
    root = _root()
    name = None
    version_text = '0.1.0'
    registry = None
    force = False
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == '--name':
            index += 1
            if index >= len(args):
                _missing_value('--name')
            name = args[index]
        elif argument == '--version':
            index += 1
            if index >= len(args):
                _missing_value('--version')
            version_text = args[index]
        elif argument == '--registry':
            index += 1
            if index >= len(args):
                _missing_value('--registry')
            registry = args[index]
        elif argument == '--force':
            force = True
        else:
            _unknown_option(argument)
        index += 1

    path = root / 'powang.toml'
    if path.exists() and not force:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'init',
            'powang.toml already exists',
            ['use --force to replace it'],
        ))
    package_name = validate_package_name(name or default_package_name(root))
    version = Version.parse(version_text)
    manifest = Manifest(
        root=root,
        path=path,
        raw={},
        name=package_name,
        version=version,
        registry_url=registry,
    )
    write_manifest(manifest)
    print(f'created {path.name} for {package_name} {version}')
    return 0


def _command_add(args: list[str]) -> int:
    root = _root()
    manifest = _manifest_or_error(root)
    specs: list[str] = []
    path_value: str | None = None
    explicit_name: str | None = None
    registry: str | None = None
    no_install = False
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == '--path':
            index += 1
            if index >= len(args):
                _missing_value('--path')
            path_value = args[index]
        elif argument == '--name':
            index += 1
            if index >= len(args):
                _missing_value('--name')
            explicit_name = args[index]
        elif argument == '--registry':
            index += 1
            if index >= len(args):
                _missing_value('--registry')
            registry = args[index]
        elif argument == '--no-install':
            no_install = True
        elif argument.startswith('-'):
            _unknown_option(argument)
        else:
            specs.append(argument)
        index += 1

    if registry:
        manifest.registry_url = registry
    if path_value is not None:
        if specs:
            raise powang_throw(powang_error_format(
                'USAGE',
                'pkg add',
                'a path dependency cannot be combined with a version specification',
            ))
        path = Path(path_value).expanduser()
        if not path.is_absolute():
            path = (root / path).resolve()
        dependency_manifest = load_manifest(path, required=False)
        if dependency_manifest is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'pkg add',
                f"path dependency has no powang.toml: {path}",
            ))
        if dependency_manifest.name is not None:
            dependency_name = dependency_manifest.name
            if explicit_name is not None and explicit_name != dependency_name:
                raise powang_throw(powang_error_format(
                    'PACKAGE',
                    'pkg add',
                    'path dependency name does not match its manifest',
                    [
                        f"requested: {explicit_name}",
                        f"manifest:  {dependency_name}",
                    ],
                ))
        else:
            dependency_name = explicit_name
        if dependency_name is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'pkg add',
                'path dependency has no package name',
                ['add [package] name to its powang.toml or pass --name'],
            ))
        validate_package_name(dependency_name, 'pkg add')
        try:
            relative = Path(os.path.relpath(path, root)).as_posix()
        except ValueError:
            relative = str(path)
        manifest.dependencies[dependency_name] = DependencySpec(
            name=dependency_name,
            path=relative,
        )
    else:
        if not specs:
            raise powang_throw(powang_error_format(
                'USAGE',
                'pkg add',
                'expected a package name or --path',
            ))
        if explicit_name is not None:
            raise powang_throw(powang_error_format(
                'USAGE',
                'pkg add',
                '--name is only valid with --path',
            ))
        registry_url = configured_registry_url(manifest.registry_url)
        client = RegistryClient(registry_url) if registry_url else None
        for spec in specs:
            name, constraint_text = _parse_dependency_spec(spec)
            if constraint_text is None:
                if client is None:
                    raise powang_throw(powang_error_format(
                        'PACKAGE',
                        'pkg add',
                        'no registry is configured',
                        [
                            'pass --registry URL',
                            'add [registry] url to powang.toml',
                            'or set POWANG_REGISTRY_URL',
                        ],
                    ))
                package = client.package(name)
                if package is None or package.latest is None:
                    raise powang_throw(powang_error_format(
                        'PACKAGE',
                        'pkg add',
                        f"package '{name}' is not in the registry",
                    ))
                constraint_text = f'^{package.latest}'
            manifest.dependencies[name] = DependencySpec(
                name=name,
                constraint=Constraint.parse(constraint_text),
            )

    write_manifest(manifest)
    print(f'updated {manifest.path.name}')
    if no_install:
        return 0
    result = install_project(root)
    _print_install_result(result)
    return 0


def _command_remove(args: list[str]) -> int:
    root = _root()
    manifest = _manifest_or_error(root)
    names: list[str] = []
    no_install = False
    for argument in args:
        if argument == '--no-install':
            no_install = True
        elif argument.startswith('-'):
            _unknown_option(argument)
        else:
            names.append(argument)
    if not names:
        raise powang_throw(powang_error_format(
            'USAGE', 'pkg remove', 'expected at least one package name',
        ))
    removed: list[str] = []
    for name in names:
        if name in manifest.dependencies:
            del manifest.dependencies[name]
            removed.append(name)
    if not removed:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'pkg remove',
            'none of the named packages are direct dependencies',
            [f"requested: {', '.join(names)}"],
        ))
    write_manifest(manifest)
    print(f'removed {", ".join(removed)}')
    if no_install:
        return 0
    result = install_project(root)
    _print_install_result(result)
    return 0


def _command_install(args: list[str]) -> int:
    root = _root()
    locked = False
    offline = False
    force = False
    for argument in args:
        if argument == '--locked':
            locked = True
        elif argument == '--offline':
            offline = True
        elif argument == '--force':
            force = True
        elif argument.startswith('-'):
            _unknown_option(argument)
        else:
            raise powang_throw(powang_error_format(
                'USAGE', 'pkg install', f"unexpected argument '{argument}'",
            ))
    result = install_project(
        root, locked=locked, offline=offline, force=force
    )
    _print_install_result(result)
    return 0


def _command_update(args: list[str]) -> int:
    root = _root()
    names: set[str] = set()
    for argument in args:
        if argument.startswith('-'):
            _unknown_option(argument)
        names.add(argument)
    result = install_project(
        root,
        update=names if names else None,
        update_all=not names,
    )
    _print_install_result(result)
    return 0


def _command_list(args: list[str]) -> int:
    if args:
        raise powang_throw(powang_error_format(
            'USAGE', 'pkg list', 'pkg list does not accept arguments',
        ))
    root = _root()
    manifest = load_manifest(root, required=False)
    if manifest is None:
        raise powang_throw(powang_error_format(
            'PACKAGE', 'manifest', 'no powang.toml found',
            ['run powang pkg init to create one'],
        ))
    lock = load_lock(root)
    if lock is None or not lock.packages:
        print('no packages installed')
        return 0
    if not lock.is_current(manifest):
        print('warning: powang.lock is out of date')
    for name, package in sorted(lock.packages.items()):
        if package.kind == 'path':
            source = f'path:{package.path}'
        else:
            source = f'registry:{package.registry}'
        print(f'{name} {package.version} {source}')
    return 0


def _command_tree(args: list[str]) -> int:
    if args:
        raise powang_throw(powang_error_format(
            'USAGE', 'pkg tree', 'pkg tree does not accept arguments',
        ))
    root = _root()
    manifest = _manifest_or_error(root)
    lock = load_lock(root)
    if lock is None:
        print('no packages installed')
        return 0
    root_name = manifest.name or root.name
    root_version = str(manifest.version) if manifest.version else '0.0.0'
    print(f'{root_name} {root_version}')
    visited: set[str] = set()

    def visit(name: str, depth: int) -> None:
        package = lock.packages.get(name)
        prefix = '  ' * depth
        if package is None:
            print(f'{prefix}{name} (missing)')
            return
        print(f'{prefix}{name} {package.version}')
        if name in visited:
            return
        visited.add(name)
        for dependency_name in sorted(package.dependencies):
            visit(dependency_name, depth + 1)

    for name in sorted(manifest.dependencies):
        visit(name, 1)
    return 0


def _command_search(args: list[str]) -> int:
    if len(args) != 1:
        raise powang_throw(powang_error_format(
            'USAGE', 'pkg search', 'expected one search query',
        ))
    query = args[0].lower()
    manifest = load_manifest(_root(), required=False)
    registry_url = (
        manifest.registry_url if manifest is not None else None
    ) or os.environ.get('POWANG_REGISTRY_URL')
    if not registry_url:
        raise powang_throw(powang_error_format(
            'PACKAGE',
            'registry',
            'no registry is configured',
            [
                'add [registry] url to powang.toml',
                'or set POWANG_REGISTRY_URL',
            ],
        ))
    client = RegistryClient(registry_url)
    matches = []
    for name, package in sorted(client.index.packages.items()):
        if query in name.lower() or query in package.description.lower():
            matches.append((name, package))
    if not matches:
        print('no packages found')
        return 0
    for name, package in matches:
        latest = str(package.latest) if package.latest is not None else 'unknown'
        description = f' - {package.description}' if package.description else ''
        print(f'{name} {latest}{description}')
    return 0


def _command_clean(args: list[str]) -> int:
    cache = False
    for argument in args:
        if argument == '--cache':
            cache = True
        else:
            _unknown_option(argument)
    clean_project(_root(), cache=cache)
    print('removed .powang')
    if cache:
        print('removed the package cache')
    return 0


def _print_install_result(result) -> None:
    for name in result.installed:
        package = result.packages[name]
        print(f'installed {name} {package.version}')
    for name in result.reused:
        package = result.packages[name]
        print(f'reused {name} {package.version}')
    print(f'wrote powang.lock with {len(result.lock.packages)} packages')


def _parse_dependency_spec(text: str) -> tuple[str, str | None]:
    if not isinstance(text, str) or not text.strip():
        raise powang_throw(powang_error_format(
            'USAGE', 'pkg add', 'package name cannot be empty',
        ))
    value = text.strip()
    if '@' in value:
        name, constraint = value.rsplit('@', 1)
        constraint = constraint.strip() or None
    else:
        name, constraint = value, None
    validate_package_name(name, 'pkg add')
    if constraint is not None:
        Constraint.parse(constraint)
    return name, constraint


def _missing_value(option: str) -> None:
    raise powang_throw(powang_error_format(
        'USAGE', 'pkg', f'{option} expects a value',
    ))


def _unknown_option(option: str) -> None:
    raise powang_throw(powang_error_format(
        'USAGE', 'pkg', f"unknown option '{option}'",
        ['run powang pkg --help to see the available commands'],
    ))
