# Architecture Specification: Safe FFI for powang

## Overview

This specification defines an opaque handle based FFI for powang. It lets powang programs use external Python modules such as pygame without modeling their classes as powang types. Configuration replaces the hard coded extern allowlist, and a generic host callback module keeps the LSP simple.

## Architecture Style

Layered with a small host bridge. The runtime keeps ownership of value conversion. Configuration and state isolation remain per InterpreterState.

## Component Architecture

### PowangHandle type
- Responsibility: represent an opaque reference to a Python object.
- Dependencies: InterpreterState handle registry.
- Exposes: type name `handle`, integer handle id, printable form.

### Handle registry
- Responsibility: map handle ids to Python objects for one run.
- Dependencies: InterpreterState.
- Exposes: register_handle, resolve_handle, clear on close.

### Value conversion bridge
- Responsibility: convert between powang values and Python values.
- Dependencies: PowangHandle, handle registry.
- Exposes: getPowangFromPython, getPythonFromPowang.

### Configuration loader
- Responsibility: read project config and environment variables.
- Dependencies: powang.toml, environment.
- Exposes: allowed extern modules, module search paths, host callbacks.

### Module loader
- Responsibility: resolve and cache powang modules.
- Dependencies: InterpreterState paths.
- Exposes: resolve, load, load_path.

### Host callback module
- Responsibility: call registered Python functions by name.
- Dependencies: host callback registry, value conversion bridge.
- Exposes: host.call(name, arguments).

### Extern resolver
- Responsibility: bind extern fun signatures to Python callables.
- Dependencies: allowed extern modules, module object lookup.
- Exposes: extern fun and extern type declarations.

### LSP index
- Responsibility: provide completion and hover for powang types and extern signatures.
- Dependencies: synced powang source.
- Exposes: type names and function signatures.

## Data Flow

Configuration is loaded at startup and stored on InterpreterState. The extern resolver checks the allowed module set before binding. Module loading checks configured search paths. When powang calls an extern function, callExternalFunction converts powang arguments to Python values. Handle arguments unwrap to their Python objects. The Python result is converted back. Unknown Python objects become handles registered in the current state. The host callback module performs the same conversion for calls by name. Task cloning rejects handle values, and handle registries are not shared across states.

## Key Decisions

### ADR: Opaque handles for Python objects
- Context: Modeling pygame classes as powang types is complex and fragile.
- Decision: Introduce PowangHandle as an opaque type with an integer id and a per state registry.
- Consequences: External objects stay usable without type modeling. Handles cannot be inspected as powang objects.
- Status: proposed

### ADR: Project configuration and environment variables
- Context: The extern allowlist is hard coded and not project specific.
- Decision: Load powang.toml and environment variables into InterpreterState. Use POWANG_CONFIG, POWANG_EXTERN_MODULES, and POWANG_MODULE_PATH.
- Consequences: Projects can declare allowed modules and import paths. Misconfiguration can allow unsafe modules, so defaults stay minimal.
- Status: proposed

### ADR: Generic host callback module
- Context: Dynamic Python calls need a simple and stable LSP surface.
- Decision: Provide host.call(name, arguments) with a variadic signature returning any.
- Consequences: The LSP needs only one signature. Call resolution happens at runtime against a configured registry.
- Status: proposed

### ADR: Handle conversion rules
- Context: Extern functions must pass opaque objects safely.
- Decision: getPowangFromPython wraps unknown objects as handles. getPythonFromPowang unwraps handles. Primitive, list, and map conversion stays unchanged.
- Consequences: Existing behavior for unknown objects changes from nova to handle. Tests that expect nova need review.
- Status: proposed

### ADR: State isolation for handles
- Context: Python objects can leak across tasks and states.
- Decision: Treat handles like task and file handles. They use reference semantics, are not deep copied, and task spawning rejects globals that hold handles. Registries are cleared on state close.
- Consequences: Tasks cannot share Python objects. Handles become invalid after their state closes.
- Status: proposed

### ADR: LSP representation
- Context: LSP completion and hover are regex and index based.
- Decision: Add handle as a built in type name and keep extern signatures in the existing index. Do not add per module class signatures.
- Consequences: LSP changes stay small. Dynamic host calls show a generic signature only.
- Status: proposed

## Interfaces

- PowangHandle type name: handle
- State fields: handles, next_handle_id, allowed_extern_modules, host_callbacks, module_search_paths
- Config file: powang.toml with sections extern.modules, paths.modules, host.callbacks
- Environment variables: POWANG_CONFIG, POWANG_EXTERN_MODULES, POWANG_MODULE_PATH
- Helper functions: register_handle(obj), resolve_handle(handle)
- Host module function: host.call(name, arguments) returns any
- Extern declaration: extern fun name(parameters) -> type >> "module.attr"

## Risks

- Python objects may outlive a state if a host callback captures them.
- Handle registries can grow if handles are not released.
- Allowing arbitrary modules reduces safety, so configuration defaults must stay strict.
- LSP type lists must be updated to include handle.
- Changing unknown object conversion from nova to handle may affect existing programs.

## Recommended Implementation Order

1. Add PowangHandle to powang_types and register it in PowangTypeMap.
2. Add handle registry fields to InterpreterState and clear them on close.
3. Implement register_handle and resolve_handle in the runtime.
4. Update getPowangFromPython and getPythonFromPowang for handles.
5. Update copy_for_task and clone_for_task for handle isolation.
6. Add configuration loading and environment variable support.
7. Update the extern resolver to use state allowed modules.
8. Update ModuleLoader to use configured search paths.
9. Implement the host callback module.
10. Update the LSP type index for handle.
11. Add tests for handle conversion, config, host calls, and isolation.