"""Module compilation, module scopes and the VM session.

The module loader evaluates imported modules with the active engine. When the
engine is ``vm`` this module compiles the module AST and executes the resulting
code object, then builds the export table with the same rules as
``src.runtime.evaluate_module_ast``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..powang_types import PowangModule, PowangNova, PowangAny
from ..error import powang_throw, powang_error_format
from ..scopestack import ScopeStack, ScopeType
from ..state import get_state
from ..lexer.token import ParserTokenType, DictRepr

from .frames import LocalStore
from .image import ProgramImage
from .interpreter import VM, VMRunOptions


@dataclass
class ModuleScope:
    """The persistent stores of one module body."""

    name: str
    path: str
    variables: LocalStore
    functions: dict[str, list] = field(default_factory=dict)
    types: dict[str, Any] = field(default_factory=dict)
    wildcards: dict[str, str] = field(default_factory=dict)
    module_value: Optional[PowangModule] = None
    global_names: Optional[set[str]] = None


def _module_scope_for(image: ProgramImage, module_index: int,
                      name: str, path: str) -> ModuleScope:
    module = image.module_info(module_index)
    code = image.code(module.code_index)
    return ModuleScope(
        name=name,
        path=path,
        variables=LocalStore(code.local_names),
        global_names=set(getattr(image, 'vm_globals', ())),
    )


def _ensure_global(store, name: str) -> None:
    if name not in store:
        store.add_slot(name)


def _bind_project(scope: ModuleScope, program_ast: Optional[list] = None) -> None:
    state = get_state()
    project = getattr(state, 'project_value', None)
    if project is None:
        return
    if program_ast is not None and _has_project_declaration(program_ast):
        return
    if 'project' not in scope.variables:
        scope.variables.add_slot('project')
    if scope.global_names is not None:
        scope.global_names.add('project')
    scope.variables['project'] = project


def _has_project_declaration(program_ast: Any) -> bool:
    if not isinstance(program_ast, (list, tuple)):
        return False
    for statement in program_ast:
        if not isinstance(statement, dict):
            continue
        statement_type = statement.get('type')
        value = statement.get('value')
        if statement_type not in {
            ParserTokenType.DECLARATION_TYPED_VAR,
            ParserTokenType.DECLARATION_INTERPRET,
        } or not isinstance(value, dict):
            continue
        if value.get('identifier', {}).get('value') == 'project':
            return True
    return False


def evaluate_program_image(image: ProgramImage, state, options: VMRunOptions) -> PowangAny:
    """Run the entry module of a compiled program image."""
    if options.verify and not options.trusted:
        from .verifier import verify_image
        verify_image(image)
    module = image.module_info(image.entry_module)
    scope = _module_scope_for(image, image.entry_module, module.name, module.path)
    scope.global_names = set(getattr(image, 'vm_globals', ()))
    _bind_project(scope, getattr(image, 'entry_ast', None))
    state.vm_globals = set(getattr(image, 'vm_globals', ()))
    vm = VM(state, image, options)
    vm.module_scopes[image.entry_module] = scope
    state.vm_instance = vm
    return vm.run()


def compile_module_image(program_ast: list[DictRepr], module_name: str,
                         module_path: Any, state) -> ProgramImage:
    """Compile and verify one module body without running it."""
    from .compiler import compile_ast
    from .verifier import verify_image

    image = compile_ast(
        program_ast,
        path=module_path,
        module_name=module_name,
        state=state,
    )
    verify_image(image)
    return image


def run_module_image_vm(image: ProgramImage, program_ast: list[DictRepr],
                        module_name: str, module_path: Any,
                        loader: Any) -> PowangModule:
    """Run a compiled module image and build its export table."""
    saved_scopes = ScopeStack.save_scopes()
    ScopeStack.reset_scopes()
    ScopeStack.push(ScopeType.GLOBAL)
    try:
        module = image.module_info(image.entry_module)
        scope = _module_scope_for(image, image.entry_module, module_name, str(module_path))
        scope.global_names = set(getattr(image, 'vm_globals', ()))
        _bind_project(scope, program_ast)
        state = get_state()
        vm = VM(state, image, VMRunOptions())
        vm.module_scopes[image.entry_module] = scope
        code = image.code(module.code_index)
        vm.run_module_code(code, scope)

        variables = scope.variables
        functions = scope.functions
        types = scope.types
        from ..runtime import _attach_module_closure
        _attach_module_closure(variables, functions, types)

        has_exports = bool(module.exports)
        members: dict[str, Any] = {}
        if has_exports:
            seen: dict[str, str] = {}
            for name, kind in module.exports:
                previous = seen.get(name)
                if previous is not None and not (previous == kind == 'function'):
                    raise powang_throw(powang_error_format(
                        'MODULE', f'module: {module_path}',
                        f"Duplicate export: {name}", [
                            f"already exported as {previous}",
                            f"then exported again as {kind}",
                        ]
                    ))
                seen[name] = kind
                if name in functions:
                    members[name] = list(functions[name])
                elif name in types:
                    members[name] = types[name]
                elif name in variables:
                    members[name] = variables[name]
                else:
                    raise powang_throw(powang_error_format(
                        'MODULE', f'module: {module_path}',
                        f"Exported name was not declared: {name}",
                    ))
        else:
            key = str(Path(module_path).resolve()) if hasattr(module_path, 'resolve') else str(module_path)
            if key not in loader.warned:
                loader.warned.add(key)
                import sys
                print(
                    f"[MODULE WARNING] module '{module_name}' declares no exports; "
                    "exporting all top-level names",
                    file=sys.stderr,
                )
            for name, value in variables.items():
                members[name] = value
            for name, overloads in functions.items():
                members[name] = list(overloads)
            for name, object_type in types.items():
                members[name] = object_type

        module_value = PowangModule(module_name, members)
        module_value.legacy = not has_exports
        module_value.vm_scope = scope
        scope.module_value = module_value
        return module_value
    finally:
        ScopeStack.pop()
        ScopeStack.restore_scopes(saved_scopes)


def evaluate_module_ast_vm(program_ast: list[DictRepr], module_name: str,
                           module_path: Any, loader: Any) -> PowangModule:
    """Compile and run one imported module on the VM."""
    image = compile_module_image(program_ast, module_name, module_path, get_state())
    return run_module_image_vm(image, program_ast, module_name, module_path, loader)


COMPILER_VERSION = "0.22.0"


class BytecodeCache:
    """Optional on disk cache for entry program images.

    The cache is off by default. The key includes the source hash, the resolved
    path, the language version and the compiler version. A corrupted entry is
    deleted and recompiled.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, source: str, path: str | Path) -> str:
        return self.key_for_sources([(str(path), source)], path)

    def key_for_sources(self, sources: list[tuple[str, str]],
                        path: str | Path,
                        dependencies: list[tuple[str, str]] | None = None) -> str:
        import hashlib
        digest = hashlib.sha256()
        for source_path, content in sorted(sources):
            digest.update(str(Path(source_path).resolve()).encode("utf-8"))
            digest.update(b"\0")
            digest.update(content.encode("utf-8"))
            digest.update(b"\0")
        digest.update(str(Path(path).resolve()).encode("utf-8"))
        digest.update(b"\0")
        for dependency_path, content in sorted(dependencies or []):
            digest.update(str(Path(dependency_path).resolve()).encode("utf-8"))
            digest.update(b"\0")
            digest.update(content.encode("utf-8"))
            digest.update(b"\0")
        digest.update(b"language=" + str(getattr(ProgramImage, "language_version", "0.22.0")).encode("utf-8"))
        digest.update(b"\0")
        digest.update(b"compiler=" + COMPILER_VERSION.encode("utf-8"))
        return digest.hexdigest()

    def load(self, key: str) -> Optional[ProgramImage]:
        path = self.root / f"{key}.pwb"
        if not path.exists():
            return None
        try:
            return ProgramImage.from_bytes(path.read_bytes())
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            return None

    def store(self, key: str, image: ProgramImage) -> None:
        path = self.root / f"{key}.pwb"
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_bytes(image.to_bytes())
            temporary.replace(path)
        except OSError:
            try:
                temporary.unlink()
            except OSError:
                pass


