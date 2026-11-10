# Implementation, Rollout, and Decisions

Purpose: Lay out implementation phases, migration, risks, completion criteria, decisions, and acceptance checks.

## 17. Implementation phases

### V0: Contracts and scaffold

Deliverables:

- Opcode registry.
- Program image structures.
- Instruction encoder and decoder.
- Verifier skeleton.
- Disassembler skeleton.
- `--engine=vm` flag.
- Differential harness.
- Tests for encoding and verification.

Gate:

- Trivial literal and arithmetic programs run on both engines.
- No existing test changes behavior.

### V1: Core expressions and control flow

Deliverables:

- Literals, variables, globals.
- Arithmetic, comparison and logic.
- If, else, loop, for range, break and continue.
- Blocks and returns.
- Copy semantics for scalars.
- Source spans and runtime errors.

Gate:

- Core language tests pass on the VM.
- Differential harness reports zero mismatches for core tests.

### V2: Functions and calls

Deliverables:

- Function declarations and expression bodies.
- First-class function values.
- Closures and captures.
- Defaults, named arguments and overloads.
- Variadics, explicit type arguments and spread.
- Recursion and stack limits.

Gate:

- Function, lambda and variadic test suites pass on both engines.

### V3: Containers, strings and native methods

Deliverables:

- Arrays, tuples, maps and sets.
- Indexing, slicing and iteration.
- Copy-on-write.
- Strings and characters.
- Interpolation.
- Builtins.
- Native methods for arr, map, str, char, tup and set.
- File and task builtins at the host boundary.

Gate:

- Container, string, character and native method suites pass on both engines.

### V4: User types, enums and operator overloading

Deliverables:

- Type declarations.
- Constructors.
- Fields and access control.
- Instance and static methods.
- Copy constructors.
- Enums.
- Operator traits and comparison dispatch.
- Const and element locks.

Gate:

- Type construction, access control and operator overloading suites pass on
  both engines.

### V5: Traits and generics

Deliverables:

- Trait declarations.
- Required and default methods.
- Trait annotations.
- Trait-qualified methods and calls.
- Generic constraints.
- Trait conflict and ambiguity errors.

Gate:

- Trait and generic suites pass on both engines.

### V6: Modules, project and packages

Deliverables:

- Module declarations.
- Built-in, relative and path imports.
- Aliases and wildcard imports.
- Exports.
- Cross-module types and traits.
- Project configuration and implicit `project`.
- Package module resolution.
- Extern functions.
- Module cycle errors.

Gate:

- Module, package, project and cross-module suites pass on both engines.

### V7: Errors and references

Deliverables:

- Error values.
- Try, catch and finally.
- Error frames and source positions.
- Postfix `?` propagation.
- Reference expressions and parameters.
- Reference pipelines.
- Reference lifetime checks.

Gate:

- Error and reference suites pass on both engines.
- Runtime error text matches the tree-walker exactly.

### V8: Async and tasks

Deliverables:

- Async declarations and lambdas.
- Lazy tasks.
- Spawn and await.
- Task waits, cancellation and status.
- Task errors and cleanup.
- Top-level await.
- Worker pool limits.

Gate:

- Async and task suites pass on both engines.
- Task cleanup tests pass under repeated starts and shutdowns.

### V9: Parity and default switch

Deliverables:

- Full differential suite passes.
- All examples pass.
- All error snapshots pass.
- Disassembler and trace mode are documented.
- Cached program images are optional.
- The VM becomes the default engine.

Gate:

- One release with the VM as opt-in and zero mismatches.
- One release with the VM as default and the tree-walker available as a
  fallback.
- No LSP behavior changes.

## 20. Migration and compatibility

### 20.1 Engine selection

Add an engine option:

- `--engine=tree` runs the tree-walker.
- `--engine=vm` runs the bytecode VM.
- `POWANG_ENGINE` supplies a default.
- `project.engine` can select an engine for a project.

The default is `tree` until the VM reaches parity.

### 20.2 Compatibility gates

A VM release is blocked when:

- Any existing test differs.
- Any example output differs.
- Any runtime error message differs.
- Any LSP diagnostic differs.
- Any package or module test fails.
- Any async cleanup test fails.

### 20.3 Bytecode versioning

The program image carries a format version and a language version. A cached
image is invalid when either version changes, when the source hash changes or
when the compiler version changes.

### 20.4 Cached images

Caching is optional. If enabled, images live under `.powang/cache/bytecode/`.
The cache key includes:

- Resolved source path.
- Source SHA-256.
- Language version.
- Compiler version.
- Module dependency hashes.
- Engine feature flags.

A corrupted cache entry is ignored and recompiled.

### 20.5 Tree-walker retirement

The tree-walker remains available for at least one release after the VM becomes
the default. It is the reference oracle for bug reports and differential tests.
Retirement requires a separate decision.

## 21. Risks and open questions

### 21.1 Integer range

The tree-walker uses Python integers with no fixed range. The native VM must
either use a bigint fallback or define a fixed integer width. The preferred
option is inline 63-bit integers with a heap bigint fallback. This preserves
current behavior and gives fast paths.

### 21.2 String representation

UTF-32 gives O(1) indexing and simple character semantics. It uses more memory
for ASCII-heavy text. UTF-8 with a code point index is more compact but more
complex. The reference VM can use Python strings while the native VM chooses
UTF-32 for correctness first and considers a mixed representation later.

### 21.3 Copy-on-write and references

