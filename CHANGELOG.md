# Changelog

All notable changes to powang are documented here.

## Unreleased

### Added

- A native C++17 runtime milestone N0 under `native/`, consuming the same `PWB1` program image as the Python compiler.
- An N0 scalar subset with nova, undef, bool, int, num and char values, integer and number arithmetic, comparisons, logical not, negation, locals, jumps, top level `print` and `println`, and the N0 disassembler and verifier. Unsupported opcodes report a clear runtime error.
- A `temp.cpp` source generator in `src/vm/native/source_gen.py` that renders into a buffer. The default integrated compiler writes a temporary `temp.cpp` file for diagnostics. The generated source is temporary and is never committed.
- An integrated `g++` driver in `src/vm/native/compiler.py`, a CMake and Ninja build in `src/vm/native/build.py`, and an image loader in `src/vm/native/loader.py`.
- `powang vm native info`, `powang vm native run <file.po>` and `powang vm native compile [--output PATH] [--keep-source] <file.po>`.
- `python -m src.vm.native.gen_opcodes --check` regenerates and checks `native/include/pwb/opcodes_generated.hpp` from the Python opcode registry.
- 18 native build tests in `tests/test_native_build.py`. They cover the generated opcode header, the in-memory buffer, the `print(1 + 2);` gate, byte-exact disassembly parity, corrupt image rejection, compiler diagnostics, temp cleanup, CLI run, CLI compile, native info, number semantics, print arity, loop image verification, bad jump rejection, missing compiler handling and stdin compilation. The number semantics test runs 36 subtests.
- The native N1 execution tier: big integers with int64 promotion, locals, globals, declarations, branches, range loops, `loop`, `break`, `continue`, functions, recursion, mutual recursion, defaults, named arguments, variadics, overload selection, closures by value and by reference, named lambda recursion, higher order function values, frames and iterators.
- The native N2 object tier: UTF-32 strings, arrays, tuples, insertion ordered maps and sets, indexing, slicing, string and array operators, iteration, deep copy with a cycle memo, interpolation, the `format` and `printf` builtins, the character builtins and the array, string, map, set, tuple and char native methods.
- `src/vm/native/meta.py` builds the deterministic PWBM function and type metadata block, and `pwb_native meta` prints it. `tests/test_native_meta.py` has 5 tests for metadata determinism, the image hash, parameter metadata and the C++ metadata round trip.
- The native N3 core: user types, constructors, public and private fields, instance methods, statics, enums, traits, default methods and operator overloading.
- `tests/native/corpus/n1` has 5 differential programs for arithmetic, big integers, control flow, functions, overloads, variadics, recursion and closures. `tests/native/corpus/n2` has 6 differential programs for strings, containers, copy semantics, slicing, interpolation and native methods. `tests/native/corpus/n3` has 5 differential programs for types, constructors, enums, traits and operators. `tests/test_vm_native_corpus.py` runs all three corpora.
- The native N4.1a `PWBB` bundle container and SHA-256 digest. The Python bundle builder and native parser carry the entry `PWB1` image and `PWBM` metadata. The generated `temp.cpp` embeds the bundle and calls `run_embedded_bundle_with_meta`, and the raw single-image path remains.
- The native N4.1b and N4.1c module graph: `ModuleLoader.read_sources`, the deterministic import-graph builder, `ModuleRuntime`, the `ModuleTable`, per-module symbol tables, `IMPORT`, `IMPORT_WILDCARD`, `LOAD_MODULE_MEMBER`, `EXPORT`, `CALL_MODULE`, module member values, the export table, the legacy warning, imported types, module-qualified construction, alias and wildcard collision checks, deferred import errors and the cyclic-import guard.
- The native N4.2 error model: `Tag::Error`, `ErrorObject`, exact `[KIND ERROR]` text, `MAKE_ERROR`, `ERROR_PROPERTY`, `THROW`, `RETHROW`, `PROPAGATE`, `TRY_BEGIN`, `TRY_END`, `FINALLY_END`, `SET_RETURN`, `SET_TRANSFER`, `JUMP_IF_TRANSFER`, `APPLY_TRANSFER`, `ABANDON_FINALLY`, the handler stack, the private unwind signal, call frame records, top-level standard output parity and PWBM version 2 descriptors and the spec map.
- The native N4.3 references: value flags, `Tag::Ref`, `RefObject`, `REF_LOCAL`, `REF_GLOBAL`, `REF_FIELD`, `REF_INDEX`, `LOAD_REF`, `STORE_REF`, reference parameters, reference pipelines, frame lifetime tokens and module global write-through.
- The native N4.4 project and extern boundary: the bundle project snapshot, `Tag::Project`, `ProjectObject`, `LOAD_PROJECT`, implicit `project` binding per module, the extern descriptor table, `DECLARE_EXTERN`, `CALL_EXTERN`, the allowed-module check and the host scalar extern hook.
- The native N5 async and task tier: lazy async tasks, `spawn` worker tasks with cloned module snapshots, `await`, `wait`, `cancel`, `task_status`, the `task.wait`, `task.cancel` and `task.status` native methods, the pending async task limit, task error propagation, cooperative cancellation checks, deterministic worker execution and task isolation.
- The native N5 file and host tier: `open`, `read`, `write` and `close` file builtins with the Python mode table, file values, the `file` native methods, `input`, `inputf`, `system`, `typeof` and `typedeep`.
- The native N6 engine integration: `--engine=native`, the native differential runner (`python -m src.vm.native.differential`), and the `powang vm native diff`, `bench`, `clean` and `pack` commands.
- Native coverage for the examples corpus: casts, user type coercion on typed declarations, field defaults, named user type constructors, match patterns (literal, wildcard, binding, range, array, tuple and object), destructuring, typed arithmetic, spreads from arrays, tuples, sets, maps and strings, generic overload filtering, tuple and set `typedeep`, and structure and element lock enforcement.
- The default scalar host bridge for `math`, `stdlib_strings`, `stdlib_json`, `stdlib_url`, `stdlib_crypto`, `stdlib_time` and `stdlib_env`, including JSON parsing and stringifying, URL encoding, query building, SHA-256, constant-time comparison, time helpers and argument counts.
- All 32 programs under `examples/` match the Python VM on standard output, standard error and exit code. `tests/test_vm_native_examples.py` runs the full example differential.
- `tests/native/corpus/n4` has the module, wildcard, legacy, error, try, finally, propagation, reference, project and extern differential programs. `tests/native/corpus/n5` has lazy task, worker task, cancellation, task error, file, cleanup, async trait, task isolation and pending limit programs. `tests/test_vm_native_corpus.py` runs the N1 to N5 corpora against the Python VM.
- `tests/test_native_bundle.py` has 15 tests for the bundle layout, digest, module graph, project block, parser rejection cases, generated source and bundle execution. `tests/test_native_meta.py` has 6 tests. `tests/test_native_tasks.py` has 2 host input and task status parity tests. `tests/test_vm_native_engine.py` has 5 tests for `--engine=native`, native imports, error stream parity and the differential module.
- The full test suite now has 644 tests.

