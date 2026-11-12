# Phase 4B Implementation Index

Purpose: map the V0 to V10 bytecode VM plans, the N0 native milestone, their dependency order, version strategy and commit convention.

This index is the entry point for the implementation plan set. The design documents in the parent directory define language semantics. The binding interface contract is `docs/phase-4b-bytecode-vm/implementation/00-contracts.md`. Each phase file is written to stand alone. A reader can open one phase file, implement it, and use the design documents only as the semantic reference.

## 1. How to read this plan set

Read in this order:

1. `00-index.md` for the phase map and shared conventions.
2. `00-contracts.md` for exact module names, signatures and invariants.
3. The phase file for the work you are implementing.
4. The design documents named in that phase file when you need the full semantic rule.

Do not skip the contracts file. It fixes names that tests and cross module callers rely on. Do not rename a public function without updating the contract file in the same change.

Each phase file uses the same section order:

- Title and one line purpose.
- Objective.
- Prerequisites.
- Deliverables, grouped by file and by language feature.
- Task checklist, one atomic commit per box.
- Lowering table for the constructs added in that phase.
- Runtime semantics notes for shared helpers.
- Acceptance criteria.
- Verification commands.
- Differential test corpus.
- Golden disassembly cases.
- Atomic commit plan.
- Risks and rollback.
- Exit gate.

## 2. Phase map

| File | Phase | Scope | Entry gate | Exit gate |
|---|---|---|---|---|
| `V0-contracts-and-scaffold.md` | V0 | Package skeleton, opcode registry, image codec, builder, verifier, disassembler, engine flag, differential harness | Design set complete, baseline suite green | Trivial literal and arithmetic programs run on both engines, no existing test changes |
| `V1-core-expressions-and-control-flow.md` | V1 | Literals, variables, globals, arithmetic, comparison, logic, if, loops, break, continue, blocks, returns, spans, runtime errors | V0 closed | Core language tests pass on the VM with zero differential mismatches |
| `V2-functions-and-calls.md` | V2 | Functions, expression bodies, first class functions, lambdas, closures, defaults, named arguments, overloads, variadics, type arguments, spread, recursion, stack limits | V1 closed | Function, lambda and variadic suites pass on both engines |
| `V3-containers-strings-and-native-methods.md` | V3 | Arrays, tuples, maps, sets, indexing, slicing, iteration, copy on write, strings, characters, interpolation, builtins, native methods, file and task builtin IDs | V2 closed | Container, string, character and native method suites pass on both engines |
| `V4-user-types-enums-and-operator-overloading.md` | V4 | Type declarations, constructors, fields, access control, instance and static methods, copy constructors, enums, operator traits, comparison dispatch, const and element locks | V3 closed | Type construction, access control and operator overloading suites pass on both engines |
| `V5-traits-and-generics.md` | V5 | Trait declarations, required and default methods, trait annotations, trait qualified methods and calls, generic constraints, conflict and ambiguity errors | V4 closed | Trait and generic suites pass on both engines |
| `V6-modules-project-and-packages.md` | V6 | Module declarations, built in, relative and path imports, aliases, wildcard imports, exports, cross module types and traits, project configuration, implicit project, package resolution, extern functions, module cycle errors | V5 closed | Module, package, project and cross module suites pass on both engines |
| `V7-errors-and-references.md` | V7 | Error values, try, catch, finally, error frames and positions, postfix question mark propagation, references, reference parameters, reference pipelines, reference lifetime checks | V6 closed | Error and reference suites pass on both engines, runtime error text matches exactly |
| `V8-async-and-tasks.md` | V8 | Async declarations and lambdas, lazy tasks, spawn and await, waits, cancellation, status, task errors and cleanup, top level await, worker pool limits | V7 closed | Async and task suites pass on both engines, cleanup tests pass under repeated starts and shutdowns |
| `V9-parity-and-default-switch.md` | V9 | Full differential suite, all examples, all error snapshots, disassembler and trace documentation, optional cached images, opt in release, default switch | V8 closed | One release opt in with zero mismatches, then one release default with tree fallback, no LSP change |
| `V10-native-vm-contract.md` | V10 | Native ABI header and JSON contract, runtime limits, host memory and async boundaries | V9 released | The native contract is generated from the registry and covered by tests |
| `N0-native-cpp17-build-plan.md` | N0 | Native C++17 runtime, `PWB1` reader, verifier, disassembler, generated opcode table, in-memory `temp.cpp` build, integrated `g++` driver | V10 gate green | Native `print(1 + 2);` writes exactly `3` with no trailing newline, exit code `0`, disassembly parity with the Python disassembler |

The N0 to N6 native milestones are tracked separately from the V0 to V10 Python VM gates. N0 is gate green. N1 to N6 are planned in `N0-native-cpp17-build-plan.md`. The Python VM remains the default engine.

## 3. Dependency order

The gate order is strict:

1. V0 must close before V1 starts.
2. V1 must close before V2 starts.
3. V2 must close before V3 starts.
4. V3 must close before V4 starts.
5. V4 must close before V5 starts.
6. V5 must close before V6 starts.
7. V6 must close before V7 starts.
8. V7 must close before V8 starts.
9. V8 must close before V9 starts.
10. V9 must close before V10 starts.
11. V10 must close before N0 starts. N0 is gate green. N1 to N6 follow the milestone order in `N0-native-cpp17-build-plan.md`.

Work may overlap inside one phase only when the interfaces in `00-contracts.md` are frozen. A phase gate is not green until its differential corpus reports zero mismatches and the existing suite is unchanged.