Copy-on-write must not break reference parameters or reference pipelines. A
reference to an element must force uniqueness before mutation or write through
the shared object in a way that matches value semantics. This is a high-risk
area and needs dedicated tests.

### 21.4 Overload resolution

The tree-walker resolves overloads at runtime with a scoring function. The VM
must use the same scoring. If the compiler resolves too early, dynamic `any`
values may choose a different overload. The safe rule is to emit an overload
set call whenever any argument is dynamic.

### 21.5 Async scheduling

The current model uses lazy tasks and worker tasks without coroutine
suspension. A future coroutine model would require a new bytecode version, a
new task state machine and a new scheduler. This plan deliberately preserves
the current model.

### 21.6 Error compatibility

Runtime error strings are part of the user experience. The VM must reuse the
same error constructors and formatters. A separate VM error format would be a
regression.

### 21.7 Module cache and packages

Package versions and lock files must be part of the module identity. A module
with the same path but a different package version must not share a cache
entry. The module loader already resolves package paths. The VM must key the
cache by resolved path and package version.

### 21.8 Debugger integration

The debugger needs instruction boundaries and source spans. Optimized
superinstructions can make stepping confusing. The VM should keep a debug
image with unoptimized instructions and source spans, and a separate release
image for production.

### 21.9 Extern ABI

Extern functions cross the VM boundary. The ABI must define value conversion,
error propagation and handle ownership. The first version can reuse the Python
function bridge. The native VM needs a stable C ABI.

### 21.10 REPL state

The REPL needs persistent globals, types, traits and modules. The VM must
support incremental compilation and rollback on a failed cell. This is a
separate compile context from a file program.

## 22. Definition of done

The VM is complete when:

1. The full Powang test suite passes on the VM.
2. The full example suite produces identical output.
3. The differential harness reports zero mismatches.
4. Runtime error text and source positions match.
5. Every opcode has a verifier rule and at least one test.
6. Every AST node kind has a documented lowering rule.
7. The disassembler renders every program image table.
8. The trace mode can follow a call stack and error path.
9. Copy-on-write preserves copy semantics under tests.
10. Modules, packages, project configuration and externs work.
11. Async tasks, cancellation and cleanup work.
12. The engine flag selects tree or VM without changing program behavior.
13. The VM remains opt-in until one full release has zero mismatches.
14. The VM becomes the default only after the compatibility gates pass.
15. The LSP continues to use the same parser and checker and produces the same
    diagnostics.

## 23. Decision log

### 23.1 Locked decisions

| Decision | Choice | Reason |
|---|---|---|
| Execution style | Stack based | Simple lowering and verification |
| Oracle | Tree-walker | It defines current semantics |
| Reference implementation | Python | Fast iteration and differential testing |
| Production target | Native VM | Performance and portability |
| Bytecode version | 1 | Versioned from the first image |
| Integer model | Inline 63-bit plus bigint fallback | Preserves current integer behavior |
| String model | Code point based | Matches `char` and indexing semantics |
| Copy model | Copy-on-write with value semantics | Correctness with better allocation behavior |
| Async model | Lazy tasks and worker tasks | Matches the current language |
| Migration | Opt-in engine flag then default | Prevents a risky flag day |
| LSP | Unchanged frontend | The VM is a runtime backend |

### 23.2 Open decisions

| Decision | Options | Needed by |
|---|---|---|
| Native language | Rust or C | Native VM kickoff |
| Cached images | Off by default or on by default | V0 |
| Debug opcode | Side table only or explicit trap opcode | Debugger integration |
| Extern ABI | Python bridge only or stable C ABI | V6 |
| Integer overflow | Error or wrap when bigint is disabled | Native VM kickoff |
| String storage | UTF-32 only or mixed UTF-8 plus index | Native VM kickoff |
| Task scheduler | Fixed worker pool or adaptive pool | V8 |
| Bytecode optimization | Peephole only or superinstructions | V9 |

## Appendix E: Recommended module layout

```text
src/vm/
    __init__.py
    opcodes.py        # opcode registry and operand definitions
    image.py          # program image and code objects
    compiler.py       # AST lowering
    builder.py        # instruction builder and labels
    verifier.py       # stack and metadata verification
    interpreter.py    # execution loop
    values.py         # value tags and helpers
    heap.py           # heap objects
    frames.py         # frames and handler stacks
    dispatch.py       # call, method, trait and operator dispatch
    errors.py         # VM error unwinding and formatting
    modules.py        # module cache and initialization
    tasks.py          # lazy and worker tasks
    host.py           # builtins, native methods, externs and I/O
    disasm.py         # disassembler
    trace.py          # trace mode
    tests/            # VM unit tests
```

The existing `src/` modules remain the frontend and the tree-walker. The VM is
an additional backend, not a replacement for the parser or the checker.

## Appendix F: Acceptance checklist

- [ ] Opcode registry is the single source of truth.
- [ ] Every AST node kind has a lowering rule.
- [ ] Every opcode has a verifier rule.
- [ ] Every opcode has at least one unit test.
- [ ] Every feature has a differential test.
- [ ] Error text and positions match the tree-walker.
- [ ] Copy semantics match the tree-walker.
- [ ] Module and package behavior match the tree-walker.
- [ ] Async behavior matches the tree-walker.
- [ ] The disassembler is complete.
- [ ] The trace mode is useful.
- [ ] The engine flag is documented.
- [ ] The VM is opt-in before it is default.
- [ ] The LSP remains unchanged.
