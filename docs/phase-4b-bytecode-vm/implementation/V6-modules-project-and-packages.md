# V6: Modules, Project and Packages

Purpose: deliver module declarations, built in, relative and path imports, aliases, wildcard imports, exports, cross module types and traits, project configuration, the implicit project binding, package module resolution, extern functions and module cycle errors on the bytecode VM.

## Objective

At the end of V6 the VM runs complete multi module programs. A module has an init code object. Imports resolve through the existing `ModuleLoader`, which owns path resolution, the module cache, the loading stack and cycle detection. The VM plugs into that loader instead of creating a second loader. Module initialization is depth first. A module is marked initializing before its code runs and initialized after its export table is complete.

Exports follow the same rules as `evaluate_module_ast`. A module without any `export` statement exports nothing. A module with exports exposes only the marked declarations. Duplicate export names raise the same error. Wildcard imports bind the same names into the current scope.

Cross module types and traits are values in the module export table. A qualified type name such as `geo.Point` resolves through the module table at construction and method dispatch time.

The implicit `project` binding and the `LOAD_PROJECT` opcode read the same `state.project_value` that `load_project_config` builds. Package module resolution reuses `src.pkg` and `ModuleLoader.resolve`. Extern functions reuse the existing Python bridge and the same extern error text.

Semantic reference: `docs/phase-4b-bytecode-vm/04-compiler-lowering.md` section 12.14, `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` section 13.8, and `docs/phase-4b-bytecode-vm/07-implementation-rollout-and-decisions.md` sections 20.3, 20.4 and 21.7.

## Prerequisites

