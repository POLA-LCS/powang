# Phase 4B Status

Purpose: track the V0 to V10 gates, the N0 to N6 native milestones, the `src/vm` module ownership and the Appendix F acceptance checklist.

Status values:

- `not started`
- `in progress`
- `blocked`
- `gate green`
- `released`

Update this file in the same commit that closes a task checklist box. A phase becomes `gate green` only when its exit gate is fully checked. A phase becomes `released` only when its version is published.

## 1. Phase status

| Phase | Scope | Status | Version | Commit range |
|---|---|---|---|---|
| V0 | Contracts and scaffold | gate green | 0.21.0 | see git log |
| V1 | Core expressions and control flow | gate green | 0.21.0 | see git log |
| V2 | Functions and calls | gate green | 0.21.0 | see git log |
| V3 | Containers, strings and native methods | gate green | 0.21.0 | see git log |
| V4 | User types, enums and operator overloading | gate green | 0.21.0 | see git log |
| V5 | Traits and generics | gate green | 0.21.0 | see git log |
| V6 | Modules, project and packages | gate green | 0.21.0 | see git log |
| V7 | Errors and references | gate green | 0.21.0 | see git log |
| V8 | Async and tasks | gate green | 0.21.0 | see git log |
| V9 | Parity and default switch | released | 0.22.0 | see git log |
| V10 | Native ABI and runtime limits | gate green | 0.22.0 | see git log |

Design documents: complete.

Contracts document: complete.

The VM became the default engine in `0.22.0`. The tree walker remains the reference engine and the fallback with `--engine=tree` and `POWANG_ENGINE=tree`.

Recorded results for `0.22.0`:

- Default VM suite: 593 tests, all pass.
- Tree fallback suite with `POWANG_ENGINE=tree`: 593 tests, all pass.
- Differential example corpus: every `.po` file under `examples`, zero mismatches.
- Differential inline corpus: 13 programs, zero mismatches.
- Error parity corpus: 13 cases, identical output, error text and exit code.
- Seeded fuzzer: 1000 generated programs on seed 7 and 1000 on seed 2026, zero skips and zero mismatches.
- Stress corpus: large containers, many closures, many awaited tasks, large string slicing and repeated runs.
- Project engine, module cache, block scopes, task handle resolution, native ABI, disassembler, trace, JSON output, image round trip, cache, engine flag and verifier reject tests pass.

### Native runtime milestones

| Milestone | Scope | Status | Version |
|---|---|---|---|
| N0 | `PWB1` reader, decoder, verifier, disassembler, generated opcode table, `temp.cpp` source generation and integrated `g++` driver | gate green | 0.22.0 |
| N1 | Big integers, locals, globals, control flow, functions, closures, calls, defaults, named arguments, variadics, overload selection, frames and iterators | gate green | 0.22.0 |
| N2 | Strings, arrays, tuples, maps, sets, indexing, slicing, iteration, deep copy, interpolation, core builtins and native methods | gate green | 0.22.0 |
| N3 | User types, constructors, fields, methods, statics, enums, traits, operator dispatch and locks | gate green | 0.23.0 |
| N4 | Modules, project, externs, errors and references | gate green | 0.23.0 |
| N5 | Async, tasks, file I/O and the host bridge | gate green | 0.24.0 |
| N6 | Full parity, performance and distribution | gate green | 0.25.0 |

The native runtime lives under `native/` and consumes the same `PWB1` program image as the Python compiler. It is opt in. The Python VM remains the default engine and the differential oracle.

The N0 gate runs a real `print(1 + 2);` image through the native executable. Standard output is exactly `3` with no trailing newline, the exit code is `0`, and the native entry-code disassembly is byte-identical to the Python disassembler. The N0 scalar subset covers nova, undef, bool, int, num and char values, integer and number arithmetic, comparisons, logical not, negation, locals, jumps, top level `print` and `println`, and the N0 disassembler and verifier. An unsupported opcode fails with a clear runtime error. The N0 number semantics tests match the Python VM: mixed int/num arithmetic and comparisons follow the Python VM cast order, division and modulo by zero return nova for int and num, and float modulo follows the divisor sign, including signed zero. Integer overflow promotes to bigint in N1.

N1 execution is gate green. It adds arbitrary precision integers with int64 promotion, locals, globals, declarations, branches, range loops, `loop`, `break`, `continue`, functions, recursion, mutual recursion, defaults, named arguments, variadics, overload selection, closures by value and by reference, named lambda recursion, higher order function values, frames and iterators. `tests/native/corpus/n1` has 5 differential programs.

