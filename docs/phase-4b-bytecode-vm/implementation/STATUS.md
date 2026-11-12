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
| N3 | User types, enums, traits, operator dispatch and locks | not started | 0.23.0 |
| N4 | Modules, project, externs, errors and references | not started | 0.23.0 |
| N5 | Async, tasks, file I/O and the host bridge | not started | 0.24.0 |
| N6 | Full parity, performance and distribution | not started | 0.25.0 |

The native runtime lives under `native/` and consumes the same `PWB1` program image as the Python compiler. It is opt in. The Python VM remains the default engine and the differential oracle.

The N0 gate runs a real `print(1 + 2);` image through the native executable. Standard output is exactly `3` with no trailing newline, the exit code is `0`, and the native entry-code disassembly is byte-identical to the Python disassembler. The N0 scalar subset covers nova, undef, bool, int, num and char values, integer and number arithmetic, comparisons, logical not, negation, locals, jumps, top level `print` and `println`, and the N0 disassembler and verifier. An unsupported opcode fails with a clear runtime error. The N0 number semantics tests match the Python VM: mixed int/num arithmetic and comparisons follow the Python VM cast order, division and modulo by zero return nova for int and num, and float modulo follows the divisor sign, including signed zero. Integer overflow promotes to bigint in N1.

N1 execution is gate green. It adds arbitrary precision integers with int64 promotion, locals, globals, declarations, branches, range loops, `loop`, `break`, `continue`, functions, recursion, mutual recursion, defaults, named arguments, variadics, overload selection, closures by value and by reference, named lambda recursion, higher order function values, frames and iterators. `tests/native/corpus/n1` has 5 differential programs.

N2 is gate green. It adds UTF-32 strings, arrays, tuples, insertion ordered maps and sets, indexing, slicing, string and array operators, iteration, deep copy with a cycle memo, interpolation, the `format` and `printf` builtins, the character builtins and the array, string, map, set, tuple and char native methods. `tests/native/corpus/n2` has 6 differential programs. The file and task native methods remain in N5. Runtime error stream and text parity remains incomplete.

`tests/test_native_build.py` has 18 tests. They cover the generated opcode header, the in-memory buffer, the `print(1 + 2);` gate, byte-exact disassembly parity, corrupt image rejection, compiler diagnostics, temp cleanup, CLI run, CLI compile, native info, number semantics, print arity, loop image verification, bad jump rejection, missing compiler handling and stdin compilation. The number semantics test runs 36 subtests. `tests/test_native_meta.py` has 5 tests for deterministic PWBM metadata, the image hash, parameter metadata and the C++ metadata round trip. `tests/test_vm_native_corpus.py` has 2 differential tests covering the N1 and N2 corpora. The full suite has 618 tests. Run them with:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_native_build -v
```

The version is still `0.22.0`. N0, N1 and N2 are milestones, not releases. The plan targets `0.23.0` for N0 to N2. N3 to N6 remain planned, so the full native VM is not complete.

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
- The native C++17 runtime is implemented through milestone N2 under `native/`, and `powang vm native` is opt in. It consumes the same `PWB1` images as the Python compiler and covers scalars, big integers, functions, closures, strings, containers and native methods. User types, modules, errors, references, tasks and the full host surface are N3 to N6 work. Integer overflow promotes to bigint. Division and modulo by zero return nova for int and num operands, matching the Python VM. The full native VM is not complete. `V10-native-vm-contract.md` and `powang vm abi` define the contract it consumes.
- Runtime error stream and text parity is an explicit native parity task. `print();` is rejected by both engines with exit code 1, but the Python CLI writes its diagnostic to standard output while the native runtime writes its diagnostic to standard error. The exact error text also differs, so native error text and stream parity is not complete.
- Preemptive scheduling and coroutine suspension are not part of the language model. Lazy tasks and worker tasks run without arbitrary expression suspension. A future coroutine model needs a new bytecode version and a new task state machine.
- A JIT is not part of this phase. It can be added behind the same verifier, contract and differential suite.
- The optional cache stores the entry program image and imported module images. It is off by default and enabled with `--vm-cache`.