- V5 is `gate green`. Types, traits and generic constraints work.
- The V5 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v5 --fail-fast
```

- The baseline suite is green.

Contract surfaces this phase depends on:

- `src/vm/image.py`: `ModuleInfo`, `CallSite.dispatch` values `module` and `extern`, `ProgramImage.modules`.
- `src/vm/modules.py`: `ModuleScope`, `VMModuleLoader`, `evaluate_module_image`, `initialize_module`.
- `src/module_loader.py`: `ModuleLoader.load`, `load_path`, `resolve`, `cache`, `loading`, `base_stack`.
- `src/runtime.py`: `evaluate_module_ast`, `build_module_exports`, `bindWildcardImport`, `callModuleMember`, `callExternalFunction`.
- `src/config.py`: `load_project_config`, `state.project_value`.
- `src/pkg`: package resolution and lock file handling.

## Deliverables

### By file

| File | Work in V6 |
|---|---|
| `src/vm/modules.py` | `ModuleScope`, `VMModuleLoader`, `evaluate_module_image`, `initialize_module`, `module_from_scope`, `resolve_qualified_type`, `call_module_function`, `load_project_value` |
| `src/vm/compiler.py` | Module declaration entries, import lowering, alias binding, wildcard import lowering, export marking, `LOAD_PROJECT`, extern declarations, cross module type references, `CALL_MODULE` call sites |
| `src/vm/declarations.py` | External type resolution, extern function registration, `declare_extern` |
| `src/vm/interpreter.py` | Handlers for `IMPORT`, `IMPORT_WILDCARD`, `LOAD_MODULE_MEMBER`, `LOAD_PROJECT`, `EXPORT`, `DECLARE_EXTERN`, `CALL_EXTERN`, `CALL_MODULE` |
| `src/vm/host.py` | Extern bridge, project field access, module host boundary |
| `src/module_loader.py` | Engine dispatch in `_evaluate`, shared export table helper call |
| `src/config.py` | Read the project metadata engine key and expose it on state before program start |
| `src/runtime.py` | Extract `build_module_exports` from `evaluate_module_ast` and make it public |
| `src/vm/tests/test_modules.py` | Module declaration, import, alias, wildcard, export and immutability |
| `src/vm/tests/test_module_cycles.py` | Cycle detection and the exact error text |
| `src/vm/tests/test_cross_module.py` | Cross module types, traits and qualified calls |
| `src/vm/tests/test_project.py` | Project configuration and implicit project |
| `src/vm/tests/test_extern.py` | Extern registration and calls |
| `src/vm/tests/test_packages.py` | Package module resolution through the loader |
| `src/vm/tests/golden/` | V6 golden disassembly snapshots |
| `src/vm/tests/corpus/v6/` | V6 differential corpus, including multi file module folders |
| `tests/test_vm_modules.py` | End to end VM engine test for module programs |

### By language feature

| Feature | Required behavior |
|---|---|
| Module declaration | `module main;` creates a `ModuleInfo` entry |
| Built in import | `use strings;` loads the built in module through `ModuleLoader.resolve` |
| Relative import | `use .helper as helper;`, `use ..shared` and `use ...shared` resolve through `base_stack` |
| Path import | `use "./lib/greeting.po" as greeting;` |
| Package import | A package module resolves through `src.pkg` and the lock file |
| Alias import | `use "./lib/greeting.po" as greeting;` binds one local alias |
| Wildcard import | `use "./lib/greeting.po" as *;` binds all exports |
| Export | `export fun`, `export type`, `export variable` and `export project` |
| Export table | Built with the same rules as `evaluate_module_ast` |
| Module immutability | Module member assignment is a runtime error |
| Cross module type | `geo.Point.[0, 0]` resolves the type through the module table |
| Cross module trait | A trait from another module can constrain a generic parameter |
| Project configuration | `project.po` loads through `load_project_config` |
| Project engine key | The project metadata key `engine` with value `vm` selects the VM when no command line or environment override exists |
| Implicit project | `project` is visible in every module without an import |
| `LOAD_PROJECT` | Pushes `state.project_value` or the implicit `project` binding |
| Extern function | `extern fun name(...) >> "module.function";` registers a Python bridge |
| Extern call | `CALL_EXTERN` reuses `callExternalFunction` |
| Module cycle | The loader and checker produce the same cycle error and chain as the tree walker |

## Task checklist

- [ ] Add `ModuleInfo` population and module init code objects.
- [ ] Lower module declarations and the module table.
- [ ] Add `IMPORT` and alias binding.
- [ ] Add `IMPORT_WILDCARD` and wildcard binding.
- [ ] Add `LOAD_MODULE_MEMBER` and `CALL_MODULE`.
- [ ] Add `EXPORT` and the shared module export table builder.
- [ ] Add `LOAD_PROJECT` and the implicit project binding.
- [ ] Add external type resolution for cross module types.
- [ ] Add extern declarations and `CALL_EXTERN`.
- [ ] Hook the VM into `ModuleLoader._evaluate`.
- [ ] Add package module resolution and the module cache key rules.
- [ ] Add module cycle and module mutation errors.
- [ ] Add V6 unit tests, corpus, golden snapshots and the module engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `module main;` | no instruction, `ModuleInfo.name` and `ModuleInfo.path` set |
| `use strings;` | `IMPORT module_id, slot`, then the alias is bound to `slot` |
| `use strings as text;` | `IMPORT module_id, slot` |
| `use "./lib/greeting.po" as greeting;` | `IMPORT module_id, slot` |
| `use "./lib/greeting.po" as *;` | `IMPORT_WILDCARD module_id` |
| `greeting.hello("x")` | evaluate args, `CALL_MODULE call_site` with module and export name |
| `greeting.value` | `LOAD_MODULE_MEMBER module_id, export_id` |
| `export fun hello(...)` | `DECLARE_FUNCTION function_index`, `DUP`, `STORE_GLOBAL hello`, `EXPORT hello` |
| `export type Point[...]` | `DECLARE_TYPE type_id`, `DUP`, `STORE_GLOBAL Point`, `EXPORT Point` |
| `export value := 1;` | evaluate value, `DECLARE_INFER_GLOBAL value`, `STORE_GLOBAL value`, `LOAD_GLOBAL value`, `EXPORT value` |
| `export project: Project = Project.[...]` | project value is loaded by `load_project_config`. The module also binds and exports it with `LOAD_GLOBAL project`, `EXPORT project` |
| `project.logLevel` | `LOAD_PROJECT`, `LOAD_MEMBER logLevel` |
| `extern fun parse(text: str): any >> "json.parse";` | `DECLARE_EXTERN extern_id`, `LOAD_GLOBAL parse`, `EXPORT parse` when exported |
| `parse("{}")` where `parse` is extern | evaluate args, `CALL_EXTERN call_site` |
| `geo.Point.[0, 0]` | evaluate args, `CONSTRUCT external_type_id, call_site` |
| `shapes.render(person)` | evaluate `person`, `CALL_MODULE call_site` with module and export name |
| module init | lower dependency imports, lower statements, build export table, `LOAD_NOVA`, `RETURN` |

## Runtime semantics notes

### Module table

A `ModuleInfo` entry carries:

- `name`: the declared module name.
- `path`: the resolved absolute path or the built in module name.
- `code_index`: the module init code object.
- `imports`: the resolved import descriptors.
- `exports`: the `(name, kind)` pairs in declaration order.

`CompileContext` compiles one module at a time and collects dependencies. A dependency is compiled before the importer finishes linking. The module table is keyed by the resolved module identity: resolved path plus package version when the module comes from a package.

### Loader integration

`src/module_loader.ModuleLoader._evaluate(path)` currently calls `evaluate_module_ast`. V6 changes it to:

```python
if getattr(get_state(), "engine", "tree") == "vm":
    from .vm.modules import evaluate_module_path
    return evaluate_module_path(self, path)
