"""The ``powang vm`` command line surface.

Commands:

- ``powang vm disasm <file.po> [--json] [--no-verify]``
- ``powang vm run [--trace] <file.po> [args...]``
- ``powang vm diff <file.po>``
- ``powang vm bench [--runs N] [name...]``
- ``powang vm native run <file.po> [args...]``
- ``powang vm native compile [--output PATH] [--keep-source] <file.po>``
- ``powang vm native info``
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ..error import PowangError, powang_error_format, powang_throw
from ..state import fresh_state, get_state, set_state
from ..config import load_config, load_project_config
from ..pkg.installer import load_package_config, require_packages_ready
from ..module_loader import find_entry_module
from ..runtime import get_file_content
from ..builtins.tasks import shutdown_state_tasks
from ..stdlib.stdlib_http_server import shutdown_state_servers
from ..stdlib.stdlib_env import set_argv

from .compiler import compile_source
from .disasm import disassemble_image, disassemble_image_json
from .differential import compare_file
from .bench import run_benchmarks, format_results
from .interpreter import VMRunOptions, run_program
from .verifier import verify_image, VerificationError


def _usage() -> int:
    print("powang vm usage:")
    print("    powang vm disasm <file.po> [--json] [--no-verify]")
    print("    powang vm run [--trace] [--vm-cache] <file.po> [args...]")
    print("    powang vm diff <file.po>")
    print("    powang vm bench [--runs N] [name...]")
    print("    powang vm abi [--json]")
    print("    powang vm native run <file.po> [args...]")
    print("    powang vm native compile [--output PATH] [--keep-source] <file.po>")
    print("    powang vm native info")
    return 2


def _compile_file(path: str, verify: bool = True, check: bool = False):
    content = get_file_content(path)
    image = compile_source(
        content, path=path, module_name=Path(path).stem,
        check=check, state=get_state(),
    )
    if verify:
        verify_image(image)
    return image


def _setup_state(path: str) -> object:
    state = fresh_state()
    state.engine = 'vm'
    if not load_project_config(state, path):
        load_config(state, path)
    load_package_config(state, path)
    require_packages_ready(state)
    state.paths['RELATIVE'] = Path(path).resolve()
    state.paths['ABSOLUTE'] = Path(__file__).resolve().parents[2] / 'powang.py'
    return state


def _disasm(args: list[str]) -> int:
    if not args:
        return _usage()
    path = None
    verify = True
    as_json = False
    for argument in args:
        if argument == '--no-verify':
            verify = False
        elif argument == '--json':
            as_json = True
        elif path is None:
            path = argument
    if path is None:
        return _usage()
    state = _setup_state(path)
    set_state(state)
    image = _compile_file(path, verify=verify)
    print(disassemble_image_json(image) if as_json else disassemble_image(image))
    return 0


def _run(args: list[str]) -> int:
    trace = False
    cache = False
    path = None
    script_args: list[str] = []
    for argument in args:
        if argument == '--trace':
            trace = True
        elif argument == '--vm-cache':
            cache = True
        elif path is None:
            path = argument
        else:
            script_args.append(argument)
    if path is None:
        return _usage()
    state = _setup_state(path)
    set_state(state)
    set_argv(script_args)
    try:
        content = get_file_content(path)
        run_program(
            content, path=path, check=True, state=state,
            engine_options=VMRunOptions(
                trace=trace,
                cache_dir=".powang/cache/bytecode" if cache else None,
            ),
        )
        return 0
    except PowangError as error:
        print(str(error))
        return 2 if error.kind == 'USAGE' else 1
    finally:
        try:
            shutdown_state_tasks(state)
        except Exception:
            pass
        try:
            shutdown_state_servers(state)
        except Exception:
            pass
        try:
            state.close()
        except Exception:
            pass


def _diff(args: list[str]) -> int:
    if len(args) != 1:
        return _usage()
    result = compare_file(args[0])
    print(result.report())
    if not result.equal:
        print("--- tree stdout ---")
        print(result.tree.stdout)
        print("--- vm stdout ---")
        print(result.vm.stdout)
        print("--- tree stderr ---")
        print(result.tree.stderr)
        print("--- vm stderr ---")
        print(result.vm.stderr)
        return 1
    return 0


def _bench(args: list[str]) -> int:
    runs = 3
    names: list[str] = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == '--runs' and index + 1 < len(args):
            runs = int(args[index + 1])
            index += 2
            continue
        names.append(argument)
        index += 1
    results = run_benchmarks(names or None, runs=runs)
    print(format_results(results))
    return 0


def _abi(args: list[str]) -> int:
    from .native_abi import render_c_header, render_json_contract
    print(render_json_contract() if '--json' in args else render_c_header(), end='')
    return 0


_NATIVE_USAGE_LINES: tuple[str, ...] = (
    "    powang vm native run <file.po> [args...]",
    "    powang vm native compile [--output PATH] [--keep-source] <file.po>",
    "    powang vm native diff [--corpus DIR] [--examples PATH] [--json] [--fail-fast]",
    "    powang vm native bench [--runs N] [--json] [file.po...]",
    "    powang vm native clean [--all]",
    "    powang vm native pack [--output DIR]",
    "    powang vm native info",
)


def _native_usage() -> None:
    for line in _NATIVE_USAGE_LINES:
        print(line)


def _native_info(args: list[str]) -> int:
    from .native.build import ensure_runtime
    from .native.compiler import IntegratedGcc, NativeBuildError

    try:
        paths = ensure_runtime()
    except NativeBuildError as error:
        print(f"native build error: {error}", file=sys.stderr)
        return 1
    driver = IntegratedGcc(
        include_dir=paths.include_dir, library_dir=paths.build_dir,
    )
    print(f"compiler: {driver.available() or 'missing'}")
    print(f"version: {driver.version()}")
    print(f"runtime: {paths.library}")
    print(f"native: {paths.executable}")
    return 0


def _native_compile(args: list[str]) -> int:
    from .native.compiler import NativeBuildError
    from .native.loader import compile_image

    output: Path | None = None
    keep_source = False
    path: str | None = None
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == '--output':
            if index + 1 >= len(args):
                _native_usage()
                return 2
            output = Path(args[index + 1])
            index += 2
            continue
        if argument == '--keep-source':
            keep_source = True
            index += 1
            continue
        if argument.startswith('-') or path is not None:
            _native_usage()
            return 2
        path = argument
        index += 1
    if path is None:
        _native_usage()
        return 2
    if output is None:
        suffix = '.exe' if os.name == 'nt' else ''
        output = Path('build/native') / (Path(path).stem + suffix)
    from .native.session import compile_native_file

    try:
        session = compile_native_file(path, check=True)
        program = compile_image(
            session.image,
            output=output,
            keep_source=keep_source,
            bundle=session.bundle,
        )
    except PowangError as error:
        print(str(error))
        return 1
    except NativeBuildError as error:
        print(f"native build error: {error}", file=sys.stderr)
        if error.result is not None and error.result.stderr:
            print(error.result.stderr, file=sys.stderr, end='')
        return 1
    print(program.executable)
    return 0


def _native_run(args: list[str]) -> int:
    from .native.compiler import NativeBuildError
    from .native.session import run_native_file

    path: str | None = None
    script_args: list[str] = []
    for argument in args:
        if path is None:
            if argument.startswith('-'):
                continue
            path = argument
        else:
            script_args.append(argument)
    if path is None:
        _native_usage()
        return 2
    try:
        result = run_native_file(path, script_args)
    except PowangError as error:
        print(str(error))
        return 1
    except NativeBuildError as error:
        print(f"native build error: {error}", file=sys.stderr)
        if error.result is not None and error.result.stderr:
            print(error.result.stderr, file=sys.stderr, end='')
        return 1
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def _native_diff(args: list[str]) -> int:
    from .native.differential import run

    corpora: list[Path] = []
    examples: list[Path] = []
    fail_fast = False
    as_json = False
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == '--corpus' and index + 1 < len(args):
            corpora.append(Path(args[index + 1]))
            index += 2
            continue
        if argument == '--examples' and index + 1 < len(args):
            examples.append(Path(args[index + 1]))
            index += 2
            continue
        if argument == '--fail-fast':
            fail_fast = True
        elif argument == '--json':
            as_json = True
        elif argument.startswith('-'):
            _native_usage()
            return 2
        else:
            path = Path(argument)
            if path.is_dir():
                corpora.append(path)
            else:
                examples.append(path)
        index += 1
    if not corpora and not examples:
        _native_usage()
        return 2
    return run(
        corpora, examples, fail_fast=fail_fast, as_json=as_json,
    )


def _native_bench(args: list[str]) -> int:
    import json

    from .native.bench import run_native_benchmarks

    runs = 3
    as_json = False
    paths: list[Path] = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == '--runs' and index + 1 < len(args):
            runs = max(1, int(args[index + 1]))
            index += 2
            continue
        if argument == '--json':
            as_json = True
            index += 1
            continue
        if argument.startswith('-'):
            _native_usage()
            return 2
        paths.append(Path(argument))
        index += 1
    try:
        records = run_native_benchmarks(paths or None, runs=runs)
    except FileNotFoundError:
        print('no benchmark programs selected', file=sys.stderr)
        return 2
    except Exception as error:
        print(f"native build error: {error}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(records, indent=2))
    else:
        for record in records:
            print(
                f"{record['program']}: "
                f"vm {record['python_seconds'] * 1000:.2f} ms, "
                f"native {record['native_seconds'] * 1000:.2f} ms, "
                f"{record['speedup']:.2f}x"
            )
    return 0


def _native_clean(args: list[str]) -> int:
    import shutil

    from .native.build import BUILD_DIR

    remove_all = '--all' in args
    targets = [BUILD_DIR] if remove_all else [BUILD_DIR / 'cache']
    for target in targets:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            print(f"removed {target}")
        else:
            print(f"absent {target}")
    return 0


def _native_pack(args: list[str]) -> int:
    import shutil

    from .native.build import ensure_runtime

    output: Path | None = None
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == '--output' and index + 1 < len(args):
            output = Path(args[index + 1])
            index += 2
            continue
        if argument.startswith('-'):
            _native_usage()
            return 2
        output = Path(argument)
        index += 1
    try:
        paths = ensure_runtime()
    except Exception as error:
        print(f"native build error: {error}", file=sys.stderr)
        return 1
    destination = output or (Path.cwd() / 'dist' / 'native')
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths.library, destination / paths.library.name)
    shutil.copy2(paths.executable, destination / paths.executable.name)
    shutil.copytree(
        paths.include_dir, destination / 'include',
        dirs_exist_ok=True,
    )
    print(destination)
    return 0


def _native(args: list[str]) -> int:
    if not args:
        _native_usage()
        return 2
    command = args[0]
    rest = args[1:]
    if command in {'--help', '-h', 'help'}:
        _native_usage()
        return 0
    if command == 'info':
        return _native_info(rest)
    if command == 'compile':
        return _native_compile(rest)
    if command == 'run':
        return _native_run(rest)
    if command == 'diff':
        return _native_diff(rest)
    if command == 'bench':
        return _native_bench(rest)
    if command == 'clean':
        return _native_clean(rest)
    if command == 'pack':
        return _native_pack(rest)
    _native_usage()
    return 2


def vm_main(args: list[str]) -> int:
    if not args or args[0] in {'--help', '-h', 'help'}:
        return _usage()
    command = args[0]
    rest = args[1:]
    try:
        if command == 'disasm':
            return _disasm(rest)
        if command == 'run':
            return _run(rest)
        if command == 'diff':
            return _diff(rest)
        if command == 'bench':
            return _bench(rest)
        if command == 'abi':
            return _abi(rest)
        if command == 'native':
            return _native(rest)
    except VerificationError as error:
        print(powang_error_format('COMPILE', 'verifier', str(error)))
        return 1
    except PowangError as error:
        print(str(error))
        return 2 if error.kind == 'USAGE' else 1
    return _usage()
