"""The ``powang vm`` command line surface.

Commands:

- ``powang vm disasm <file.po> [--json] [--no-verify]``
- ``powang vm run [--trace] <file.po> [args...]``
- ``powang vm diff <file.po>``
- ``powang vm bench [--runs N] [name...]``
"""

from __future__ import annotations

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
    return 2


def _compile_file(path: str, verify: bool = True):
    content = get_file_content(path)
    image = compile_source(
        content, path=path, module_name=Path(path).stem,
        check=False, state=get_state(),
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
    except VerificationError as error:
        print(powang_error_format('COMPILE', 'verifier', str(error)))
        return 1
    except PowangError as error:
        print(str(error))
        return 2 if error.kind == 'USAGE' else 1
    return _usage()
