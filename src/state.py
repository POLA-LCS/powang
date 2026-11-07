"""Per-execution interpreter state.

The interpreter used to keep its lexical scopes in class-level lists on
``ScopeStack``. Every execution in one Python process therefore shared a single
scope stack, so a second program (or a second thread) could see and corrupt the
first one's variables, functions and return slot.

The lexical data now lives on a ``ScopeState`` instance owned by an
``InterpreterState``. A ``contextvars.ContextVar`` selects the active state for
the current execution context. Context variables are isolated per thread and
per copied context, which is exactly the granularity needed here: each thread
that starts a run gets its own scopes.

``src.scopestack.ScopeStack`` remains as a thin class-level proxy over the
active state so existing call sites keep working unchanged.
"""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Optional

from .powang_types import *
from .scopestack import ScopeType


@dataclass(frozen=True)
class WarningRecord:
    """A non-fatal diagnostic produced by the parser, checker or runtime."""

    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_column: Optional[int] = None
    code: str = 'PW200'


class ScopeState:
    """The lexical stacks for one execution context.

    This is the old ``ScopeStack`` implementation turned into an instance. The
    method names and signatures are intentionally unchanged so the rest of the
    interpreter does not have to care where the stacks live.
    """

    def __init__(self):
        self.return_value: PowangAny | None = None
        self.important: list[ScopeType | None] = [ScopeType.GLOBAL]
        self.method_call_stack: list[PowangObjectType] = []
        self.static_method_stack: list[str] = []

        self.variables: list[dict[str, PowangAny]] = [{}]
        self.functions: list[dict[str, list[PowangFunction]]] = [{}]
        self.ObjectTypes: list[dict[str, PowangObjectType]] = [{}]
        self.wildcard_sources: list[dict[str, str]] = [{}]

    def get_variable(self, name: str) -> Optional[PowangAny]:
        for scope in self.variables[::-1]:
            if (value := scope.get(name)) is not None:
                return value
        return None

    def find_variable_slot(self, name: str) -> tuple[dict[str, PowangAny], PowangAny] | None:
        """Return the scope dictionary and live value holding ``name``."""
        for scope in self.variables[::-1]:
            if name in scope:
                return scope, scope[name]
        return None

    def get_functions(self, name: str) -> list[PowangFunction] | None:
        for scope in self.functions[::-1]:
            if (func := scope.get(name)) is not None:
                return func
        return None

    def get_ObjectType(self, name: str) -> PowangObjectType | None:
        for scope in self.ObjectTypes[::-1]:
            if (type := scope.get(name)) is not None:
                return type
        return None

    def get_wildcard_source(self, name: str) -> str | None:
        for scope in self.wildcard_sources[::-1]:
            if (source := scope.get(name)) is not None:
                return source
        return None

    def new_wildcard_source(self, name: str, source: str):
        self.wildcard_sources[-1][name] = source
        return source

    def get_existingObjectType(self, name: str) -> PowangObjectType:
        value = self.get_ObjectType(name)
        if value is None:
            raise powang_throw(powang_error_identifier_not_found("object type", name, [
                "user type doesn't exists"
            ]))
        return PowangCopyConstructObjectType(value)

    def new_variable(self, name: str, value: PowangAny):
        self.variables[-1][name] = value
        return value

    def new_function(self, name: str, value: PowangFunction):
        self.functions[-1].setdefault(name, []).append(value)
        return value

    def new_ObjectType(self, name: str, value: PowangObjectType):
        self.ObjectTypes[-1][name] = value
        return value

    def current_scope_type(self) -> ScopeType:
        for scope_type in self.important[::-1]:
            if scope_type is not None:
                return scope_type
        return ScopeType.GLOBAL

    def pop(self):
        self.important.pop()
        self.variables.pop()
        self.functions.pop()
        self.ObjectTypes.pop()
        self.wildcard_sources.pop()
        return True

    def push(self, scope_type: ScopeType | None = None):
        self.important.append(scope_type)
        self.variables.append({})
        self.functions.append({})
        self.ObjectTypes.append({})
        self.wildcard_sources.append({})
        return True

    def push_captured(self, variables: dict[str, PowangAny],
                      functions: dict[str, list[PowangFunction]],
                      object_types: dict[str, PowangObjectType]):
        """Push an existing scope as a read-through lexical closure."""
        self.important.append(None)
        self.variables.append(variables)
        self.functions.append(functions)
        self.ObjectTypes.append(object_types)
        self.wildcard_sources.append({})
        return True

    def save_scopes(self):
        return (
            self.important,
            self.variables,
            self.functions,
            self.ObjectTypes,
            self.wildcard_sources,
        )

    def reset_scopes(self):
        """Start a completely isolated lexical context.

        Module bodies and module functions must not resolve names from the
        importer or the caller. The caller saves the previous stacks and
        restores them afterwards.
        """
        self.important = []
        self.variables = []
        self.functions = []
        self.ObjectTypes = []
        self.wildcard_sources = []
        return True

    def restore_scopes(self, state):
        (
            self.important,
            self.variables,
            self.functions,
            self.ObjectTypes,
            self.wildcard_sources,
        ) = state
        return True