### Notes

- The native runtime is opt in. The Python VM remains the default engine and the differential oracle. The version stays `0.22.0` because N0, N1, N2, the N3 core, N4, N5 and the N6 integration are milestones, not releases.
- N0 through N5 and the N6 integration cover scalars, big integers, functions, closures, strings, containers, user types, enums, traits, operators, native methods, the `PWBB` bundle, modules, imports, exports, language errors, try, catch, finally, propagation, references, project values, the scalar extern boundary, lazy async tasks, worker tasks, cancellation, file I/O, the default host bridge, `--engine=native` and the native differential and packaging tools. The N5 worker executor runs spawned work deterministically on the spawning thread against a cloned module snapshot, which matches the single-worker differential contract. Remaining N6 work is the seeded fuzz gate, the stress gate, executable caching, inline caches, threaded dispatch and the default engine decision. Native method access-control and ambiguity error text parity also remains in the N3 remainder. Mixed int/num arithmetic and comparisons follow the Python VM cast order. Division and modulo by zero return nova for int and num. Integer overflow promotes to bigint. Full native parity is not claimed across every host module and platform.

## 0.22.0

### Added

- `project.engine` in `project.po` selects `tree` or `vm` for a project run.
- `powang run --engine=tree|vm` overrides the project engine for one run.
- Imported module images join the optional bytecode cache with source and transitive dependency hashes.
- Runtime block scopes. Block locals, loop variables, catch bindings and match bindings are hidden after their scope ends.
- `powang vm abi` and `powang vm abi --json` generate the native opcode, operand and tag contract as a C header or JSON.
- The native VM contract is documented in `docs/phase-4b-bytecode-vm/implementation/V10-native-vm-contract.md`.

