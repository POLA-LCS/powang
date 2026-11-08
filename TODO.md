# Powang TODO

Last updated: 2026-11-08

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done.

## Next step

- [ ] Phase 2C: traits and interfaces.
  - Plan: `docs/phase-2c-traits-and-interfaces/README.md` (to be written)
  - Structural satisfaction.
  - Trait annotations.
  - Trait-qualified methods for signature conflicts.
  - Default trait method bodies checked against the declared contract.
  - LSP completion after `Trait.`.
  - Target versions: powang `0.13.0`, powang-lsp `0.19.0`.

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

3. [ ] Traits and interfaces.
   - Structural satisfaction.
   - Trait annotations.
   - Trait-qualified methods for signature conflicts.
   - LSP completion after `Trait.`.
   - Decision: a single structural method with a compatible signature satisfies every trait that requires that method. No `Trait.method` is needed when the signatures are identical.
   - `Trait.method` stays because two traits can require the same method name with different return types or different semantics. Return-type-only distinctions cannot be resolved by structural matching alone.
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
- [x] LSP-only `undef type` display for uninitialized typed variables.
- [ ] LSP trait completion that inserts the full trait method signature.
- [ ] Debugger and debug adapter.
- [ ] Package registry client.

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
- [x] LSP `0.16.1` hover syntax highlighting with `powang` fenced code blocks.
- [x] Plain-text hover prose with no markdown bold or inline code spans.
- [x] Examples for all Phase 2A, Phase 2B1 and Phase 2B2 features.
