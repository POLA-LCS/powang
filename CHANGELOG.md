# Changelog

All notable changes to powang are documented here.

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
- Pipeline expressions using `|>`.
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
  and returns are verified; unannotated code stays dynamic and degrades to `some`.
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
- Extern booleans no longer collapse to nova.
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