### Changed

- The bytecode VM is the default execution engine. The tree walker remains available with `--engine=tree` and `POWANG_ENGINE=tree`.
- The language version is `0.22.0` and the package version is `0.22.0`.

### Fixed

- Errors inside catch blocks now reach enclosing handlers and enclosing finally blocks.
- Postfix `?` propagation runs active finally blocks, including nested ones.
- Break and continue inside a finally body discard the pending error and clean up the handler.
- Block locals no longer leak into the module scope, the task clone or a later block iteration.
- Task handles copied by a typed declaration resolve to the live task in `wait`, `cancel` and `task_status`.
- `performOperation` no longer recurses forever when an implicit cast makes no progress.
- Deep recursion reports the language recursion error instead of a Python traceback.
- Function copies keep their bytecode metadata.

## 0.21.0

### Added

- A stack based bytecode virtual machine at `src/vm` with an opcode registry, program image codec, instruction builder, verifier, disassembler, trace mode and execution loop.
- An AST compiler that lowers every implemented language construct to bytecode, including declarations, calls, containers, user types, enums, traits, operator dispatch, errors, references, modules and tasks.
- The `--engine=tree` and `--engine=vm` selection flag, the `POWANG_ENGINE` environment variable and the `powang vm` command line surface.
- `powang vm disasm` prints the module, type, trait, function, constant, call site, pattern and source tables plus the instruction stream.
- `powang vm run --trace` prints a compact instruction trace with source spans.
- `powang vm diff` runs both engines and compares standard output, standard error and the exit code.
- `powang vm bench` runs the benchmark corpus on both engines.
- A differential test harness that runs the example suite and an inline corpus on both engines.
- Image serialization with the `PWB1` container, format version `1`, a CRC32 checksum and deterministic table encoding.
- A verifier that checks opcode validity, operand ranges, constant indices, slots, jump targets, exception ranges, stack heights, merge points, spans and cross table references.

### Changed

- `InterpreterState` carries an `engine` field. File runs, project runs, imports and the REPL honor the selected engine.
- The module loader evaluates imported modules with the active engine, so a VM program keeps its module graph on the VM.
- `callFunction` delegates to the VM when a function carries a code object and the VM engine is active, so shared runtime helpers and extern callbacks keep working.
- The test helpers accept an `engine` argument and the full suite runs on both engines.

### Notes

- The tree walker remains the default engine. The VM is opt in until one full release has zero differential mismatches.
- The Python reference VM is a correctness and differential oracle. The native VM remains the performance target.
- Private interpreter state, checkpoints and temporary files are ignored by git.

## 0.19.1

### Changed

- String indexing, string iteration and `str.get` now return `char`.
- Spread over a string now yields `char`.
- Slicing a string still returns `str`.

### Removed

- `str.char_at`. Use `text[index]`, `str.get(index)` or `str.chars()`.

## 0.19.0

### Added

- `char`, a Unicode scalar value type, with single-quoted literals such as `'a'`.
- Character escapes, including `\u{HEX}` Unicode escapes in character and string literals.
- Character builtins: `is_digit`, `is_alpha`, `is_alnum`, `is_space`, `is_upper`, `is_lower`, `is_ascii`, `ord`, `chr` and `digit_value`.
- `str.char_at` and `str.chars` for explicit character access.
- Native `char` methods: `code`, `to_str` and the ASCII character predicates.
- Character concatenation with strings and characters.
- Character ordering, hashing and comparison by code point.
- Explicit `char` and `str` casts and `char.[value]` construction.

### Changed

- String indexing still returns a one-character `str` for compatibility.
  Use `str.char_at` when a `char` is required.
- `str.chars` returns `arr[char]`, while iterating a `str` still yields one-character strings.

## 0.14.0

### Added