return evaluate_module_ast(ast, module_name, path, self)
```

`evaluate_module_path` must use the same `self.cache`, `self.loading`, `self.base_stack` and `self.resolve` calls. It must not create a second cache. `load_path` remains the only place that checks the cache and detects cycles, so the VM gets the same cycle error text and the same chain details.

### Module initialization

1. The loader resolves the path and checks the cache.
2. The loader checks the loading stack for a cycle.
3. The loader pushes the resolved path on the loading stack.
4. The compiler produces the module image and its dependencies.
5. The VM creates a `ModuleScope` with an empty `LocalStore`, empty function and type tables and an empty wildcard table.
6. The VM pushes the module scope onto `state.scope` and `state.call_frames`.
7. The VM runs the module init code object.
8. The VM builds the export table from the final scope.
9. The VM marks the module initialized and caches it.
10. The loader pops the loading stack in a `finally` block.

A failed module does not enter the cache. The loading stack is popped in a `finally` block. The error is wrapped by `ModuleLoader._wrap` with the same `MODULE` error text as the tree walker.

### Export table

V6 extracts the export table construction from `evaluate_module_ast` into `src.runtime.build_module_exports(scope_variables, scope_functions, scope_types, exported, module_path)`. Both engines call it.

Rules:

- A module with no `export` statement exports nothing.
- `export fun` exports the overload list.
- `export type` exports the type object.
- `export variable` exports the value.
- A duplicate export name raises the same `MODULE` error.
- A declared export that is not present in the scope raises the same `MODULE` error.
- Export order follows source order for diagnostics and disassembly.

`EXPORT name` registers the name in `frame.module_scope.exports`. It pops the duplicated value that follows the declaration store. The value itself already lives in the module global store.

### Imports

- `IMPORT module_id, slot` loads the module through `ModuleLoader.load` and stores the `PowangModule` value in the local slot.
- `IMPORT_WILDCARD module_id` calls `src.runtime.bindWildcardImport(where, module)` in the current VM frame. The bridge makes `ScopeStack.new_variable` write into the frame `LocalStore`.
- `LOAD_MODULE_MEMBER module_id, export_id` reads the module export by name. A missing member raises the same `MODULE` or `IDENTIFIER` error as the tree walker.
- `CALL_MODULE call_site` reads the module and export name, then calls `src.runtime.callModuleMember(where, module, member_name, arguments)`. That helper selects an overload and calls `callFunctionValue`, which delegates to the VM for VM functions.
- A module member assignment raises the same `MODULE` mutation error as the tree walker. Modules are immutable after initialization.

### Cross module types

- A cross module type entry in `ProgramImage.types` has `name` in `module.Type` form and `kind` `object` or `enum`. Its `properties` and `methods` may be empty because the runtime resolves the real type object from the module table.
- `src.vm.declarations.resolve_type(type_name, frame)` splits a qualified name, loads the module from the frame module table or the global module cache, reads the export, and verifies that it is a `PowangObjectType`.
- `CONSTRUCT` and `CALL_STATIC` use `resolve_type` before reading the field layout or method table.
- A cross module trait is a `TraitRuntimeInfo` in `state.traits` under the declared trait name. The qualified name `mod.Trait` resolves through the module table when `CHECK_TRAIT` or `TRAIT_CAST` receives a qualified name.

### Project

- `load_project_config(state, base_path)` runs before the program and builds `state.project_value`.
- `LOAD_PROJECT` pushes `state.project_value` when it exists.
- When a module has no explicit `project` declaration, the VM inserts the implicit `project` binding into the module scope before running the init code. This matches `evaluate_module_ast`.
- `project.logLevel`, `project.allowSystem`, `project.modules` and `project.paths` read through `LOAD_MEMBER` or `LOAD_FIELD`. The `Project` type is registered as a host object type with the existing `BUILTIN_OBJECT_TYPES` layout.
- The project metadata key `engine` selects the engine when it is present. Precedence remains command line, environment, project, default. This key is host configuration metadata read from `project.po` before `state.project_value` is built. It is not a field of the `Project` value type, so the language type layout does not change.

### Packages

- `ModuleLoader.resolve("package", name, base, level)` already resolves package module paths through `src.pkg`.
- The VM must key its module cache by resolved path and package version. The loader cache key is already the resolved path. When a package version is part of the path or the lock file, the resolved path differs and the cache entry differs. If the loader can resolve the same path at two package versions, the cache key must include the package version explicitly.
- A missing package or a lock mismatch raises the same `MODULE` or `USAGE` error as the tree walker.
- `project.po` may declare `modules` and `paths`. The VM must not bypass the loader search path setup.

### Extern functions

- `DECLARE_EXTERN extern_id` reads the `ExternInfo` descriptor. The descriptor has:
  - `name`: the Powang name.
  - `target`: the host module and function string, for example `stdlib_env.argv`.
  - `args`: the parameter AST.
  - `return_node`: the return type AST.
- The runtime registers the function in `state.external_functions[name]` in the same shape the tree walker expects.
- `CALL_EXTERN call_site` reads the name, looks up `state.external_functions[name]`, and calls `src.runtime.callExternalFunction(where, name, function, external, arguments)`.
- Named arguments for extern functions are rejected with the same `ARGUMENT` error text as the tree walker.
- Extern errors are wrapped as `EXTERN` errors with the same kind, message and cause chain.

### Module cycle error

The cycle error text is owned by the existing loader and checker. The VM must not hard code a new string. Two paths exist:

- The loader path raises `MODULE` error `Cyclic module import` with the repeated path chain.
- The checker path raises `TYPE` error `cyclic module import involving '<name>'` when the import graph is checked before execution.

The VM calls `ModuleLoader.load_path` and does not catch or rewrite either error. The differential corpus compares the full stderr and exit code, so the exact path and chain order must match the tree walker.

## Acceptance criteria

1. Every V6 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. A two module program with a relative path import runs on both engines with identical output.
3. A built in module import `use strings;` runs on both engines with identical output.
4. A wildcard import binds the same names as the tree walker.
5. A module with no exports exposes no members and a member access raises the same error.
6. A duplicate export raises the same `MODULE` error text.
7. Module member assignment raises the same module mutation error.
8. A cross module type constructs and its methods run on both engines.
9. A cross module trait constrains a generic function on both engines.
10. `project.po` values are visible through the implicit `project` binding in every module.
11. A project metadata key named `engine` with value `vm` selects the VM when no command line or environment override exists.
12. A package module resolves through the existing loader and lock file.
13. An extern function call returns the same value and error text on both engines.
14. A module cycle produces the same error text, exit code and any chain details as the tree walker.
15. The V6 corpus reports zero mismatches.
16. `test_cross_module.py`, `test_module_resolution.py` and `test_project.py` pass with `POWANG_ENGINE=vm`.
17. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_modules -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_module_cycles -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_cross_module -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_project -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_extern -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_packages -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v6 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_cross_module.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_module_resolution.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_project.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_modules.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v6\modules\main.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v6\modules\main.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v6/`.