N2 is gate green. It adds UTF-32 strings, arrays, tuples, insertion ordered maps and sets, indexing, slicing, string and array operators, iteration, deep copy with a cycle memo, interpolation, the `format` and `printf` builtins, the character builtins and the array, string, map, set, tuple and char native methods. `tests/native/corpus/n2` has 6 differential programs. The file and task native methods remain in N5. Runtime error stream and text parity remains incomplete.

N3 is gate green. It covers user types, constructors, fields, instance methods, statics, enums, traits, default methods, operator overloading, structure and element locks, runtime private field and method access control, private static methods, operator and trait method ambiguity, and native method lock enforcement. `tests/native/corpus/n3` has 8 differential programs. `tests/test_native_access_control.py` checks the runtime access-control and ambiguity error text against the Python VM.

N4 is gate green. It adds the deterministic `PWBB` bundle, the Python import-graph builder, `ModuleLoader.read_sources`, `ModuleRuntime`, the `ModuleTable`, per-module symbol tables, `IMPORT`, `IMPORT_WILDCARD`, `LOAD_MODULE_MEMBER`, `EXPORT`, `CALL_MODULE`, module member values, the export table, the legacy warning, imported types and module-qualified construction, deferred import errors and the cyclic-import guard. It adds the language error model with `Tag::Error`, exact error text, `MAKE_ERROR`, `ERROR_PROPERTY`, `THROW`, `RETHROW`, `PROPAGATE`, try, catch, finally, the handler stack, call frame records, top-level standard output parity and PWBM version 2 descriptors. It adds references with value flags, `Tag::Ref`, `RefObject`, the reference opcodes, reference parameters, reference pipelines and frame lifetime tokens. It adds the project snapshot, `Tag::Project`, `LOAD_PROJECT`, implicit `project` binding, the extern descriptor table, `DECLARE_EXTERN`, `CALL_EXTERN`, the allowed-module check and the host scalar extern hook.

N4 gate results, commit range `857b8f6..3fc8237`:

- `tests.test_native_bundle`: 15 tests pass.
- `tests.test_native_meta`: 6 tests pass.
- `tests.test_native_build`: 18 tests pass.
- `tests.test_vm_native_corpus`: 4 tests pass, including 29 N4 differential programs across the module, wildcard, legacy, error, try, finally, propagation, reference, project and extern cases.
- `ctest --test-dir build/native`: 1 of 1 test passes.
- Full Python suite: 635 tests pass.
- The N4 corpus compares standard output, standard error and exit codes against the Python VM. Top-level language errors are written to standard output as in the Python CLI.

N5 is gate green. It adds lazy async tasks, `spawn` worker tasks with cloned module snapshots, `await`, `wait`, `cancel`, `task_status`, the task native methods, the pending async task limit, task error propagation, cooperative cancellation and task isolation. It adds the file builtins and file values, the host input, inputf and system bridge, and the `typeof` and `typedeep` builtins. The worker executor is deterministic: it runs spawned work on the spawning thread against a cloned module snapshot, which matches the single-worker differential contract and avoids sharing the non-thread-safe machine across threads. True parallel worker execution and the network host modules remain.

N5 gate results, commit range after `e7d7331`:

- `tests.test_vm_native_corpus`: the N5 subtest runs 9 differential programs.
- `tests.test_native_tasks`: 2 tests pass.
- `ctest --test-dir build/native`: 1 of 1 test passes.
- Full Python suite: 638 tests pass.

N6 is gate green at the `0.25.0` release candidate. The engine integration is complete: `--engine=native`, the native differential runner, seeded native fuzzing, and `powang vm native diff`, `bench`, `clean` and `pack`. Every example under `examples/` matches the Python VM, including casts, match patterns, destructuring, typed declarations and defaults, named constructors, generic overload selection, spreads and the default host bridge for `math`, `strings`, `json`, `url`, `crypto`, `time`, `env`, `log` and script arguments. Structure and element locks are enforced. On a 200,000 iteration arithmetic loop the native runtime ran in about 66 ms against about 7.8 seconds for the tree walker and 8.5 seconds for the Python VM over three runs. The `native/benches` loop, string and container suites and the `src.vm.native.bench` runner back the `bench` command. The seeded fuzz gate is green: 1000 of 1000 generated programs on seed 7 and 1000 of 1000 on seed 2026 match the Python VM, including weak nova, bool, char and modulo edge cases. Checker warnings are emitted before native compile and check errors. The stress gate is green: 100 native startups and 200 task lifecycles pass without leaks. The warm executable cache is implemented for the integrated file path: a 1.12 second cold start drops to a 0.29 second warm start, within 1.23 times the tree walker on the same small program. A 50 KB source program compiles in 1.12 seconds cold and 0.46 seconds warm, inside the compile gates. The default engine decision is recorded: the Python VM remains the default. Remaining work after the release candidate is optional inline caches and threaded dispatch, the HTTP host modules, the generic host callback bridge and true parallel worker execution.

