# Phase 4B Status

Purpose: track the V0 to V9 gates, the `src/vm` module ownership and the Appendix F acceptance checklist.

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
| V9 | Parity and default switch | in progress | 0.21.0 | see git log |

Design documents: complete.

Contracts document: complete.

The V9 gate is in progress by design. The VM is opt in at `0.21.0`. The default engine switch waits for one full release with zero differential mismatches, as the design requires.

Recorded results for `0.21.0`:

- Tree suite: 575 tests, all pass.
- VM suite with `POWANG_ENGINE=vm`: 575 tests, all pass.
- Differential example corpus: every `.po` file under `examples`, zero mismatches.
- Differential inline corpus: 13 programs, zero mismatches.
- Seeded fuzzer: 1000 generated programs on seed 2026, 7 oracle crashes skipped, zero mismatches.
- Error parity corpus: 13 cases, identical output, error text and exit code.
- Disassembler, trace, JSON output, image round trip, cache, engine flag and verifier reject tests pass.

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
| `src/vm/cli.py` | V0 | implemented |
| `src/vm/dispatch.py` | V2 | implemented |
| `src/vm/declarations.py` | V4 | implemented |
| `src/vm/modules.py` | V6 | implemented |
| `src/vm/tasks.py` | V8 | implemented |
| `src/vm/bench.py` | V9 | implemented |

Tests live in the repository `tests/` directory, not under `src/vm/tests`. The design document's recommended `src/vm/tests/` layout is a suggestion. The project keeps one test discovery root so the tree and VM suites run together.

`src/vm/compiler.py` and `src/vm/interpreter.py` were extended phase by phase without changing their public names. `src/vm/values.py`, `src/vm/verifier.py` and `src/vm/image.py` keep the same public names.

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
- The default switch is deliberately deferred. The VM remains opt in at `0.21.0`.

## 4. How to run the gates

Run these commands from the repository root in Windows PowerShell.

The tree suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The full suite on the VM:

```powershell
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
Remove-Item Env:\POWANG_ENGINE
```

The VM unit and integration tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_foundation tests.test_vm_runtime tests.test_vm_tooling tests.test_vm_differential tests.test_vm_errors -v
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

The engine selection:

```powershell
.\.venv\Scripts\python.exe powang.py --engine=tree examples\modern.po
.\.venv\Scripts\python.exe powang.py --engine=vm examples\modern.po
$env:POWANG_ENGINE = "vm"
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
Version: <0.20.x or 0.21.0>
```

## 6. Known limitations

- The Python VM is a correctness reference. It is not expected to beat the tree walker on every program. The benchmark report shows the measured ratio.
- Block locals share the module store with module globals. Task isolation treats names that the compiler did not record as module declarations as local and does not clone them. A block local that shadows a module global name is treated as a module global for task isolation.
- The `project.engine` selection source is not available because the `Project` value has no `engine` field. Use `--engine=` or `POWANG_ENGINE` instead.
- The optional cache covers the entry program image. Imported modules are compiled on demand and are not written to the cache.
- The fuzzer skips a generated program when the tree walker raises a Python traceback or reports an internal error. Those cases are oracle crashes, not semantic references.
- The VM remains opt in. The default engine is still `tree`.
