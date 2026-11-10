# V9: Parity and Default Switch

Purpose: prove full differential parity, document the disassembler and trace mode, add optional cached images and benchmarks, keep the VM opt in for one full release, then make the VM the default engine with the tree walker as a fallback.

## Objective

V9 is the release gate. It does not add language features. It proves that the VM executes every language feature, every example, every error path and every existing test with the same observable behavior as the tree walker. It finishes the disassembler and trace mode, adds optional bytecode caching, records performance baselines and switches the default engine only after the compatibility gates pass.

V9 spans two releases. The first release keeps the tree walker as the default and ships the VM as opt in. The second release makes the VM the default and keeps `--engine=tree` as a supported fallback. The first release must complete with zero mismatches before the second release is tagged.

The language version is `0.21.0` at the end of V9. The bytecode format version stays `1`. The LSP keeps the same parser and checker and produces the same diagnostics.

Semantic reference: `docs/phase-4b-bytecode-vm/06-tooling-testing-and-performance.md`, `docs/phase-4b-bytecode-vm/07-implementation-rollout-and-decisions.md` sections 19 to 23, and `docs/phase-4b-bytecode-vm/README.md` sections 22, 23 and Appendix F.

## Prerequisites

- V8 is `gate green`. Async and task cleanup pass under repeated starts and shutdowns.
- The V8 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v8 --fail-fast
```

- The existing suite is green in tree mode.
- No LSP source file changed during V0 to V8.

Contract surfaces this phase depends on:

- `src/vm/differential.py`: full suite runner, example runner, error snapshot runner, fuzz runner.
- `src/vm/bench.py`: benchmark corpus and report.
- `src/vm/modules.py`: `BytecodeCache`.
- `src/vm/disasm.py`: complete table rendering and deterministic `--json`.
- `src/vm/trace.py`: complete event set and text sink.
- `src/vm/image.py`: `LANGUAGE_VERSION = "0.21.0"`.
- `src/state.py`: default engine.
- `powang.py`: command line default engine.
- `pyproject.toml`: package version `0.21.0`.

## Deliverables

### By file

| File | Work in V9 |
|---|---|
| `src/vm/differential.py` | `--suite tests`, `--examples examples`, `--snapshots`, `--fuzz`, full report and mismatch bundle |
| `src/vm/bench.py` | Benchmark corpus, runner, wall time, peak memory, instruction count, startup report |
| `src/vm/modules.py` | `BytecodeCache`, cache key, cache read and write, corrupted entry recovery |
| `src/vm/disasm.py` | Complete module, type, trait, function, constant, call site, pattern, spec, source, global, string and debug tables, deterministic JSON |
| `src/vm/trace.py` | Instruction, call, return, task and error events, stable text format |
| `src/vm/cli.py` | Final `vm` subcommands, `--vm-cache`, `--trace`, `--json`, help text |
| `src/vm/image.py` | `LANGUAGE_VERSION = "0.21.0"` |
| `src/state.py` | Default engine changes to `"vm"` in the second release only |
| `powang.py` | Default engine changes to `"vm"` in the second release only, `--engine=tree` remains |
| `pyproject.toml` | Version `0.21.0` in the second release |
| `src/vm/tests/test_full_parity.py` | Corpus plus existing suite parity |
| `src/vm/tests/test_error_snapshots.py` | Error snapshot comparison |
| `src/vm/tests/test_cache.py` | Cache key, hit, miss, corruption and invalidation |
| `src/vm/tests/test_bench.py` | Benchmark runner and report shape |
| `src/vm/tests/snapshots/errors/` | Error snapshot files |
| `src/vm/tests/corpus/v9/` | Full parity and stress programs |
| `tests/test_vm_parity.py` | End to end release parity test |

### By release item

V9 adds no language feature. The table groups the release work that proves the earlier feature phases.

| Item | Required result |
|---|---|
| Full differential suite | Every corpus phase and the existing suite run on both engines with zero mismatches |
| All examples | Every `examples/*.po` file except `*.ignore.po` produces identical output and exit code |
| All error snapshots | Every error program produces identical stderr and exit code |
| Disassembler | Every program image table renders, offsets are stable, JSON output is deterministic |
| Trace mode | Instruction, call, return, task and error events render in a compact stable format |
| Optional cached images | Off by default, opt in with `--vm-cache`, cache key covers every invalidation input |
| Benchmarks | Tree baseline, VM baseline, instruction counts, startup time, three run report |
| Opt in release | One full release with VM opt in and zero mismatches |
| Default release | VM default, tree fallback, no LSP change |
| Language version | `0.21.0` |
| Bytecode format version | `1` |

## Task checklist

- [ ] Run the full differential suite and fix every parity gap.
- [ ] Run every example on both engines and fix every output difference.
- [ ] Add the error snapshot suite and fix every error text difference.
- [ ] Finalize the disassembler tables and deterministic JSON.
- [ ] Finalize trace events and the text sink.
- [ ] Add optional cached images and cache invalidation.
- [ ] Add the benchmark corpus and the three run report.
- [ ] Cut the opt in release `0.20.x` with the VM behind `--engine=vm`.
- [ ] Keep the opt in release open for one full release cycle with zero mismatches.
- [ ] Switch the default engine to `vm` and cut `0.21.0`.
- [ ] Run the LSP suite and confirm no diagnostic change.
- [ ] Update `STATUS.md`, the V9 file and the release notes.

## Lowering table

V9 adds no language constructs. The table records the final lowering checks that the full suite covers.

| Source construct | Emitted instruction sequence | Final check |
|---|---|---|
| Every V0 literal and arithmetic form | `LOAD_*`, `ADD` to `MOD`, `RETURN` | Golden offsets and full corpus |
| Every V1 declaration and control flow form | `DECLARE_*`, `STORE_*`, `JUMP_*`, `RETURN` | Full core corpus |
| Every V2 function and call form | `DECLARE_FUNCTION`, `CALL*`, `MAKE_CAPTURE`, `LOAD_CAPTURE` | Function, lambda and variadic suites |
| Every V3 container, string and native form | `MAKE_*`, `INDEX_*`, `SLICE`, `ITER_*`, `CALL_NATIVE`, `CALL_BUILTIN` | Container, string and native suites |
| Every V4 type, enum and operator form | `DECLARE_TYPE`, `CONSTRUCT`, `LOAD_FIELD`, `CALL_METHOD`, `CALL_STATIC`, `LOAD_ENUM_MEMBER`, `SET_LOCKS` | Type, enum and operator suites |
| Every V5 trait and generic form | `DECLARE_TRAIT`, `CHECK_TRAIT`, `TRAIT_CAST`, `CALL_TRAIT` | Trait and generic suites |
| Every V6 module and project form | `IMPORT`, `IMPORT_WILDCARD`, `LOAD_MODULE_MEMBER`, `EXPORT`, `LOAD_PROJECT`, `CALL_MODULE`, `CALL_EXTERN` | Module, project and package suites |
| Every V7 error and reference form | `MAKE_ERROR`, `THROW`, `TRY_*`, `FINALLY_END`, `PROPAGATE`, `REF_*`, `LOAD_REF`, `STORE_REF` | Error and reference suites |
| Every V8 async and task form | `CALL_ASYNC`, `CALL_ASYNC_METHOD`, `SPAWN`, `AWAIT`, `CHECK_CANCEL` | Async and task suites |
| Cached image load | `read_image`, `verify_image(strict=False)`, run | Cache tests |
| Trace run | every instruction emits `TRACE_EVENT` through the sink | Trace tests |

## Runtime semantics notes

### Full differential suite

`src/vm/differential.py` gains these modes:

- `--suite tests` runs `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` twice in fresh subprocesses, once with `POWANG_ENGINE=tree` and once with `POWANG_ENGINE=vm`, and compares stdout, stderr and exit code.
- `--examples examples` runs every `*.po` file in the directory tree on both engines. Files whose name ends with `.ignore.po` are skipped. Multi file examples run from their own directory.
- `--corpus src\vm\tests\corpus` runs every phase corpus.
- `--snapshots src\vm\tests\snapshots` runs every error program and compares the normalized stderr to the snapshot.
- `--fuzz --seed N` runs the grammar based fuzzer for N programs or until a failure. A failure saves the source, seed, disassembly, tree output and VM output under `.powang/failures/`.
- `--fail-fast` stops at the first mismatch.

The runner compares stdout, stderr, exit code, created or modified files and the set of completed task IDs. Timing is reported but never compared. The suite runner normalizes unittest timing lines and temporary directory paths before comparison. An example that depends on host state uses a deterministic fixture. If an example cannot be made deterministic, it is listed in `src/vm/tests/corpus/v9/example_skips.txt` with a reason and remains covered by `test_examples.py` for the no traceback and no diagnostic checks.

A mismatch bundle contains:

- The source path and source text.
- The tree and VM stdout, stderr and exit code.
- The first differing field.
- The VM disassembly.
- The tree and VM command lines.

### Error snapshots

Each snapshot is a `.stderr` file next to a `.po` source under `src/vm/tests/snapshots/errors/`. The comparison normalizes CRLF to LF. The snapshot stores the full stderr or the full stdout diagnostic stream, whichever the CLI uses for the error family. The runner uses the same capture path as the CLI.

The snapshot set covers every family in Appendix D:

- Runtime type mismatch.
- Undefined reference.
- Index out of range.
- Invalid cast.
- Invalid operation.
- Argument count.
- Argument type.
- Module resolution.
- Module cycle.
- Module mutation.
- Const lock.
- Reference escape.
- Task cancellation.
- Task failure.
- File error.
- User error.
- Recursion.

### Disassembler

`disassemble_image` renders these sections in this order:

1. Header: magic, format version, language version, flags, table count, checksum.
2. Module table: index, name, path, code index, export count.
3. Type table: index, name, kind, type parameters, field count, method count, variant count.
4. Trait table: index, name, property count, method count, default count.
5. Function table: index, name, code index, min argc, flags.
6. Constant pool: index, kind, stable rendered value.
7. Call site table: index, dispatch, name, module, type, trait, positional count, argument kinds, type argument count.
8. Pattern table: index, kind, binding count, nested count.
9. Type spec table: index, rendered spec.
10. Source file table: index, path.
11. Global name table: index, name.
12. String table: index, string.
13. Debug line table: index, line, column.
14. Code objects: name, qualname, source, parameter count, local count, capture count, max stack, flags, instruction offsets, opcode, operands, span line and column, exception table.

Every section prints even when empty. The `--json` output uses the same key order as the text output and a stable sort for maps. The disassembler reads only the opcode registry and the image. It never imports the compiler.

### Trace mode

`TraceEvent` fields:

- `kind`: `instruction`, `call`, `return`, `task_create`, `task_await`, `task_done`, `error`.
- `frame_name`.
- `ip`.
- `opcode`.
- `stack_depth`.
- `line` and `column`.
- `task_id`.
- `detail`.

`TextTraceSink` format:

```text
0000 main              LOAD_INT 1          stack=1 line=2
0009 main              CALL      site=0    stack=1 line=2
call add
...
return add value=3
task 4 create pending
task 4 await
task 4 done 42
error IDENTIFIER line=3
```

The format is compact, stable within one version and not a public API. The trace sink is selected by `--trace` and writes to stderr so program stdout stays comparable.

### Cached images

- Caching is off by default. It is enabled by `--vm-cache`, `POWANG_VM_CACHE=1` or the project metadata cache key.
- The cache directory is `.powang/cache/bytecode/` under the project root.
- The cache key is a SHA-256 over:
  - The resolved source path.
  - The source SHA-256.
  - `FORMAT_VERSION`.
  - `LANGUAGE_VERSION`.
  - The compiler version constant.
  - The sorted dependency hashes.
  - The package version when the module comes from a package.
  - The engine feature flags.
- A cache hit runs `read_image` and `verify_image(strict=False)`. A bad magic, bad checksum, bad table or a verification failure deletes the entry and recompiles.
- A cache write is atomic: write to a temporary file in the same directory, flush, then replace.
- Debug images are not cached with release images. The cache key includes the debug flag.
- A cache entry never changes program output. A cache hit and a cache miss must produce identical behavior.

### Benchmarks

`src/vm/bench.py` contains one program per family:

- Arithmetic loop.
- Recursive function.
- Array and map updates.
- String and character processing.
- Object allocation and method calls.
- Trait dispatch.
- Error handling.
- Async task creation and waiting.
- Module loading.
- Startup.

The runner records wall time, peak memory with `tracemalloc`, VM instruction count and startup time. `--runs 3` reports the median and the spread. The report is a table with `engine`, `program`, `runs`, `median_ms`, `peak_kb`, `instructions`, `startup_ms`.

Performance targets are recorded but do not block the correctness gate:

- Python reference VM within 2x of the tree walker on the corpus.
- Native VM at least 3x faster on CPU bound programs.
- Native VM startup within 1.2x of the tree walker.

### Engine default switch

Release one, version `0.20.x`:

- `InterpreterState.engine` default remains `"tree"`.
- `powang.py` default remains `tree`.
- `--engine=vm`, `POWANG_ENGINE=vm` and the project metadata engine key with value `vm` select the VM.
- The release notes say the VM is opt in and list the known limitations.
- The release must stay published for one full release cycle with zero reported mismatches before release two.

Release two, version `0.21.0`:

- `InterpreterState.engine` default becomes `"vm"`.
- `powang.py` default becomes `vm`.
- `--engine=tree` remains and selects the tree walker.
- `POWANG_ENGINE=tree` remains.
- The project metadata engine key remains accepted with value `tree`.
- The tree walker is not deleted. It stays the oracle for bug reports and differential tests.
- The LSP is unchanged. The parser, checker and diagnostics are the same code paths.

A rollback is a one line default change plus a patch release. The VM remains available behind `--engine=vm`.

### Version and cache invalidation

- `LANGUAGE_VERSION` changes from `0.20.0` to `0.21.0` in the release two commit.
- `FORMAT_VERSION` stays `1`.
- All cached images from `0.20.x` are invalid because the language version differs.
- A package version change invalidates the module dependency hashes.
- A compiler version change invalidates the cache key.

## Acceptance criteria

1. `.\.venv\Scripts\python.exe -m src.vm.differential --suite tests --fail-fast` reports zero mismatches.
2. `.\.venv\Scripts\python.exe -m src.vm.differential --examples examples --fail-fast` reports zero mismatches.
3. `.\.venv\Scripts\python.exe -m src.vm.differential --snapshots src\vm\tests\snapshots --fail-fast` reports zero mismatches.
4. Every opcode has a verifier rule and at least one unit test. The registry generator test proves it.
5. Every AST node kind has a lowering test. The compiler coverage test proves it.
6. The disassembler renders every table for an empty image and for `examples\modern.po`.
7. The trace output contains instruction, call, return, task and error events for a program that uses all five.
8. A cache hit and a cache miss produce identical stdout, stderr and exit code.
9. A corrupted cache entry is deleted and the program still runs.
10. The benchmark report contains every corpus program for both engines and three runs.
11. The opt in release is tagged and published with the VM behind the flag.
12. The default release is tagged only after one full release cycle with zero mismatches.
13. `--engine=tree` still runs every corpus after the default switch.
14. The LSP suite in its own repository is green and `git diff --name-only src/typecheck.py src/parser.py src/lexer` is empty for the release branch.
15. `pyproject.toml` version is `0.21.0` in the default release.
16. `STATUS.md` shows every phase as `gate green` or `released`.
17. The existing suite is green in both engine modes.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus --fail-fast
.\.venv\Scripts\python.exe -m src.vm.differential --suite tests --fail-fast
.\.venv\Scripts\python.exe -m src.vm.differential --examples examples --fail-fast
.\.venv\Scripts\python.exe -m src.vm.differential --snapshots src\vm\tests\snapshots --fail-fast
.\.venv\Scripts\python.exe -m src.vm.differential --fuzz --seed 1 --count 100 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_examples.py" -v
.\.venv\Scripts\python.exe powang.py vm disasm examples\modern.po
.\.venv\Scripts\python.exe powang.py vm disasm --json examples\modern.po
.\.venv\Scripts\python.exe powang.py vm run --trace examples\modern.po
.\.venv\Scripts\python.exe -m src.vm.bench --runs 3 --engine both
.\.venv\Scripts\python.exe powang.py --engine=tree examples\modern.po
.\.venv\Scripts\python.exe powang.py --engine=vm examples\modern.po
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_typecheck_internal.py" -v
git diff --name-only -- src\typecheck.py src\parser.py src\lexer
```

Cache verification:

```powershell
.\.venv\Scripts\python.exe powang.py --engine=vm --vm-cache examples\modern.po
.\.venv\Scripts\python.exe -c "from pathlib import Path; entries = list(Path('.powang/cache/bytecode').glob('*')); assert entries, 'cache is empty'; print(len(entries))"
.\.venv\Scripts\python.exe powang.py --engine=vm --vm-cache examples\modern.po
```

Default switch verification after release two:

```powershell
.\.venv\Scripts\python.exe powang.py examples\modern.po
.\.venv\Scripts\python.exe powang.py --engine=tree examples\modern.po
.\.venv\Scripts\python.exe powang.py --engine=vm examples\modern.po
.\.venv\Scripts\python.exe -c "from src.state import fresh_state; assert fresh_state().engine == 'vm'; print('vm default')"
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v9/`.

`full_parity.po`:

```po
type Point[+] {
    | x: int;
    | y: int;

    fun this.add(other: Point): Point >> Point.[this.x + other.x, this.y + other.y];
    fun this.compare(other: Point): int >> this.x - other.x;
    fun this.describe(): str >> $"({this.x}, {this.y})";
}

trait Described {
    fun describe(): str;
    fun label(): str >> this.describe();
}

type Screen[+] {
    | name: str;
    fun this.draw(): str >> "screen";
}

fun render[T: Described](value: T): str >> value.label();

values := [1, 2, 3];
values[0] = 9;
pairs := ["a" >> 1, "b" >> 2];

left := Point.[1, 2];
right := Point.[3, 4];
sum := left + right;
println(sum.describe());
println(pairs["b"]);

value := 15;
match value {
    case 0 >> 10 >> println(0);
    case 10 >> 20 >> println(1);
    case _ >> println(2);
}

try {
    error("boom");
} catch problem {
    println(problem.kind);
} finally {
    println("done");
}

counter := 0;
fun increment(target: &int) {
    target += 1;
}
increment(&counter);
println(counter);

async fun double(input: int): int >> input * 2;
println(await double(21));

task := spawn double(5);
println(wait(task));
```

`stress_containers.po`:

```po
values := [];
for i >> 0 >> 500 {
    values &> arr.push(i);
}
total := 0;
for value >> values {
    total += value;
}
println(total);

pairs := [>>];
for i >> 0 >> 200 {
    pairs["k" + (i as str)] = i * 2;
}
println(size(pairs));
println(pairs["k199"]);
```

`stress_closures.po`:

```po
fun make(amount: int): fun[int, int] {
    return fun(value: int): int >> value + amount;
}

first := make(1);
second := make(2);
third := make(3);
println(first(1));
println(second(1));
println(third(1));
println(first(2) + second(2) + third(2));
```

`stress_errors.po`:

```po
fun depth(value: int): int {
    if value == 0 {
        error("bottom");
    }
    return depth(value - 1);
}

try {
    depth(50);
} catch problem {
    println(problem.kind);
    println(problem.message);
    println(size(problem.frames));
}
```

`empty.po`:

```po
## An empty program exercises empty image tables.
```

The full parity corpus is a regression net. The individual phase corpora remain the primary per feature tests.

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v9_full_parity` | `src/vm/tests/corpus/v9/full_parity.po` | Every table non empty, every opcode family present at least once, all offsets stable |
| `v9_stress_containers` | `src/vm/tests/corpus/v9/stress_containers.po` | Hidden iterator slots, `CALL_NATIVE`, `INDEX_SET`, backward jumps |
| `v9_stress_closures` | `src/vm/tests/corpus/v9/stress_closures.po` | Many code objects, capture cells, `CALL_VALUE` |
| `v9_stress_errors` | `src/vm/tests/corpus/v9/stress_errors.po` | `MAKE_ERROR`, `THROW`, `TRY_BEGIN`, `FINALLY_END`, frames |
| `v9_empty_image` | `src/vm/tests/corpus/v9/empty.po` | Empty sections render with headers and zero counts |
| `v9_cache_hit` | `src/vm/tests/corpus/v9/full_parity.po` with `--vm-cache` | Second run reads the cache, output identical |
| `v9_trace` | `src/vm/tests/corpus/v9/full_parity.po` with `--trace` | Instruction, call, return, task and error events all appear |

## Atomic commit plan

1. `vm(v9): run the full differential suite and fix parity gaps`
2. `vm(v9): run every example on both engines`
3. `vm(v9): add the error snapshot suite`
4. `vm(v9): finalize the disassembler tables and json output`
5. `vm(v9): finalize trace events and the text sink`
6. `vm(v9): add optional cached program images`
7. `vm(v9): add the benchmark corpus and three run report`
8. `vm(v9): document the vm cli and tooling`
9. `vm(v9): cut the opt in release with the vm behind the flag`
10. `vm(v9): keep the opt in release open for one cycle`
11. `vm(v9): switch the default engine to vm and cut 0.21.0`
12. `vm(v9): update status release notes and the final checklist`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| A parity gap appears late | The full suite runs on every commit after V6. A mismatch blocks the release | Keep the VM opt in and fix before the default switch |
| An example depends on host timing | The example runner compares output and exit code, never timing. Async examples use `wait` before printing | Remove the example from the blocking list with a documented reason |
| Error snapshot churn | Snapshots are exact and reviewed. A message change is a language change | Regenerate only with a reviewed language decision |
| The cache serves a stale image | The key covers source hash, dependency hashes, versions and flags. Verification runs in trusted mode | Disable `--vm-cache` and delete `.powang/cache/bytecode` |
| The default switch breaks a user project | The opt in release runs for one full cycle. `--engine=tree` remains | Revert the default line and publish a patch release |
| The LSP changes indirectly | No parser or checker edit in V9. The diff check is part of the gate | Revert the release commit and keep the VM opt in |
| Performance regresses | The report records the baseline. Correctness remains the gate | Do not block the release on Python VM speed. Optimize after parity |
| A benchmark is noisy | Three runs, median and spread, stable machine profile | Report the spread and do not treat timing as a pass or fail |
| The cache write is interrupted | Write to a temporary file and replace atomically | Delete the partial entry and recompile |

## Exit gate

V9 and the whole Phase 4B program are closed when all of these are true:

- [ ] Every phase from V0 to V8 is `gate green`.
- [ ] The full differential suite reports zero mismatches.
- [ ] Every example produces identical output and exit code.
- [ ] Every error snapshot matches.
- [ ] Every opcode has a verifier rule and a test.
- [ ] Every AST node kind has a lowering rule and a test.
- [ ] The disassembler renders every table, including empty tables.
- [ ] Trace mode shows instruction, call, return, task and error events.
- [ ] Cached images are optional, safe and invalidated by every input.
- [ ] The benchmark report has three runs for both engines.
- [ ] The opt in release is published and has zero reported mismatches for one full release cycle.
- [ ] The default release is published with the VM as default and the tree walker as fallback.
- [ ] The LSP diagnostics are unchanged.
- [ ] `pyproject.toml` reports `0.21.0`.
- [ ] `LANGUAGE_VERSION` reports `0.21.0`.
- [ ] `STATUS.md` shows every phase as `gate green` or `released` and every Appendix F item checked.