def copy_for_task(value: PowangAny, _memo: Optional[dict[int, PowangAny]] = None) -> PowangAny:
    """Deep-copy a value for task isolation.

    A reference is snapshotted by copying the value it currently points at, so
    a spawned task cannot mutate the parent through ``&x``. The memo keeps
    shared references and cycles intact within one task clone.
    """
    if _memo is None:
        _memo = {}
    if value.type == PowangReference.type:
        raise powang_throw(powang_error_format(
            'TASK',
            'spawn',
            'References cannot be sent to a task',
            [
                "a reference only lives for the duration of one call",
                "pass a value or a copy instead",
            ],
        ))
    return PowangCopyConstruct(value, _memo)


class InterpreterState:
    """One execution context: every piece of run state lives here.

    The lexical stacks already moved here in W22. The remaining interpreter
    tables moved with W23/W24 so two states in one process can never observe
    or corrupt each other's files, modules, externs, type aliases, paths or
    script arguments.
    """

    def __init__(self, scope: ScopeState | None = None):
        self.scope: ScopeState = scope if scope is not None else ScopeState()

        ## Open file handles owned by this run, keyed by the Powang filename.
        self.file_streams: dict[str, IO] = {}

        ## The per-state module loader. Built lazily by
        ## ``src.module_loader.get_loader`` so it can read this state's paths.
        self.module_loader: object | None = None

        ## Parser/runtime type tables. They are per run, not per process.
        self.type_alias: dict[str, DictRepr] = {}
        self.user_types: set[str] = set()

        ## Extern bindings declared by this run. The module allowlist stays
        ## process-wide because it is configuration, not run state.
        self.external_functions: dict[str, tuple[PowangFunction, object]] = {}
        self.external_types: dict[str, tuple[PowangObjectType, object]] = {}

        ## Script resolution paths and the arguments after the input file.
        self.paths: dict[str, Path] = {}
        self.script_argv: list[str] = []

        ## Task infrastructure. A task clone shares the parent's pool so the
        ## outermost run can join every task it indirectly spawned.
        self.task_pool: object | None = None

        ## In-process HTTP servers owned by this state (ADR-0001 W28). The
        ## registry is per state so two runs never stop each other's servers.
        ## Ids are allocated per state and start at 1.
        self.http_servers: dict[int, object] = {}
        self.http_next_server_id: int = 1

        ## Opaque Python object handles.
        self.handles: dict[int, Any] = {}
        self.next_handle_id: int = 1

        ## Extern configuration.
        self.allowed_extern_modules: set[str] = set()
        self.module_search_paths: list[Path] = []
        self.extern_module_cache: dict[str, Any] = {}
        self.host_callbacks: dict[str, Any] = {}
        self.project_value: Optional[PowangProject] = None
        self.log_level: str = os.environ.get("POWANG_LOG_LEVEL", "info").lower()
        self.allow_system: bool = os.environ.get("POWANG_ALLOW_SYSTEM") == "1"

        ## Non-fatal diagnostics collected during one run. `--no-warnings`
        ## toggles printing without changing what is collected, so the LSP can
        ## still publish them.
        self.warnings: list[WarningRecord] = []
        self.warnings_enabled: bool = True

    def register_handle(self, obj: Any) -> int:
        handle_id = self.next_handle_id
        self.next_handle_id += 1
        self.handles[handle_id] = obj
        return handle_id

    def resolve_handle(self, handle_id: int) -> Any:
        if handle_id not in self.handles:
            raise powang_throw(powang_error_format(
                'HANDLE', None, 'Unknown handle', [
                    f"handle {handle_id} does not exist in this state",
                ],
            ))
        return self.handles[handle_id]

    def close(self) -> None:
        streams = self.file_streams
        while streams:
            _, stream = streams.popitem()
            try:
                stream.close()
            except OSError:
                pass
        self.handles.clear()

    def warn(self, message: str, line: Optional[int] = None,
             column: Optional[int] = None, end_column: Optional[int] = None,
             code: str = 'PW200') -> None:
        """Record a warning once per run, deduplicated by text and position."""
        record = WarningRecord(message, line, column, end_column, code)
        if record not in self.warnings:
            self.warnings.append(record)

    def take_warnings(self) -> list[WarningRecord]:
        records = list(self.warnings)
        self.warnings.clear()
        return records

    def emit_warnings(self, stream=None) -> None:
        """Print collected warnings to stderr unless warnings are disabled."""
        import sys
        records = self.take_warnings()
        if not self.warnings_enabled:
            return
        target = stream if stream is not None else sys.stderr
        for record in records:
            print(f"[WARNING] {record.message}", file=target)

    def clone_for_task(self) -> 'InterpreterState':
        """Build the shared-nothing state a spawned task runs in.

        Immutable configuration (native tables, extern bindings, paths, script
        arguments, function definitions and user-type templates) is copied
        shallowly. Mutable *global variable bindings* are deep-copied so a
        task can never observe or mutate the parent's values. Local scopes,
        file streams and the module loader start fresh: a task loads modules
        on its own and owns the files it opens.

        ``PowangTask`` and ``PowangFileStream`` global bindings cannot be
        copied safely, so spawning while one exists raises a catchable task
        error that names the offending variable.
        """
        clone = InterpreterState()

        source_scope = self.scope
        clone_scope = clone.scope

        global_variables = source_scope.variables[0] if source_scope.variables else {}
        task_memo: dict[int, PowangAny] = {}
        for name, value in global_variables.items():
            if value.type in {PowangTask.type, PowangFileStream.type, PowangHandle.type}:
                raise powang_throw(powang_error_format(
                    'TASK',
                    'spawn',
                    f"cannot spawn a task: global '{name}' is a {value.type} value",
                    [
                        f"{value.type} values cannot be shared with a task",
                        "make the binding local or remove it before spawning",
                    ],
                ))
            clone_scope.variables[0][name] = copy_for_task(value, task_memo)

        ## Function overload sets and user-type templates are treated as
        ## immutable definitions, so sharing them avoids copying bytecode.
        if source_scope.functions:
            clone_scope.functions[0] = dict(source_scope.functions[0])
        if source_scope.ObjectTypes:
            clone_scope.ObjectTypes[0] = dict(source_scope.ObjectTypes[0])
        if source_scope.wildcard_sources:
            clone_scope.wildcard_sources[0] = dict(source_scope.wildcard_sources[0])
        if source_scope.important:
            clone_scope.important[0] = source_scope.important[0]

        ## Fresh local stacks: the clone starts at global scope.
        clone_scope.return_value = None
        clone_scope.method_call_stack = []
        clone_scope.static_method_stack = []

        clone.file_streams = {}
        clone.module_loader = None
        clone.type_alias = dict(self.type_alias)
        clone.user_types = set(self.user_types)
        clone.external_functions = dict(self.external_functions)
        clone.external_types = dict(self.external_types)
        clone.paths = dict(self.paths)
        clone.script_argv = list(self.script_argv)
        clone.task_pool = self.task_pool
        clone.log_level = self.log_level
        clone.allow_system = self.allow_system
        clone.warnings_enabled = self.warnings_enabled
        return clone

    def close(self) -> None:
        """Close only the file streams owned by this state."""
        streams = self.file_streams
        while streams:
            _, stream = streams.popitem()
            try:
                stream.close()
            except OSError:
                pass


## The active state is selected per execution context (thread / copied
## context), never process-wide. ``None`` means "no run owns this context yet";
## ``get_state`` lazily creates one so standalone code keeps working.
CURRENT_STATE: ContextVar[InterpreterState | None] = ContextVar(
    "powang_current_state", default=None
)


def new_state() -> InterpreterState:
    """Create a state without installing it."""
    return InterpreterState()


def fresh_state() -> InterpreterState:
    """Create a new state, ready to be installed with ``set_state``."""
    return new_state()


def get_state() -> InterpreterState:
    """Return the active state, creating one when the context has none."""
    state = CURRENT_STATE.get()
    if state is None:
        state = new_state()
        CURRENT_STATE.set(state)
    return state


def set_state(state: InterpreterState) -> Token:
    """Install ``state`` in this context and return the reset token."""
    return CURRENT_STATE.set(state)


def reset_state(token: Token) -> None:
    """Restore the state that was active before ``set_state``."""
    CURRENT_STATE.reset(token)