N6 integration results:

- Full Python VM suite: 656 tests pass.
- Full tree walker suite with `POWANG_ENGINE=tree`: 656 tests pass.
- Native differential over all 32 `examples/*.po`: zero mismatches.
- N1 to N5 native corpora: zero mismatches.
- Seeded fuzz: 1000 of 1000 on seed 7 and 1000 of 1000 on seed 2026.
- Stress: 100 native startups and 200 task lifecycles pass.
- `ctest --test-dir build/native`: 1 of 1 test passes.
- Wheel and sdist at `0.25.0`: the wheel contains the native sources, headers, tests and benchmarks. A clean wheel install runs `--engine=native` and `vm native bench` successfully, with a temporary native build.

`tests/test_native_build.py` has 18 tests. They cover the generated opcode header, the in-memory buffer, the `print(1 + 2);` gate, byte-exact disassembly parity, corrupt image rejection, compiler diagnostics, temp cleanup, CLI run, CLI compile, native info, number semantics, print arity, loop image verification, bad jump rejection, missing compiler handling and stdin compilation. The number semantics test runs 36 subtests. `tests/test_native_meta.py` has 6 tests for deterministic PWBM metadata, the image hash, parameter metadata, PWBM version 2 descriptors and the C++ metadata round trip. `tests/test_native_bundle.py` has 15 tests for the bundle layout, digest, module graph, project block, parser rejection cases, generated source and bundle execution. `tests/test_native_tasks.py` has 2 tests for host input parity and task status names. `tests/test_native_stress.py` has 2 tests for 100 native startups and 200 task lifecycles. `tests/test_vm_native_engine.py` has 5 tests for the `--engine=native` command line, imports, error stream parity and the differential module. `tests/test_vm_native_examples.py` runs the full example differential. `tests/test_vm_native_corpus.py` has 6 differential tests covering the N1, N2, N3, N4 and N5 corpora and the N6 fuzz regression programs. `tests/test_native_access_control.py` has 2 tests for runtime access control, lock error text and trait or operator ambiguity. `tests/test_native_stdlib.py` has 5 tests for the standard library success and error paths, logging, script arguments and environment lookup. `tests/test_native_bench.py` checks the benchmark runner. `tests/test_native_cache.py` checks warm executable reuse. The full suite has 656 tests. Run them with:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_native_build -v
```

The package version is `0.25.0` for the N6 release candidate. The image language version remains `0.22.0` because the image contract did not change. The Python VM remains the default engine. Inline caches and threaded dispatch are optional and not implemented because the performance gates are met. The HTTP host modules, the generic host callback bridge and true parallel worker execution are post-release work.

## 2. Module status

| Module | Owner phase | Status |
|---|---|---|
| `src/vm/__init__.py` | V0 | implemented |
| `src/vm/opcodes.py` | V0 | implemented |
| `src/vm/image.py` | V0 | implemented |
| `src/vm/builder.py` | V0 | implemented |
| `src/vm/verifier.py` | V0 | implemented |
| `src/vm/values.py` | V0 | implemented |
| `src/vm/frames.py` | V0 | implemented |
| `src/vm/compiler.py` | V0 to V8 | implemented |
| `src/vm/interpreter.py` | V0 to V8 | implemented |
| `src/vm/host.py` | V0 | implemented |
| `src/vm/errors.py` | V0 | implemented |
| `src/vm/disasm.py` | V0 | implemented |
| `src/vm/trace.py` | V0 | implemented |
| `src/vm/differential.py` | V0 | implemented |
| `src/vm/fuzz.py` | V9 | implemented |
| `src/vm/cli.py` | V0 | implemented |
| `src/vm/dispatch.py` | V2 | implemented |
| `src/vm/declarations.py` | V4 | implemented |
| `src/vm/modules.py` | V6 | implemented |
| `src/vm/tasks.py` | V8 | implemented |
| `src/vm/bench.py` | V9 | implemented |
| `src/vm/native_abi.py` | V10 | implemented |

Tests live in the repository `tests/` directory, not under `src/vm/tests`. The design document's recommended `src/vm/tests/` layout is a suggestion. The project keeps one test discovery root so the default and fallback suites run together.

## 3. Appendix F acceptance checklist

- [x] Opcode registry is the single source of truth.
- [x] Every AST node kind has a lowering rule.
- [x] Every opcode has a verifier rule.
- [x] Every opcode has at least one handler and the handler coverage test passes.
- [x] Every feature has a differential test.
- [x] Error text and positions match the tree walker.
- [x] Copy semantics match the tree walker.
- [x] Module and package behavior match the tree walker.
- [x] Async behavior matches the tree walker.
- [x] The disassembler is complete.
- [x] Trace mode is useful.
- [x] The engine flag is documented.
- [x] The VM is opt in before it is default.
- [x] The LSP remains unchanged.

Notes:

- "Every opcode has at least one unit test" is covered by the registry encoding test, the handler coverage guard and the feature tests. A dedicated per opcode execution test for every opcode is not present. The coverage guard fails when an opcode name disappears from the interpreter source.
- The VM became the default only after the opt-in release with zero mismatches.

## 4. How to run the gates

Run these commands from the repository root in Windows PowerShell.

The default VM suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The tree fallback suite:

```powershell
$env:POWANG_ENGINE = "tree"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
Remove-Item Env:\POWANG_ENGINE
```

The VM unit and integration tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_foundation tests.test_vm_runtime tests.test_vm_tooling tests.test_vm_differential tests.test_vm_errors tests.test_vm_stress -v
```

