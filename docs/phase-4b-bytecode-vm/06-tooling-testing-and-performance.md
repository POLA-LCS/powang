# Tooling, Testing, and Performance

Purpose: Specify VM tooling, verification tests, differential tests, fuzzing, and performance goals.

## 16. Tooling

### 16.1 Disassembler

`powang vm disasm file.po` prints:

- Module table.
- Type and trait tables.
- Function code objects.
- Constant pool entries.
- Instruction offsets.
- Source spans.
- Exception tables.

The disassembler reads the same opcode registry as the VM.

### 16.2 Trace mode

`powang vm run --trace file.po` prints a compact trace of:

- Instruction pointer.
- Opcode.
- Stack depth.
- Current source span.
- Call and return events.
- Task events.
- Runtime errors.

Trace mode is for debugging and differential analysis. It is not a stable API.

### 16.3 Differential harness

The differential harness runs a program twice:

1. Tree-walker.
2. VM.

It compares:

- Standard output.
- Standard error.
- Exit code.
- Created or modified files.
- Task completion sets.
- Timing only for regression reports, not equality.

The harness runs the full test suite. A mismatch blocks the phase.

### 16.4 Fuzzing

A grammar-based fuzzer generates valid programs from the language grammar and
the checker. It runs both engines and compares results. A seed is recorded for
every failure. The fuzzer must cover:

- Deep expressions.
- Nested containers.
- All operator combinations.
- Match patterns.
- Trait and operator dispatch.
- Error paths.
- Async tasks.
- Module graphs.

### 16.5 Benchmarks

The benchmark corpus contains:

- Arithmetic loops.
- Recursive functions.
- Array and map updates.
- String and character processing.
- Object allocation and method calls.
- Trait dispatch.
- Error handling.
- Async task creation and waiting.
- Module loading.
- Startup time.

The first report is the tree-walker baseline. The second report is the Python
reference VM. The third report is the native VM. Performance claims require
three runs and a stable machine profile.

## 18. Test plan

### 18.1 Unit tests

- Opcode encoding and decoding.
- Constant pool deduplication.
- Label patching.
- Verifier reject cases.
- Value equality and hashing.
- Copy-on-write.
- Frame layout.
- Error formatting.
- Task states.
- Module cache.
- Disassembler output.

### 18.2 Golden disassembly tests

Representative programs have stable disassembly snapshots. They cover every
opcode family. A snapshot change requires a reviewed opcode or lowering change.

### 18.3 Differential tests

Every existing test runs on both engines. The harness compares output, error,
exit code and file side effects. The harness supports test filtering so a
feature phase can run only its relevant subset.

### 18.4 Fuzz tests

Grammar-based fuzzing runs on both engines. A failure saves the source, seed,
bytecode disassembly and both outputs.

### 18.5 Stress tests

- Deep recursion and stack overflow.
- Very large arrays and maps.
- Large string slicing and character access.
- Many closures and captures.
- Many modules and imports.
- Many tasks and cancellation races.
- Repeated VM creation and destruction.

### 18.6 Cross-platform tests

- Windows, macOS and Linux.
- UTF-8 source files.
- Unicode characters in strings, chars and identifiers where supported.
- File path separators.
- CRLF and LF source files.

### 18.7 Memory tests

- Copy-on-write does not leak shared storage.
- Task cleanup releases frame values.
- Module cache releases when the session ends.
- Error frames do not retain the whole program forever.
- Large values are collectable.

## 19. Performance plan

### 19.1 Baseline

Measure the tree-walker before changing anything. Record:

- Wall time.
- Peak memory.
- Allocations.
- Instruction count for the VM.
- Startup time.

### 19.2 Python reference VM

The Python VM is expected to be close to the tree-walker, perhaps slower for
small programs. Its purpose is correctness. Optimize only after parity.

Possible optimizations:

- Predecoded instruction tuples.
- Cached call site resolution.
- Direct local slot indexing.
- Small value interning.
- Avoid copying immutable strings and tuples.
- Fast paths for int, num, bool and char operations.

### 19.3 Native VM

The native VM is where the performance target lives. It can use:

- Tagged 64-bit values.
- Direct threaded dispatch.
- Inline caches for fields, methods and overloads.
- Copy-on-write with reference counting.
- Arena or region allocation per task.
- Specialized arithmetic instructions.
- Superinstructions for common sequences.
- Optional profile-guided optimization.

### 19.4 Targets

Correctness target:

- Zero differential mismatches.

Performance target:

- Python reference VM within 2x of the tree-walker on the benchmark corpus.
- Native VM at least 3x faster than the tree-walker on CPU-bound benchmarks.
- Native VM startup within 1.2x of the tree-walker for small scripts.

If the Python VM is slower, that is not a release blocker. The native VM is the
performance deliverable.

