# Powang TODO

Last updated: 2026-11-08

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done.

## Next step

- [ ] Phase 2B2: variadics and spread.
  - Plan: `docs/phase-2b2-variadics-and-spread/README.md`
  - Includes explicit type arguments, prefix `...` spread, zero-argument `undef` inference and overload rules.
  - Companion LSP change: uninitialized typed variables display as `undef[type]`.
  - Target versions: powang `0.11.0`, powang-lsp `0.17.0`.

## Language features in order

1. [ ] Variadics and spread.
   - `fun sum[T](values: T...): T`
   - `sum(...values)`
   - `sum(...[1, 2, 3])`
   - `sum[int](1, 2, 3)`
   - Zero variadic arguments infer `undef`.
   - Explicit type arguments select the template overload before concrete overloads.

2. [ ] Match destructuring and exhaustiveness.
   - Array patterns.
   - Tuple patterns.
   - Object patterns.
   - Range patterns.
   - Enum and boolean exhaustiveness warnings.
   - Unreachable case warnings.

3. [ ] Traits and interfaces.
   - Structural satisfaction.
   - Trait annotations.
   - Trait-qualified methods for signature conflicts.
   - LSP completion after `Trait.`.
   - Decision: a single structural method with a compatible signature satisfies every trait that requires that method. No `Trait.method` is needed when the signatures are identical.
   - `Trait.method` is only needed when two traits require the same method name with different signatures, or when the same signature needs trait-specific behavior.

4. [ ] Range patterns.
   - Ranges are currently sugar for C-style `for`. This item is about pattern ranges such as `case 0 >> 10 >> ...`, not loop ranges.

5. [ ] Cross-module type checking.
   - Check imports and exports across files.
   - Report errors at the importing call site.

6. [ ] Async and await.
   - Needs a scheduler and suspension design.
   - `spawn` remains the parallel task primitive.

7. [ ] Package registry and dependency resolver.
   - Needs a manifest, lock file and cache design.

8. [ ] Operator overloading through traits.
   - Depends on traits.

9. [ ] Debugger.
   - Depends on stable source spans and a debug adapter design.

10. [ ] TLS, HTTP/2 and WebSockets.
    - Platform work for the HTTP module.

11. [ ] FFI handles and `extern type`.
    - The `handle` type exists. The registry and host callback design still need work.

12. [ ] Performance work.
    - Profile first.
    - A bytecode VM is not planned until profiling proves the tree-walker is the bottleneck.

## Tooling

- [ ] Standalone formatter as `powang format`.
- [ ] Standalone linter as `powang lint`.
- [ ] `project.format.po` configuration.
- [ ] LSP calls the standalone formatter and linter.
- [ ] LSP-only `undef[type]` display for uninitialized typed variables.
- [ ] LSP trait completion that inserts the full trait method signature.
- [ ] Debugger and debug adapter.
- [ ] Package registry client.

### `undef` display convention

- `undef` is the internal type for an empty variadic argument list.
- It is not a user-annotatable type.
- The LSP displays an uninitialized typed variable as `undef[type]`.
  - `x: int` displays as `x: undef[int]`.
  - `handler: fun[int, int]` displays as `handler: undef[fun[int, int]]`.
- The runtime display of an undefined value should use `undef`, for example `<int: undef>` instead of `<int: undefined>`.
- This display convention is separate from the language type system.

### `project.format.po` design

The formatter configuration uses the same discovery pattern as `project.po`.

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
- [x] LSP `0.16.1` hover syntax highlighting with `powang` fenced code blocks.
- [x] Plain-text hover prose with no markdown bold or inline code spans.
- [x] Examples for all Phase 2A and Phase 2B1 features.
