"""Module loading, caching, and cycle detection.

Modules are real scoped units now. The loader owns:

* resolution of ``use name`` against the interpreter's ``modules/`` directory
* resolution of ``use "./path.po"`` against the importing file's directory
* a parse/evaluate cache keyed by resolved absolute path
* cycle detection across the import chain

Evaluation itself stays in :mod:`src.runtime`; the import is lazy to avoid a
circular import at module load time.
"""

from pathlib import Path
from typing import Any, Optional

from .error import (
    PowangError,
    powang_error_format,
    powang_error_from_exception,
    powang_throw,
)
from .parser import Parser, ParserTokenType
from .powang_types import PowangModule
from .state import get_state


def _read_source(path: Path) -> str:
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        if not content.endswith('\n'):
            content = content + '\n'
        return content


class ModuleLoader:
    """Module cache and import chain for one interpreter state.

    Module identity is per state: the same file executes once inside a state
    and once more in a second state. Construction never reads process globals;
    it resolves paths from the owning state at call time, so a loader created
    before the CLI publishes the script path still resolves correctly.
    """

    def __init__(self, state=None, interpreter_path: Path | str | None = None):
        if state is not None and not hasattr(state, 'paths'):
            ## Backwards compatibility: the old constructor took the
            ## interpreter path as its first positional argument.
            interpreter_path = state
            state = None
        if state is None:
            state = get_state()
        self.state = state
        self._interpreter_path: Path | None = (
            Path(interpreter_path).resolve()
            if interpreter_path is not None
            else None
        )
        self.cache: dict[str, PowangModule] = {}
        self.loading: list[str] = []
        self.base_stack: list[Path] = []
        self.warned: set[str] = set()

    @property
    def interpreter_path(self) -> Path:
        if self._interpreter_path is not None:
            return self._interpreter_path
        absolute = self.state.paths.get('ABSOLUTE')
        if absolute is None:
            return Path(__file__).resolve().parents[1] / 'powang.py'
        return Path(absolute).resolve()

    @interpreter_path.setter
    def interpreter_path(self, value: Path | str) -> None:
        self._interpreter_path = Path(value).resolve()

    # ------------------------------------------------------------- resolution
    def default_base(self) -> Path:
        relative = self.state.paths.get('RELATIVE')
        if relative is not None:
            return Path(relative).resolve()
        return self.interpreter_path

    def resolve(self, kind: str, name: str, base: Path | None = None) -> Path:
        if kind == 'name':
            for base_path in self.state.module_search_paths:
                candidate = base_path / 'modules' / name
                if candidate.exists():
                    return candidate.resolve()
            candidate = self.interpreter_path.parent / 'modules' / name
        else:
            importing = base if base is not None else self.default_base()
            candidate = importing.parent / Path(name)
        return candidate.resolve()

    def load(self, use_value: dict[str, Any]) -> PowangModule:
        kind = use_value.get('kind', 'name')
        name = use_value.get('name', '')
        base_value = use_value.get('base')
        base: Optional[Path] = None
        if base_value:
            base = Path(base_value).resolve()
        elif self.base_stack:
            base = self.base_stack[-1]
        path = self.resolve(kind, name, base)
        return self.load_path(path)

    def load_path(self, path: Path) -> PowangModule:
        key = str(path.resolve())
        if key in self.cache:
            return self.cache[key]
        if key in self.loading:
            start = self.loading.index(key)
            chain = self.loading[start:] + [key]
            raise self._make_error(
                path,
                'Cyclic module import',
                chain,
            )

        self.loading.append(key)
        try:
            module = self._evaluate(path)
            self.cache[key] = module
            return module
        finally:
            self.loading.pop()

    # ------------------------------------------------------------- evaluation
    def _evaluate(self, path: Path) -> PowangModule:
        if not path.exists():
            raise self._make_error(
                path,
                f"Can't find the module: {path}",
            )

        if path.is_dir():
            sources = sorted(
                (entry for entry in path.iterdir() if entry.is_file()),
                key=lambda entry: entry.name,
            )
            module_name = path.name
        else:
            sources = [path]
            module_name = path.stem

        if not sources:
            raise self._make_error(path, f"Module directory is empty: {path}")

        ast: list[Any] = []
        for source_path in sources:
            try:
                content = _read_source(source_path)
            except OSError as file_error:
                raise self._make_error(
                    source_path,
                    f"Can't read module file: {source_path}",
                    [str(file_error)],
                ) from None
            parser = Parser(content, source_path=source_path)
            try:
                ast.extend(parser.parse())
            except AssertionError as parse_error:
                converted = powang_error_from_exception(parse_error)
                if converted is None:
                    raise
                raise self._wrap(
                    source_path,
                    converted,
                    line=parser.tokenizer.row + 1,
                ) from None

        closure_base = sources[0]
        self.base_stack.append(closure_base)
        try:
            from .runtime import evaluate_module_ast
            try:
                return evaluate_module_ast(ast, module_name, path, self)
            except AssertionError as evaluation_error:
                converted = powang_error_from_exception(evaluation_error)
                if converted is None:
                    raise
                raise self._wrap(path, converted) from None
        finally:
            self.base_stack.pop()

    # ----------------------------------------------------------------- errors
    @staticmethod
    def _make_error(path: Path, message: str, details: Optional[list[str]] = None) -> PowangError:
        error = powang_error_format(
            'MODULE',
            f'module: {path}',
            message,
            details if details is not None else [],
        )
        setattr(error, '_module_error', True)
        return error

    @classmethod
    def _wrap(cls, path: Path, error: PowangError, line: Optional[int] = None) -> PowangError:
        if getattr(error, '_module_error', False):
            return error
        details: list[str] = []
        if line is not None:
            details.append(f"ln: {line} | {str(error)}")
        else:
            details.append(str(error))
        wrapped = powang_error_format(
            'MODULE',
            f'module: {path}',
            'Module failed to load',
            details,
        )
        wrapped.cause = error
        setattr(wrapped, '_module_error', True)
        return wrapped


def find_entry_module(root: Path | str) -> Path:
    root = Path(root).resolve()
    candidates: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix != '.po':
            continue
        try:
            content = _read_source(path)
            program_ast = Parser(content, source_path=path).parse()
        except Exception:
            continue
        if not program_ast or not isinstance(program_ast[0], dict):
            continue
        first = program_ast[0]
        if first.get('type') != ParserTokenType.MODULE_DECLARATION:
            continue
        value = first.get('value')
        if not isinstance(value, dict):
            continue
        if value.get('identifier', {}).get('value') != 'main':
            continue
        candidates.append(path)
    if len(candidates) != 1:
        raise powang_throw(powang_error_format(
            'USAGE', 'run', 'expected exactly one module named main in the project directory',
            [f"found {len(candidates)}"],
        ))
    return candidates[0]


def get_loader() -> ModuleLoader:
    """Return the active state's module loader, creating it lazily."""
    state = get_state()
    loader = state.module_loader
    if not isinstance(loader, ModuleLoader):
        loader = ModuleLoader(state)
        state.module_loader = loader
    return loader


## Compatibility alias for the pre-W23 call site. It carries no state of its
## own: every call resolves through the active InterpreterState.
def get_module_loader() -> ModuleLoader:
    return get_loader()


def reset_module_loader() -> None:
    """Drop only the active state's loader cache (used by fresh runs)."""
    get_state().module_loader = None
