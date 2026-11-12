from src import *
from src.state import fresh_state, get_state, set_state
from src.builtins.tasks import shutdown_state_tasks
from src.stdlib.stdlib_http_server import shutdown_state_servers
from src.stdlib.stdlib_env import set_argv
from src.config import load_config, load_project_config
from src.pkg.cli import package_main
from src.pkg.installer import load_package_config, require_packages_ready
from src.module_loader import find_entry_module
from src.typecheck import check_source
from sys import argv, exit as sys_exit, stdin
import os
import sys as _sys
import pathlib
from pathlib import Path
import traceback

INTERPRETER_PATH = pathlib.Path(__file__).resolve()

def print_usage():
    print('Powang X usage:')
    print('    powang                  Runs the REPL.')
    print('    powang (--help | -h)    Display this message.')
    print('    powang input.po         Interprets an input.')
    print('    powang pkg <command>    Manages project packages.')
    print('FLAGS:')
    print('    --ast output.json       Dumps the ast tree into a json.')
    print('    --check                 Parse and type-check only, do not execute.')
    print('    --no-check              Skip static type checking before execution.')
    print('    --no-warnings           Do not print non-fatal warnings.')
    print('    --debug                 Print a full traceback for internal errors.')
    print('    --allow-system          Allow system() while an HTTP server is running.')
    print('    --engine=tree|vm|native Select the execution engine. Default: vm.')
    ## `--help` intentionally exits with status 1, as documented above.
    return 1

def initialize_repl(state=None, engine: str = 'tree'):
    if engine == 'native':
        raise powang_throw(powang_error_format(
            'USAGE', 'repl',
            'the native engine requires an input file',
            ['start the REPL with --engine=tree or --engine=vm'],
        ))
    ## The REPL owns one state for the whole session so variables declared on
    ## one line stay visible on the next. File runs never pass a state and
    ## therefore start fresh on every invocation.
    repl_state = state if state is not None else fresh_state()
    repl_state.paths.setdefault('ABSOLUTE', INTERPRETER_PATH)
    repl_state.paths.setdefault('RELATIVE', repl_state.paths['ABSOLUTE'])
    print('Powang X REPL. Type "exit" or press Ctrl-D to quit.')
    interactive = stdin.isatty()
    while True:
        try:
            if interactive:
                print('>>> ', end='', flush=True)
            line = stdin.readline()
        except KeyboardInterrupt:
            print()
            continue
        if not line: ## EOF (Ctrl-D)
            if interactive:
                print()
            break
        line = line.rstrip('\n')
        if line.strip() == 'exit':
            break
        if not line.strip():
            continue
        try:
            if engine == 'vm':
                session = repl_state.vm_session
                result = session.run_cell(line)
            else:
                result = interpret_program(line, None, state=repl_state)
            if result is None:
                continue
            if isinstance(result, PowangNova) or not result.weak.has_value:
                continue
            casted_result = explicitCastString(result)
            assert casted_result is not None
            print(casted_result.data)
        except PowangError as err:
            print(str(err))
        except AssertionError as ass:
            ## Defensive fallback for a legacy assertion that is not wrapped.
            converted = powang_error_from_exception(ass)
            print(str(converted) if converted is not None else str(ass))
        except RecursionError:
            print(powang_error_format("RECURSION", "runtime", "Python recursion limit reached"))
    return 0

def arguments_handler(args: list[str]):
    input_file: str | None = None
    ast_output: str | None = None
    debug: bool = False
    check_only: bool = False
    no_check: bool = False
    no_warnings: bool = False
    allow_system: bool = False
    script_args: list[str] = []

    if len(args) == 0:
        return 0

    for arg in args:
        if ast_output is not None and ast_output == '':
            ast_output = arg
        elif arg.startswith('--'):
            arg = arg[2:]
            if arg in {'help', 'h'}:
                return 1
            elif arg == 'ast':
                ast_output = ''
            elif arg == 'check':
                check_only = True
            elif arg == 'no-check':
                no_check = True
            elif arg == 'no-warnings':
                no_warnings = True
            elif arg == 'debug':
                debug = True
            elif arg == 'allow-system':
                allow_system = True
            elif arg.startswith('engine='):
                pass
            else:
                raise powang_throw(powang_error_format('USAGE', None, 'Invalid flag for powang file', [
                    f"invalid flag: {arg}"
                ]))
        elif input_file is None:
            input_file = arg
        else:
            ## Everything after the input file belongs to the script, not to
            ## the interpreter. Flags may still appear in any position above.
            script_args.append(arg)


    if ast_output is not None and not ast_output:
        raise powang_throw(powang_error_format('USAGE', None, 'dump output was not provided'))
    if check_only and no_check:
        raise powang_throw(powang_error_format('USAGE', None, 'Conflicting flags', [
            "--check and --no-check cannot be used together"
        ]))
    return input_file, ast_output, debug, check_only, no_check, no_warnings, script_args, allow_system