`modules/main.po`:

```po
use "./greeting.po" as greeting;
use "./greeting.po" as *;

println(greeting.hello("powang"));
println(greeting.shout("powang"));
println(hello("wildcard"));
println(shout("wildcard"));
```

`modules/greeting.po`:

```po
module greeting;

export fun hello(name: str): str {
    return "hello " + name;
}

export fun shout(name: str): str {
    return hello(name) + "!";
}
```

`builtin/main.po`:

```po
use strings;

println(strings.trim("  text  "));
println(strings.upper("powang"));
println(strings.replace("a-b-c", "-", "+"));
println(strings.split("a,b,c", ","));
```

`cross_module/main.po`:

```po
use "./geometry.po" as geo;
use "./geometry.po" as *;

a: geo.Point = geo.Point.[0, 0];
b: geo.Point = geo.Point.[3, 4];
println(geo.distance(a, b));

p: Point = Point.[2, 3];
println(p.x + p.y);
println(distance(Point.[0, 0], Point.[1, 1]));
```

`cross_module/geometry.po`:

```po
module geometry;

export type Point[+] {
    | x: int;
    | y: int;
}

export fun distance(left: Point, right: Point): int {
    dx := left.x - right.x;
    dy := left.y - right.y;
    return dx * dx + dy * dy;
}
```