Parallel work that does not change a gate:

- The benchmark corpus in `src/vm/bench.py` can start after V5.
- The disassembler table rendering can start after V3.
- Trace event coverage can start after V4.
- Documentation updates can follow each phase without waiting for V9.

## 4. Version strategy

- The bytecode format version is `1` from V0. It changes only when an opcode is renumbered or an image table changes shape.
- The language version for the implementation train is `0.21.0` for V0 through V9.
- `0.21.0` is the opt in release. The VM is available through `--engine=vm`, `POWANG_ENGINE=vm` and `project.engine >> "vm"`.
- The target tooling version is powang-lsp `0.27.0`. The LSP itself keeps the same parser and checker.
- `0.22.0` is the default switch release. The VM is the default engine and the tree walker remains the reference engine and the fallback.
- The tree walker remains available as `--engine=tree` and `POWANG_ENGINE=tree` for at least one release after the default switch.
- V10 defines the native ABI contract for a separate native implementation.
- N0 is implemented at `0.22.0` as a milestone, not a release. The plan targets `0.23.0` for N0 to N2. N1 to N6 remain planned.
- A cached image is valid only when the format version, language version, source hash, compiler version, package version, module dependency hashes and engine feature flags all match.

## 5. Commit convention

Implementation commits use a conventional commit prefix with the phase scope:

- `vm(v0): ...`
- `vm(v1): ...`
- `vm(v2): ...`
- `vm(v3): ...`
- `vm(v4): ...`
- `vm(v5): ...`
- `vm(v6): ...`
- `vm(v7): ...`
- `vm(v8): ...`
- `vm(v9): ...`

Documentation only commits use `docs(phase-4b): ...`.

One task checklist box equals one commit. Do not combine two boxes in one commit. Do not mark a box complete before its verification command passes.

## 6. Definition of done summary

The VM is complete when all of these are true:

1. The full Powang test suite passes on the VM.
2. The full example suite produces identical output on both engines.
3. The differential harness reports zero mismatches.
4. Runtime error text and source positions match the tree walker.
5. Every opcode has a verifier rule and at least one test.
6. Every AST node kind has a documented lowering rule.
7. The disassembler renders every program image table.
8. Trace mode can follow a call stack and an error path.
9. Copy on write preserves value semantics under tests.
10. Modules, packages, project configuration and externs work.
11. Async tasks, cancellation and cleanup work.
12. The engine flag selects tree or VM without changing program behavior.
13. The VM remains opt in until one full release has zero mismatches.
14. The VM becomes the default only after the compatibility gates pass.
15. The LSP keeps using the same parser and checker and produces the same diagnostics.

## 7. Status tracking

`STATUS.md` is the live progress tracker. Update it in the same commit that closes a task checklist box. A phase status moves through these values:

- `not started`
- `in progress`
- `blocked`
- `gate green`
- `released`

A phase is `gate green` only when its exit gate checklist is fully checked. A phase is `released` only when its version is published.

## 8. Feature placement decisions

The rollout phases name most features. These placements resolve features that the phase summaries do not name explicitly. Each placement is repeated in the phase file that owns the work.

| Feature or opcode | Phase | Reason |
|---|---|---|
| `MATCH` and pattern descriptors for literal, binding, wildcard, range, array, tuple, map and set patterns | V3 | Container and range patterns need the container heap model |
| `MATCH` for object and enum patterns, guards and expression position match | V4 | Object and enum patterns need the type table |
| Destructuring declarations for arrays and tuples | V3 | Uses `DESTRUCTURE` and container indexing |
| Destructuring declarations for objects | V4 | Uses field IDs and object layouts |
| Value pipelines with `:>` | V2 | They lower to calls and method calls |
| Reference pipelines with `&>` | V7 | They need reference values and lifetime checks |
| Safe member access with `?.` and coalesce with `??` | V4 | They need member tables and nova checks |
| `ROT`, `LOAD_NAME`, `STORE_NAME`, `TO_BOOL`, `TYPE_CHECK_VALUE` | V1 | Core stack, name and type operations |
| `REVERSE` and `CAST` | V3 | Unary reverse and explicit casts cover strings, characters and containers |
| `CALL_ASYNC_METHOD` | V8 | Async method dispatch needs the task model |
| `src/vm/heap.py` | Not created | The Python reference VM uses the existing `PowangAny` classes from `src.powang_types`. Copy on write lives in `src/vm/values.py` and container mutation lives in `src/vm/interpreter.py`. |

Const declarations are compile time macros. The parser substitutes the stored expression at each use site. The compiler never creates a runtime global for a const. `SET_LOCKS` handles runtime const and element locks that come from type expressions.

## 9. Open questions

- The design documents do not assign `MATCH` to a named phase. This plan assigns it to V3 and V4 as recorded above.
- The design documents do not assign destructuring declarations to a named phase. This plan assigns them to V3 and V4 as recorded above.
- The design documents say the disassembler and trace mode must be documented in V9. This plan treats the V9 phase file and the `powang vm --help` output as the canonical reference until a dedicated user guide is scheduled.
- The contracts name `project.engine` as an engine source. The `Project` value type has no `engine` field. This plan treats it as project metadata read by the host before the `Project` value is built. Confirm this interpretation before V6.
- The native VM language choice, the native string storage and the extern C ABI remain open decisions from section 23.2 of the design. They do not block V0 through V9 on the Python reference VM.