def run_project(engine_args: list[str] | None = None) -> int:
    root = Path.cwd()
    state = fresh_state()
    state.paths['ABSOLUTE'] = INTERPRETER_PATH
    state.paths['RELATIVE'] = root
    state.warnings_enabled = True
    if not load_project_config(state, None):
        raise powang_throw(powang_error_format(
            'USAGE', 'run', 'project.po is required for powang run',
        ))
    engine = resolve_engine(engine_args or [], state.project_value)
    state.engine = engine
    load_package_config(state, root)
    require_packages_ready(state)
    entry = find_entry_module(root)
    set_state(state)
    set_argv([])
    if engine == 'native':
        from src.vm.native.compiler import NativeBuildError
        from src.vm.native.session import run_native_file
        try:
            result = run_native_file(entry)
        except PowangError as error:
            print(str(error))
            return 1
        except NativeBuildError as error:
            print(f"native build error: {error}", file=_sys.stderr)
            return 1
        _sys.stdout.write(result.stdout)
        _sys.stderr.write(result.stderr)
        return result.returncode
    content = get_file_content(str(entry))
    if engine == 'vm':
        from src.vm.interpreter import run_program
        run_program(content, path=str(entry), check=True, state=state)
    else:
        interpret_program(content, None, check=True, state=state)
    return 0


def main(args: list[str]):
    if args and args[0] in {'pkg', 'package'}:
        return package_main(args[1:])
    if args and args[0] == 'vm':
        from src.vm.cli import vm_main
        return vm_main(args[1:])
    if args and args[0] == 'run':
        engine_args = [argument for argument in args[1:] if argument.startswith('--engine=')]
        if len(args) - 1 != len(engine_args):
            raise powang_throw(powang_error_format(
                'USAGE', 'run',
                'powang run accepts only --engine=tree, --engine=vm or --engine=native',
            ))
        return run_project(engine_args)
    result = arguments_handler(args)
    if isinstance(result, int):
        if result == 0:
            ## The REPL has no script, so no script arguments are visible.
            repl_state = fresh_state()
            repl_state.paths['ABSOLUTE'] = INTERPRETER_PATH
            repl_state.paths['RELATIVE'] = INTERPRETER_PATH
            repl_state.warnings_enabled = '--no-warnings' not in args
            repl_state.allow_system = allow_system if 'allow_system' in locals() else repl_state.allow_system
            load_project_config(repl_state, None)
            if repl_state.project_value is None:
                load_config(repl_state, None)
            engine = resolve_engine(args, repl_state.project_value)
            repl_state.engine = engine
            if engine == 'vm':
                from src.vm.modules import VMSession
                repl_state.vm_session = VMSession(repl_state)
            load_package_config(repl_state, None)
            set_state(repl_state)
            set_argv([])
            return initialize_repl(repl_state, engine)
        elif result == 1:
            return print_usage()

    input_file, ast_output, debug, check_only, no_check, no_warnings, script_args, allow_system = result

    if input_file is None and not check_only and ast_output is None:
        repl_state = fresh_state()
        repl_state.paths['ABSOLUTE'] = INTERPRETER_PATH
        repl_state.paths['RELATIVE'] = INTERPRETER_PATH
        repl_state.warnings_enabled = not no_warnings
        repl_state.allow_system = allow_system
        engine = resolve_engine(args, None)
        repl_state.engine = engine
        if engine == 'vm':
            from src.vm.modules import VMSession
            repl_state.vm_session = VMSession(repl_state)
        set_state(repl_state)
        set_argv([])
        return initialize_repl(repl_state, engine)

    if check_only and input_file is None:
        raise powang_throw(powang_error_format('USAGE', None, '--check requires an input file', [
            "--check is only available for files, not for the REPL"
        ]))

    ## This invocation owns one state. Installing it before publishing argv
    ## makes both `args` and `PATHS` refer to that state, never to a previous
    ## run in the same process.
    run_state = fresh_state()
    run_state.allow_system = allow_system
    run_state.warnings_enabled = not no_warnings
    if not load_project_config(run_state, input_file):
        load_config(run_state, input_file)
    engine = resolve_engine(args, run_state.project_value)
    run_state.engine = engine
    load_package_config(run_state, input_file)
    require_packages_ready(run_state)
    run_state.paths['ABSOLUTE'] = INTERPRETER_PATH
    if input_file:
        run_state.paths['RELATIVE'] = Path(input_file).resolve()
    set_state(run_state)
    ## `--check` never executes the file, so the arguments are cleared instead
    ## of being published to the `args` module.
    set_argv([] if check_only else script_args)

    if input_file:
        content = get_file_content(input_file)
        if check_only:
            type_errors = check_source(content, str(Path(input_file).resolve()))
            run_state.emit_warnings()
            if type_errors:
                for type_error in type_errors:
                    print(str(type_error))
                return 1
            return 0
        if engine == 'native':
            if ast_output:
                raise powang_throw(powang_error_format(
                    'USAGE', None,
                    '--ast is not supported with --engine=native',
                ))
            from src.vm.native.compiler import NativeBuildError
            from src.vm.native.session import run_native_file
            try:
                result = run_native_file(
                    input_file, script_args, timeout=60.0,
                    warnings=not no_warnings,
                )
            except PowangError as error:
                print(str(error))
                return 1
            except NativeBuildError as error:
                print(f"native build error: {error}", file=_sys.stderr)
                return 1
            _sys.stdout.write(result.stdout)
            _sys.stderr.write(result.stderr)
            return result.returncode
        if engine == 'vm':
            if ast_output:
                import json
                from src.parser import Parser as _AstParser
                from src.simplify import simplify_program as _simplify
                from src.runtime import ast_to_json as _ast_to_json
                _parser = _AstParser(content, source_path=Path(input_file))
                _ast = _simplify(_parser.parse(), run_state.warn)
                with open(ast_output, 'w', encoding='utf-8') as _handle:
                    _handle.write(json.dumps(
                        _ast_to_json(_ast), indent=4, ensure_ascii=False,
                    ))
            from src.vm.interpreter import run_program
            run_program(
                content, path=input_file, check=not no_check,
                state=run_state,
            )
        else:
            interpret_program(content, ast_output, check=not no_check, state=run_state)
    return 0