- Cross-module type checking for aliased and wildcard imports.
- Imported functions, variables, object types and traits.
- Module-qualified calls, type annotations and construction.
- Qualified trait annotations.
- Import cycle detection and imported module diagnostics at the import site.
- LSP cross-module diagnostics.

### Changed

- The checker resolves modules with the same path rules as the runtime loader.
- Imported signatures qualify exported type and trait names to the module alias.

## 0.13.3

### Changed

- `function` is no longer a valid type annotation. Write function types as `fun[arg_types..., return_type]`.
- `function` is reserved and cannot be declared as a user type.

### Fixed

- The LSP keeps nested function types such as `fun[fun[int, int], int]` intact.

## 0.13.2

### Added

- Built-in object type templates are registered in every runtime scope.
- `project` is bound implicitly in imported modules when a project configuration is loaded.
- `Project` is highlighted as a user type by the LSP.

### Changed

- The LSP now offers implicit `project` completion and hover in Powang files.

## 0.13.1

### Added

- `Project` is a fully integrated built-in object type with field checking.
- Member access on `project` values works in the checker and at runtime.
- Named and positional `Project` construction validates field names and types.
- A shared `BUILTIN_OBJECT_TYPES` registry drives the checker, runtime and LSP.

### Fixed

- `project.po` files can be type-checked and run directly.
- `project.modules`, `project.paths`, `project.logLevel` and `project.allowSystem` are readable.
- The LSP `undef` inlay hint inserts only the virtual `undef` marker before the existing type.

## 0.13.0

### Added

- Structural `trait` declarations with properties, required methods and default methods.
- Trait annotations on variables, parameters and return types.
- Generic trait constraints with `T: Trait` and `T: TraitA & TraitB`.
- Trait-qualified method definitions with `fun Trait.method(...)`.
- Trait-qualified calls with `Trait.method(value, ...)`.
- Conflict and ambiguity diagnostics for incompatible trait signatures.
- LSP `trait` highlighting and `Trait.` completion.

### Changed

- Function body parameter binding now uses the checker signature, so generic `T` parameters keep their type and constraints.
- Function values with type parameters infer their type arguments at call sites.

## 0.12.0

### Added

- Array, tuple and object destructuring in match patterns.
- Rest bindings in array and tuple patterns.
- Nested match patterns.
- Numeric range patterns with an inclusive lower bound and an exclusive upper bound.
- Boolean and enum exhaustiveness warnings, `PW215`.
- Unreachable case warnings, `PW216`.
- Match expression result type inference.

### Changed

- Match guards run after all destructuring bindings.
- A boolean `true` or `false` in a match pattern is now a literal, not a binding.

## 0.11.0

### Added

- Variadic user functions with `values: T...` and `values..` sugar.
- Generic type parameters on function declarations.
- Explicit call type arguments with `callee[type](...)`.
- Prefix spread with `...values` and `...[1, 2, 3]`.
- Spread support for arrays, tuples, sets, maps and strings.
- Variadic signatures in `typedeep`, such as `fun[int..., int]`.
- LSP signature help and hover for variadic functions.
- LSP `undef type` display for uninitialized typed variables.

### Changed

- Function signatures track type parameters and variadic tails.
- Explicit type arguments select the template overload before concrete overloads.

## 0.10.0

### Added

- Function type annotations with `fun[arg_types..., ret_type]`.
- Lambda expressions with block and `>>` bodies.
- Named lambdas for recursion and `fun &` mutable capture.
- Function values passed as arguments, returned from functions and stored in arrays.
- Function signatures in `typedeep`.
- Examples for loops, slicing, annotations, error frames, spawned methods, lambdas and function types.

### Changed

- Function declarations record their signature for `typedeep` and casts.
- The LSP presents hover text as plain text without markdown bold or code spans.

## 0.9.0

### Added

- `loop` and `loop if` loops, with declarations allowed in the condition.
- `break` and `continue`, including labeled forms.
- Optional labels on `for`, `loop` and `loop if`.
- Slicing with `from >> to`, negative indices and negative ordinary indexing.
- Annotations for `obj`, `task`, `file`, `handle` and `error`.
- Error frames on caught error values.
- `spawn` on method and static method calls.
- Literal boolean dead-branch simplification with `PW210` to `PW214` warnings.

### Changed

