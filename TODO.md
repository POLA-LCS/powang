# Powang TODO

Last updated: 2026-11-10

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done.

## Next step

- [ ] Phase 4A: debugger and debug adapter.
  - Depends on stable source spans and a debug adapter design.
  - Target versions: powang `0.20.0`, powang-lsp `0.26.0`.
  - The `char` type shipped in powang `0.19.1` and powang-lsp `0.25.1`.
  - The bytecode VM plan is defined in `docs/phase-4b-bytecode-vm/README.md`.

## Language features in order

1. [x] Variadics and spread.
   - [x] `fun sum[T](values: T...): T`
   - [x] `sum(...values)`
   - [x] `sum(...[1, 2, 3])`
   - [x] `sum[int](1, 2, 3)`
   - [x] Zero variadic arguments infer `undef`.
   - [x] Explicit type arguments select the template overload before concrete overloads.
   - [x] LSP `undef type` display for uninitialized typed variables.
   - Plan: `docs/phase-2b2-variadics-and-spread/README.md`

2. [x] Match destructuring and exhaustiveness.
   - [x] Array patterns.
   - [x] Tuple patterns.
   - [x] Object patterns.
   - [x] Range patterns.
   - [x] Enum and boolean exhaustiveness warnings.
   - [x] Unreachable case warnings.
   - Plan: `docs/phase-2b3-match-patterns/README.md`

3. [x] Traits and interfaces.
   - [x] Structural satisfaction.
   - [x] Trait annotations.
   - [x] Trait-qualified methods for signature conflicts.
   - [x] LSP completion after `Trait.`.
   - [x] Default trait method bodies checked against the declared contract.
   - [x] Generic constraints with `T: Trait` and `T: TraitA & TraitB`.
   - [x] Conflict and ambiguity diagnostics.
   - Plan: `docs/phase-2c-traits-and-interfaces/README.md`
   - Diagnostics to implement:
     - `type X cannot satisfy TraitA and TraitB: method draw has incompatible signatures (TraitA.draw() -> str, TraitB.draw() -> bytes). Add fun TraitA.draw and fun TraitB.draw.`
     - `generic parameter T is constrained by TraitA and TraitB, which require incompatible signatures for draw. Use a single trait constraint or a trait-qualified call.`
     - `call to draw is ambiguous between TraitA.draw and TraitB.draw. Cast the value to one trait or use Trait.method.`
   - Default trait method bodies:
     - A default body is checked against the trait contract, not the concrete type.
     - The trait contract exposes only the members declared in the trait.
     - A default body cannot access undeclared members. The checker reports `trait method draw uses member color which is not declared in the trait. Declare color in the trait or remove the usage.`
     - Do not infer the trait shape from members used in a default body. That would make the contract implicit and fragile. If inferred constraints are wanted later, they should be a separate opt-in feature.
     - At runtime, `this` is the concrete object. Declared trait methods dispatch to the concrete implementations. The checker-only contract is not a runtime type.

4. [x] Range patterns.
   - Range patterns are implemented in Phase 2B3 with an inclusive lower bound and an exclusive upper bound.
   - Loop ranges remain sugar for C-style `for`.

5. [x] Cross-module type checking.
   - [x] Check imports and exports across files.
   - [x] Report errors at the importing call site.
   - [x] Preserve module boundaries for traits and object types.
   - [x] Qualified type annotations and construction.
   - [x] Import cycle detection.
   - [x] Built-in `use name`, relative `use .name` and `use ..name`, and explicit path imports.
   - Plan: `docs/phase-2d-cross-module-types/README.md`

6. [x] Async and await.
   - [x] `async fun` declarations, methods, statics, trait defaults and lambdas.
   - [x] `await` expressions and top-level await.
   - [x] Lazy async tasks with `spawn` as the parallel primitive.
   - [x] Await type checking and result type propagation.
   - [x] Lazy task wait, cancel, status, limits, error propagation and shutdown cleanup.
   - [x] LSP keyword highlighting, completion, hover, indexing and diagnostics.
   - Plan: `docs/phase-3a-async-await/README.md`

7. [x] Package registry and dependency resolver.
   - [x] `powang.toml` manifest and `powang.lock` lock file.
   - [x] Semver constraints and backtracking resolver.
   - [x] Registry and path dependencies.
   - [x] Local and HTTP registry clients with SHA-256 integrity checks.
   - [x] Safe archive extraction and global cache.
   - [x] `powang pkg` init, add, remove, install, update, list, tree, search and clean.
   - [x] Runtime and checker module resolution for installed packages.
   - [x] LSP diagnostics for package imports.
   - Plan: `docs/phase-3b-package-registry/README.md`