class VMSession:
    """Persistent VM state for the REPL.

    Each cell compiles into a module fragment. Declarations at the cell top
    level are emitted as global operations, so they survive in the session
    store. A failed cell restores the store to its previous shape.
    """

    def __init__(self, state, name: str = "<repl>"):
        self.state = state
        self.scope = ModuleScope(
            name=name,
            path=name,
            variables=LocalStore([]),
        )
        self.image = None
        self.options = VMRunOptions()

    def _snapshot(self) -> dict[str, PowangAny]:
        return dict(self.scope.variables.items())

    def _restore(self, snapshot: dict[str, PowangAny]) -> None:
        names = list(snapshot.keys())
        self.scope.variables = LocalStore(names)
        for name, value in snapshot.items():
            self.scope.variables[name] = value
        self.scope.functions = {}
        self.scope.types = {}

    def run_cell(self, source: str) -> PowangAny:
        from .compiler import compile_source
        snapshot = self._snapshot()
        functions_snapshot = {
            name: list(overloads) for name, overloads in self.scope.functions.items()
        }
        types_snapshot = dict(self.scope.types)
        saved = ScopeStack.save_scopes()
        ScopeStack.reset_scopes()
        ScopeStack.push(ScopeType.GLOBAL)
        ScopeStack.variables[-1] = self.scope.variables
        ScopeStack.functions[-1] = self.scope.functions
        ScopeStack.ObjectTypes[-1] = self.scope.types
        ScopeStack.wildcard_sources[-1] = self.scope.wildcards
        try:
            image = compile_source(
                source, path=Path("<repl>"), module_name="<repl>",
                check=False, state=self.state, repl=True,
            )
            module = image.module_info(image.entry_module)
            code = image.code(module.code_index)
            self.image = image
            vm = VM(self.state, image, self.options)
            vm.module_scopes[image.entry_module] = self.scope
            vm._module_stack.append(self.scope)
            try:
                return vm.run_code(
                    code, [], is_function=False,
                    module_scope=self.scope,
                    functions=self.scope.functions,
                    types=self.scope.types,
                    wildcards=self.scope.wildcards,
                )
            finally:
                vm._module_stack.pop()
        except Exception:
            self._restore(snapshot)
            self.scope.functions = functions_snapshot
            self.scope.types = types_snapshot
            raise
        finally:
            ScopeStack.restore_scopes(saved)