- `if false` branches are removed from the AST before checking and execution.
- `loop` without a targeting `break` emits `PW210`.
- `loop if true` recommends `loop`, and `loop if false` is removed.
- `spawn` rejects named arguments with a clear task error.

## 0.8.0

### Added

- Canonical construction with `Type.[args]` for user types and native types.
- Named constructor arguments with `name >> value`, all-or-nothing mixing rules,
  duplicate and unknown name checks.
- Access defaults: `type T[+]` is public by default and `type T[-]` is private by
  default. Redundant explicit specifiers produce a warning.
- Constructor members with `|`, including generated constructors and the
  zero-parameter constructor body hook.
- Write-once constructor parameters using `name: type!`.
- Native construction for `int`, `num`, `str`, `bool`, `nova`, `arr`, `tup`,
  `map` and `set`.
- Structural inference for native construction, including union element types
  such as `arr[int | num]`.
- Union type annotations with flattening, deduplication and per-branch
  assignability.
- `typedeep(value)` for structural type inspection. `typeof` remains shallow.
- `--no-warnings` and a warning sink shared by the parser, checker and runtime.
- Native type namespaces for `str`, `arr`, `map`, `tup`, `set`, `file` and
  `task`.
- Static user methods called as `Type.method`.
- Explicit instance method markers with `fun this.name` and `fun .name`.
- Immediate type checker errors for unknown native members and user members.
- Stronger inference for native methods, tuple indexed reads, set unions, file
  methods and task methods.
- Deep copying for plain function parameters.
- Container structure and element locks through outer and inner `!` qualifiers.
- Empty literals `[>>]` and `[/]`, plus set construction with `set[...]`.
- Map index insertion through `map[key] = value`.
- Generic user types with `type Box[T]` and `type Box[+][T]`.
- Single-element tuple declaration warnings.
- Tuple qualifier and map key qualifier errors.
- `&>` reference pipeline sugar and optional parentheses for pipeline call
  targets.
- `strings.split` now has the default separator `" "`.

### Changed

- Array, map and tuple literals now desugar to canonical construction nodes.
- Mixed arrays infer a union instead of `mixed`.
- `python -O` no longer disables the new language checks.
- `.[...] as T` remains valid as the legacy positional form.

### Fixed

- Copying an object no longer shares `PropertyConst` and `PropertyWeak` state
  between instances. Write-once constructor members now work for every instance.
- Pipeline precedence now allows `hello(name) :> strings.upper + "!"`.

## 0.7.0

### Added

- Grammar driven `TypeSpec` representation, structural casts and rest tuple
  templates.

## 0.6.2

### Added

- `tup[int, ...]` type templating in casts and annotations.

## 0.6.0

### Changed

- Bool, task and `any` type cleanup that prepared the structural type system.

## 0.5.0

### Changed

- Renamed the builtin types `integer` to `int`, `number` to `num`, `array` to `arr`
  and `string` to `str`.
- Typed array annotations now use `arr[element]`, for example `arr[int]` and `arr[str]`.

## 0.4.0

### Added

- Trailing commas in arrays, maps, calls and parameters.
- String interpolation with `$"..."`, block comments with `#! ... !#`, and `println`.
- Range iteration with `for i >> start >> end` and `for i >> start >> step >> end`.
- Destructuring declarations and for-each destructuring, including typed bindings,
  group types and references.
- `match` statements with literal, binding, typed binding and wildcard patterns,
  plus guards.
- Null-safe `?.` access and `??` coalescing.
- Declarations in `if` conditions, scoped to the branch.
- Named arguments using `name >> value`.
- Expression-bodied functions with `>>`.
- Pipeline expressions using `:>`.
- `const` declarations as compile-time macro substitution.
- Typed array annotations such as `array[integer]` and `array[string]`. Element types are
  checked on declarations, function arguments, returns, indexing and casts.
- `inputf(receptor, prompt)` prints the prompt and then reads one line into the receptor.

### Changed

- The `output` builtin is now `print`.
- A bare `array` annotation is sugar for `array[any]`.

### Removed

- The empty uv lock file and build artifacts. The powang repository keeps the
  language implementation, standard library, examples, tests, docs, and banner.

## 0.2.0-web-rc1

### Added

