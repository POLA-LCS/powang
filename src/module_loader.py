"""Module loading, caching, and cycle detection.

Modules are real scoped units now. The loader owns:

* resolution of ``use name`` against the interpreter's ``modules/`` directory
* resolution of ``use "./path.po"`` against the importing file's directory
* a parse/evaluate cache keyed by resolved absolute path
* cycle detection across the import chain

Evaluation itself stays in :mod:`src.runtime`; the import is lazy to avoid a
circular import at module load time.
"""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ModuleSources:
    """One module's name and ordered source texts, without evaluation."""

    name: str
    path: Path
    sources: tuple[tuple[Path, str], ...]


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

    def resolve(
        self,
        kind: str,
        name: str,
        base: Path | None = None,
        level: int = 0,
    ) -> Path:
        if kind == 'name':
            ## Bare names are language built-ins. They always resolve from the
            ## interpreter's modules directory, never from the input file.
            modules_root = self.interpreter_path.parent / 'modules'
            candidate = modules_root / name
            if candidate.exists():
                return candidate.resolve()
            file_candidate = modules_root / f'{name}.po'
            if file_candidate.is_file():
                return file_candidate.resolve()

            ## Explicitly configured roots still support the package manager
            ## and legacy project path configuration.
            for base_path in self.state.module_search_paths:
                configured_root = base_path / 'modules'
                configured = configured_root / name
                if configured.exists():
                    return configured.resolve()
                configured_file = configured_root / f'{name}.po'
                if configured_file.is_file():
                    return configured_file.resolve()
            return candidate.resolve()

        importing = base if base is not None else self.default_base()
        if kind == 'relative':
            root = importing.parent if importing.is_file() or importing.suffix else importing
            for _ in range(max(0, level - 1)):
                root = root.parent
            candidate = root / name
            if candidate.exists():
                return candidate.resolve()
            file_candidate = root / f'{name}.po'
            if file_candidate.is_file():
                return file_candidate.resolve()
            return candidate.resolve()

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
        level = use_value.get('level', 0)
        if not isinstance(level, int):
            level = 0
        path = self.resolve(kind, name, base, level)
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
    def read_sources(self, path: Path) -> ModuleSources:
        """Return one module's ordered source texts without evaluating it.

        Resolution, directory ordering and the read error wrapping match
        ``_evaluate`` exactly. Parsing and compilation are the caller's job.
        """
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

        collected: list[tuple[Path, str]] = []
        for source_path in sources:
            try:
                content = _read_source(source_path)
            except OSError as file_error:
                raise self._make_error(
                    source_path,
                    f"Can't read module file: {source_path}",
                    [str(file_error)],
                ) from None
            collected.append((source_path, content))
        return ModuleSources(
            name=module_name,
            path=path,
            sources=tuple(collected),
        )

    def _evaluate(self, path: Path) -> PowangModule:
        module_sources = self.read_sources(path)
        sources = [source_path for source_path, _ in module_sources.sources]
        module_name = module_sources.name

        ast: list[Any] = []
        source_texts: list[tuple[str, str]] = []
        for source_path, content in module_sources.sources:
            source_texts.append((str(source_path), content))
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
            engine = getattr(self.state, 'engine', 'tree')
            try:
                if engine == 'vm':
                    from .vm.modules import (
                        compile_module_image,
                        evaluate_module_ast_vm,
                        run_module_image_vm,
                    )
                    cache = getattr(self.state, 'bytecode_cache', None)
                    if cache is None:
                        return evaluate_module_ast_vm(ast, module_name, path, self)
                    dependencies = self._dependency_sources(ast, closure_base)
                    key = cache.key_for_sources(source_texts, path, dependencies)
                    image = cache.load(key)
                    if image is not None:
                        from .vm.compiler import collect_program_globals
                        image.entry_ast = ast
                        image.vm_globals = collect_program_globals(ast)
                        return run_module_image_vm(
                            image, ast, module_name, path, self,
                        )
                    image = compile_module_image(
                        ast, module_name, path, self.state,
                    )
                    cache.store(key, image)
                    return run_module_image_vm(
                        image, ast, module_name, path, self,
                    )
                return evaluate_module_ast(ast, module_name, path, self)
            except AssertionError as evaluation_error:
                converted = powang_error_from_exception(evaluation_error)
                if converted is None:
                    raise
                raise self._wrap(path, converted) from None
        finally:
            self.base_stack.pop()

    def _dependency_sources(self, ast: list[Any], base: Path,
                            visited: set[str] | None = None,
                            depth: int = 0) -> list[tuple[str, str]]:
        """Collect source texts of imported modules for the cache key.

        The walk is recursive so a change in a transitive dependency
        invalidates the cached parent module. Import cycles are detected by the
        loader itself, and the visited set stops this key walk early.
        """
        if visited is None:
            visited = set()
        if depth > 32:
            return []
        dependencies: list[tuple[str, str]] = []
        for statement in ast:
            if not isinstance(statement, dict):
                continue
            if statement.get('type') != ParserTokenType.USE_EXPRESSION:
                continue
            use = statement.get('value')
            if not isinstance(use, dict):
                continue
            try:
                dependency = self.resolve(
                    use.get('kind', 'name'),
                    use.get('name', ''),
                    base,
                    use.get('level', 0),
                )
            except Exception:
                continue
            try:
                if not dependency.is_file():
                    continue
                resolved = str(dependency.resolve())
                if resolved in visited:
                    continue
                visited.add(resolved)
                content = _read_source(dependency)
            except OSError:
                continue
            dependencies.append((resolved, content))
            try:
                dependency_ast = Parser(
                    content, source_path=dependency,
                ).parse()
            except Exception:
                continue
            dependencies.extend(self._dependency_sources(
                dependency_ast, dependency, visited, depth + 1,
            ))
        return dependencies

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