`project/main.po`:

```po
println(project.logLevel);
println(project.allowSystem);
println(project.paths[0]);
```

`project/project.po`:

```po
module project;

export project: Project = Project.[
    modules >> [],
    paths >> ["."],
    logLevel >> "debug",
    allowSystem >> false
];
```

`extern/main.po`:

```po
use crypto;

println(crypto.sha256("abc"));
```

`cycle/main.po`:

```po
use "./a.po" as a;
println(a.value());
```

`cycle/a.po`:

```po
module a;

use "./b.po" as b;

export fun value(): int >> 1;
```

`cycle/b.po`:

```po
module b;

use "./a.po" as a;

export fun value(): int >> 2;
```

`error_mutation/main.po`:

```po
use "./greeting.po" as greeting;
greeting.hello = 1;
```

The cycle corpus must produce the exact cycle chain in stderr. The harness compares full stderr.

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v6_modules` | `src/vm/tests/corpus/v6/modules/main.po` | `IMPORT`, `IMPORT_WILDCARD`, `CALL_MODULE`, `LOAD_MODULE_MEMBER`, module and export indices |
| `v6_cross_module` | `src/vm/tests/corpus/v6/cross_module/main.po` | External type entry names in `module.Type` form, `CONSTRUCT` external type index |
| `v6_project` | `src/vm/tests/corpus/v6/project/main.po` | `LOAD_PROJECT`, `LOAD_MEMBER`, project field names |
| `v6_extern` | `src/vm/tests/corpus/v6/extern/main.po` | `DECLARE_EXTERN`, `CALL_EXTERN`, extern descriptor target |
| `v6_cycle` | `src/vm/tests/corpus/v6/cycle/main.po` | Module table contains both modules, cycle failure matches the tree walker path and text, no VM marker in the error |

## Atomic commit plan

1. `vm(v6): add module table entries and module init code objects`
2. `vm(v6): lower module declarations`
3. `vm(v6): add import and alias binding`
4. `vm(v6): add wildcard imports`
5. `vm(v6): add module member loads and module calls`
6. `vm(v6): add export table builder and export instruction`
7. `vm(v6): add project loading and the implicit project binding`
8. `vm(v6): add cross module type resolution`
9. `vm(v6): add extern declarations and extern calls`
10. `vm(v6): hook the vm into the module loader`
11. `vm(v6): add package resolution and module cache key rules`
12. `vm(v6): add module cycle and mutation errors`
13. `vm(v6): add v6 corpus golden snapshots and module engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| A second module loader appears | The VM calls `ModuleLoader.load_path` and never builds its own cache | Revert the loader commit |
| Export rules drift | Extract `build_module_exports` and call it from both engines | Revert the export commit |
| Wildcard binding writes to the wrong scope | `bindWildcardImport` runs inside the VM frame with the scope bridge active | Revert the wildcard commit |
| Cross module type lookup fails for nested modules | Qualified name resolution splits on the first dot and reads the module export table | Revert the cross module commit |
| Project engine precedence differs | Precedence test with command line, environment and project value | Revert the project commit |
| Package cache shares a wrong entry | Key by resolved path and package version. The loader already resolves the path | Revert the package commit |
| Extern error text changes | Call `callExternalFunction` and compare full stderr | Revert the extern commit |
| Cycle chain order differs | Use `ModuleLoader.load_path` unchanged and test the exact chain | Revert the loader hook |
| Module mutation is allowed | Module values are immutable after init and `STORE_MEMBER` checks modules | Revert the mutation commit |

## Exit gate

V6 is closed when all of these are true:

- [ ] Every V6 opcode has a handler, a verifier rule and a unit test.
- [ ] The V6 corpus reports zero mismatches.
- [ ] Built in, relative, path and package imports match the tree walker.
- [ ] Export tables, wildcard imports and module immutability match the tree walker.
- [ ] Cross module types and traits match the tree walker.
- [ ] Project configuration and the implicit project binding match the tree walker.
- [ ] Extern functions match the tree walker for values and errors.
- [ ] Module cycles produce the exact tree walker error text and any chain details.
- [ ] `test_cross_module.py`, `test_module_resolution.py` and `test_project.py` pass with `POWANG_ENGINE=vm`.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