- Reference parameters: `fun f(x: &integer)` with explicit `f(&variable)` calls. Reads
  and writes inside the function mutate the caller's variable, constants are rejected,
  and references cannot be stored, returned, or sent to a task.
- Gradual static type checker: annotated declarations, assignments, operators, calls
  and returns are verified; unannotated code stays dynamic and degrades to `any`.
- `--check` (parse and check only) and `--no-check` (skip the static pass) modes.
- Error-union return types (`T?`), the postfix `?` propagation operator, and the
  `fail(kind, message, details...)` value constructor.
- `try` / `catch` / `finally` with correct return and finally semantics, catchable
  `error(...)`, and native error values exposing kind, message, details, where, line,
  column, frames and cause.
- Stable exit codes: 0 success, 1 language error, 2 usage, 3 internal, 130 interrupt.
- Recursion guard at 900 evaluation levels.
- Real modules: `use name`, `use name as alias`, `use name as *`, relative file modules,
  `export` declarations, per-run module cache, cycle detection with a path chain, and
  namespace member calls.
- Standard library modules: `strings`, `json`, `url`, `env`, `args`, `time`, `crypto`,
  `http` (client and server), `http_router`, and `log`.
- Thread-based tasks: `spawn`, `wait`, `wait(t, timeout_ms)`, `cancel`,
  `task_status`, a bounded worker pool and a bounded pending queue.
- HTTP server with request and response maps, per-request cloned interpreter state,
  body and header limits, request ids, access logging and graceful shutdown.
- Router with literal and `:param` patterns, 404 and 405 handling and middleware.
- Web example application and a 100-request load test, later removed on request so the
  repository keeps only the language, its modules, tests, docs and syntax examples.
- `%` modulo operator, `%:` typed form, and exponent literals.
- REPL with persistent variables and per-line error recovery.
- A 41-case unittest suite and packaging metadata with a `powang` console script.
- `InterpreterState` isolation: scopes, file streams, module caches, type aliases, user
  types, extern registries, paths and script arguments are per execution context.

### Changed

- `use name;` now binds a namespace. Use `name.member` or `use name as *;` for
  unqualified access. Modules without any `export` still expose all top-level names and
  print one warning.
- Exit codes are stable; previously a script error could still exit 0.
- The CLI installs as `powang` through the console script.
- Function values stored in variables are callable.
- Strings and maps are iterable in for-each.

### Fixed

- Array subtraction returned an empty array.
- The `if` statement mutated its own AST, so a false branch could stick forever.
- Scope frames leaked on false conditions, completed loops and errored calls.
- `write` passed wrapper objects to `writelines` and always failed.
- Map concatenation mutated its left operand.
- User-type instances shared mutable property dictionaries.
- Unicode string literals were corrupted by `unicode_escape`.
- Unary digit reversal crashed with a NameError.
- For-each iterators were invisible to the loop body.
- `write` was registered with the wrong arity.
- Division and chunking by zero now return nova or a clean error instead of a traceback.
- Extern bools no longer collapse to nova.
- Overload ties now raise an ambiguity error instead of silently picking one.
- `typeof` on user instances returns the concrete type name.
- Many documentation inaccuracies, including the `while` checklist and arithmetic comments.

### Security

- `system()` is refused while an HTTP server is running unless `--allow-system` or
  `POWANG_ALLOW_SYSTEM=1` is set.
- HTTP server defaults: 1 MiB bodies, 100 headers, 64 KiB headers, 10 s read timeout,
  4 handler slots.
- Each request runs on a cloned interpreter state, so handlers cannot share scopes.
- Access logs never include request bodies or header values.

### Known limitations

- No TLS termination. Use a reverse proxy.
- No HTTP/2, HTTP/3, WebSockets or server-sent events.
- No authentication, authorization, rate limiting, CSRF protection or ORM.
- Concurrency is thread-based. True async I/O through a generator trampoline is
  deferred because the thread model met the 100-request target.
- Cancellation is cooperative and cannot interrupt a blocking extern call.
- `extern type` is unsupported.
- No package registry or dependency resolver.
- Some legacy `assert` checks outside the common paths are still stripped by `python -O`.
- Static checking is per file. Cross-module checking (T7) and source positions in
  diagnostics (T1) are still pending.