def _project_engine(project_value) -> str | None:
    """Read the engine field from a loaded Project value."""
    if project_value is None:
        return None
    data = getattr(project_value, 'data', None)
    if not isinstance(data, dict):
        return None
    value = data.get('engine')
    if value is None or getattr(value, 'type', None) != 'str':
        return None
    return value.data


def resolve_engine(args: list[str], project_value=None) -> str:
    """Return the engine from the flag, the environment, the project or the default."""
    engine = None
    for argument in args:
        if argument.startswith('--engine='):
            engine = argument.split('=', 1)[1]
    if engine is None:
        engine = os.environ.get('POWANG_ENGINE') or None
    if engine is None:
        engine = _project_engine(project_value)
    if engine is None:
        engine = 'vm'
    engine = engine.strip().lower()
    if engine not in {'tree', 'vm', 'native'}:
        raise powang_throw(powang_error_format(
            'USAGE', None, 'Invalid engine', [
                f"engine: {engine}",
                "expected tree, vm or native",
            ]))
    return engine


def run_cli() -> int:
    import sys as _sys
    try:
        if hasattr(_sys.stdout, 'reconfigure'):
            _sys.stdout.reconfigure(encoding='utf-8')
            _sys.stderr.reconfigure(encoding='utf-8')
    except (OSError, ValueError):
        pass
    try:
        ## The language depth guard (900 evaluation levels) is only reachable
        ## if the Python stack can hold the corresponding interpreter frames.
        ## Python 3.12+ keeps Python frames off the C stack, so this is safe.
        _sys.setrecursionlimit(max(_sys.getrecursionlimit(), 4000))
    except (ValueError, RecursionError):
        pass
    debug: bool = any(arg == '--debug' for arg in argv[1:])
    exit_code: int = 0
    try:
        result = main(argv[1:])
        if result is not None:
            exit_code = int(result)
    except PowangError as err:
        ## Stable exit codes: 0 success, 1 language error, 2 usage error,
        ## 3 internal error, 130 interrupt.
        print(str(err))
        exit_code = 2 if err.kind == 'USAGE' else 1
    except AssertionError as ass:
        converted = powang_error_from_exception(ass)
        print(str(converted) if converted is not None else str(ass))
        exit_code = 1
    except KeyboardInterrupt:
        print()
        print(powang_error_format("KEYBOARD", "User input", "Keyboard interrupt"))
        exit_code = 130
    except FileNotFoundError as ferror:
        print(powang_error_format("INPUT", "File read", f"File not found: {ferror.filename}"))
        exit_code = 1
    except Exception as unexpected:
        if debug:
            traceback.print_exc()
        else:
            print(powang_error_format("INTERNAL", "unexpected", f"{type(unexpected).__name__}: {unexpected}"))
        exit_code = 3
    ## Join spawned tasks with a short deadline before tearing the run down.
    ## Unhandled task failures are reported to stderr by the pool; they never
    ## override the exit code of the main program.
    active_state = get_state()
    try:
        shutdown_state_tasks(active_state)
    except Exception:
        pass
    ## A script that called `listen` without `stop` still owns a server thread.
    ## Close every registered server so the process can exit cleanly.
    try:
        shutdown_state_servers(active_state)
    except Exception:
        pass
    ## Close only the streams owned by this process's active run state.
    active_state.close()
    return exit_code

def _entry() -> None:
    ## Console-script entry point declared in pyproject.toml.
    sys_exit(run_cli())

if __name__ == "__main__":
    sys_exit(run_cli())