8. [x] Operator overloading through traits.
   - [x] Built-in `Add`, `Subtract`, `Multiply`, `Divide`, `Remainder`, `Negate` and `Compare` traits.
   - [x] Arithmetic, unary minus and comparison operators.
   - [x] Trait-qualified implementations and custom trait-qualified methods.
   - [x] Trait annotations and generic constraints.
   - [x] Right-operand overload selection.
   - [x] Checker diagnostics and runtime ambiguity detection.
   - [x] LSP completion, hover, semantic tokens and diagnostics.
   - Plan: `docs/phase-3c-operator-overloading/README.md`

9. [x] Character type.
   - [x] `char` as a Unicode scalar value.
   - [x] Single-quoted character literals and `\u{HEX}` escapes.
   - [x] `ord`, `chr`, `digit_value` and ASCII character predicates.
   - [x] String indexing, string iteration and `str.get` return `char`.
   - [x] `str.chars` materializes an `arr[char]`.
   - [x] Native `char` methods.
   - [x] Character concatenation, ordering, hashing and casts.
   - String slicing remains a `str`, and spread over a string yields `char`.
   - Plan: `docs/phase-3d-character-type/README.md`

10. [ ] Debugger.
    - Depends on stable source spans and a debug adapter design.

11. [ ] TLS, HTTP/2 and WebSockets.
    - Platform work for the HTTP module.

12. [ ] FFI handles and `extern type`.
    - The `handle` type exists. The registry and host callback design still need work.

13. [ ] Performance work and bytecode VM.
    - Profile the tree-walker first.
    - Plan: `docs/phase-4b-bytecode-vm/README.md`.
    - Target versions: powang `0.21.0`, powang-lsp `0.27.0`.
    - Keep the tree-walker as the reference engine until differential parity.
    - The VM is opt-in before it becomes the default engine.

## Tooling

- [ ] Standalone formatter as `powang format`.
- [ ] Standalone linter as `powang lint`.
- [ ] `project.format.po` configuration.
- [ ] LSP calls the standalone formatter and linter.
- [x] LSP-only `undef type` display for uninitialized typed variables.
- [x] LSP trait completion that inserts the full trait method signature.
- [ ] Debugger and debug adapter.
- [x] Package registry client.

### `undef` display convention

- `undef` is the internal type for an empty variadic argument list.
- It is not a user-annotatable type.
- The LSP displays an uninitialized typed variable as `undef type`.
  - `x: int` displays as `x: undef int`.
  - `handler: fun[int, int]` displays as `handler: undef fun[int, int]`.
- The runtime display of an undefined value should use `undef`, for example `<int: undef>` instead of `<int: undefined>`.
- This display convention is separate from the language type system.

### `project.format.po` design

The formatter configuration uses the same discovery pattern as `project.po`.

`Project` is now a fully integrated built-in object type. Its fields live in the `BUILTIN_OBJECT_TYPES` registry, which drives the checker, runtime and LSP. A formatter configuration can extend that registry or add a new built-in object type.

Candidate shape:

```po
module project;

export project: Project = Project.[
    format >> Format.[
        indentWidth >> 4,
        useTabs >> false,
        maxLineWidth >> 100,
        trailingCommas >> true,
        alignContinuation >> false,
    ],
];
```

Open questions:

- Add a `format` field to `Project`, or introduce a dedicated `Format` type with its own export.
- Decide whether formatting settings belong in `project.format.po` only, or also in `project.po`.
- The formatter must work without the file by using stable defaults.

## Correctness and cleanup

- [ ] Fix the unreachable duplicated `load_config` block after `return True` in `src/config.py`.
- [ ] Decide whether `examples/example.ignore.po` should be tracked or deleted. It is ignored by `.gitignore` but present on disk.
- [ ] Add parser and checker fuzz tests.
- [ ] Add Windows, macOS and Linux path and encoding tests.
- [ ] Add golden diagnostic snapshots for the LSP.
- [ ] Add a standalone benchmark corpus and performance baselines.
- [ ] Document the `project.format.po` schema when the formatter lands.

## Recently completed

- [x] Phase 1 correctness and guardrails.
- [x] Phase 2A loops, labels, slicing, annotations, frames, spawned methods and constant-condition simplification.
- [x] Phase 2B1 function types and lambdas.
- [x] Phase 2B2 variadics, explicit type arguments, spread and `undef type` display.
- [x] Phase 2B3 match destructuring, range patterns, exhaustiveness and unreachable case warnings.
- [x] Phase 2C structural traits, default methods, generic constraints and trait-qualified dispatch.
- [x] `Project` built-in object type, `project.po` member access and documentation.
- [x] Project runtime templates, implicit module import and LSP user-type highlighting.
- [x] Phase 2D cross-module type checking, qualified types and imported traits.
- [x] LSP `0.16.1` hover syntax highlighting with `powang` fenced code blocks.
- [x] Plain-text hover prose with no markdown bold or inline code spans.
- [x] Examples for all Phase 2A, Phase 2B1 and Phase 2B2 features.