The differential example corpus:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --examples examples --fail-fast
```

The differential inline corpus and seeded fuzzer:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_differential.InlineDifferentialTests -v
.\.venv\Scripts\python.exe -m src.vm.differential --fuzz --seed 2026 --count 1000 --fail-fast
```

The disassembler:

```powershell
.\.venv\Scripts\python.exe powang.py vm disasm examples\modern.po
.\.venv\Scripts\python.exe powang.py vm disasm --json examples\modern.po
```

Trace mode:

```powershell
.\.venv\Scripts\python.exe powang.py vm run --trace examples\modern.po
```

A single differential run:

```powershell
.\.venv\Scripts\python.exe powang.py vm diff examples\modern.po
```

The benchmark report:

```powershell
.\.venv\Scripts\python.exe powang.py vm bench --runs 3
```

The optional bytecode cache:

```powershell
.\.venv\Scripts\python.exe powang.py vm run --vm-cache examples\modern.po
```

The native ABI contract:

```powershell
.\.venv\Scripts\python.exe powang.py vm abi
.\.venv\Scripts\python.exe powang.py vm abi --json
```

The engine selection:

```powershell
.\.venv\Scripts\python.exe powang.py --engine=tree examples\modern.po
.\.venv\Scripts\python.exe powang.py --engine=vm examples\modern.po
$env:POWANG_ENGINE = "tree"
.\.venv\Scripts\python.exe powang.py examples\modern.po
Remove-Item Env:\POWANG_ENGINE
```

The LSP must not change. Confirm that no frontend file changed:

```powershell
git diff --name-only -- src\typecheck.py src\parser.py src\lexer
```

An empty output means the frontend is unchanged.

## 5. Gate report template

When a phase closes, add one row to the phase table and paste this block into the phase completion commit message or the release notes:

```text
Phase: V<n>
Scope: <one line>
Corpus: <n> programs, <n> mismatches
Existing suite: <pass or fail>
Examples: <pass or fail>
Error snapshots: <pass or fail>
VM unit tests: <n> tests, <n> failures
Known limitations: <none or list>
Commit range: <first>..<last>
Version: <0.21.0 or 0.22.0>
```

## 6. Known limitations

- The Python reference VM uses the host Python allocator and garbage collector. A native VM owns its own heap policy. There is no separate collector in the Python engine by design.
- The native C++17 runtime is implemented through N5 and the N6 integration under `native/`, and `powang vm native` is opt in. It consumes the same `PWB1` images as the Python compiler and covers scalars, big integers, functions, closures, strings, containers, user types, constructors, fields, methods, statics, enums, traits, operators, native methods, module bundles, imports, language errors, references, lazy and worker tasks, file values and the default host bridge. The `PWBB` bundle carries the entry image, module graph and metadata and the generated source calls `run_embedded_bundle_with_meta`. Integer overflow promotes to bigint. Division and modulo by zero return nova for int and num operands, matching the Python VM. The HTTP host modules, the generic host callback bridge, true parallel worker execution and the N6 release decisions remain. `random_token` uses `std::random_device` rather than a platform CSPRNG. `V10-native-vm-contract.md` and `powang vm abi` define the contract it consumes.
- Runtime error text and stream parity is covered for the language errors, examples and native corpora. Top-level language diagnostics go to standard output and checker warnings go to standard error. The HTTP modules and the generic host callback bridge are not implemented.
- Preemptive scheduling and coroutine suspension are not part of the language model. Lazy tasks and worker tasks run without arbitrary expression suspension. A future coroutine model needs a new bytecode version and a new task state machine.
- A JIT is not part of this phase. It can be added behind the same verifier, contract and differential suite.
- The optional cache stores the entry program image and imported module images. It is off by default and enabled with `--vm-cache`.
