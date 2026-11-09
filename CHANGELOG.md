# Changelog

All notable changes to powang are documented here.

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
