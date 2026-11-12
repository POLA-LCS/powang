# N0: Native C++17 VM and In-Memory `temp.cpp` Build Plan

Status: N0, N1 and N2 are implemented and their gates are green. N3 to N6 remain planned. The native runtime consumes the same `PWB1` program image as the Python compiler. The Python VM remains the default engine and the differential oracle. The version is still `0.22.0`. N0, N1 and N2 are milestones, not releases. The plan targets `0.23.0` for N0 to N2.

Reference engine: the Python bytecode VM in `src/vm`, package version `0.22.0`, image format `PWB1` version `1`.

Purpose: define an implementation-ready path for two deliverables.

1. A native C++17 VM that consumes the same `PWB1` program image the Python compiler produces and matches the Python VM as the differential oracle.
2. An integrated build path that renders a complete `temp.cpp` translation unit into an in-memory buffer, invokes the local `g++` compiler on that text, captures diagnostics, and produces a native executable that can be run and compared with the Python VM.

The generated `temp.cpp` is rendered into a memory buffer. The default integrated compiler writes a temporary `temp.cpp` file for diagnostics and deletes it after the compile. It is never written to the repository and is not committed. The logical file name `temp.cpp` is kept for diagnostics and for an optional debug fallback.

## Implementation note (N0)

N0, N1 and N2 are implemented and their gates are green. N3 to N6 remain planned. The native runtime consumes the same `PWB1` program image as the Python compiler. The Python VM remains the default engine and the differential oracle.

The implemented layout uses different names from the placeholders in sections 2.1, 3.1 and 4.1.

1. `native/include/pwb/` contains `opcodes.hpp`, `opcodes_generated.hpp`, `image.hpp`, `value.hpp`, `error.hpp`, `verifier.hpp`, `disasm.hpp`, `vm.hpp` and `host.hpp`.
2. `native/src/` contains `opcodes.cpp`, `image.cpp`, `verifier.cpp`, `disasm.cpp`, `vm.cpp`, `host.cpp` and `main.cpp`. `native/CMakeLists.txt` builds `pwb_runtime` and `pwb_native`.
3. `src/vm/native/` contains `gen_opcodes.py`, `source_gen.py`, `compiler.py`, `build.py` and `loader.py`. These are the implemented names that replace the planned `abi.py`, `sourcegen.py`, `gcc.py`, `cache.py` and `cli.py`.
4. `gen_opcodes.py` generates the checked-in C++ opcode table from the Python registry into `native/include/pwb/opcodes_generated.hpp`. This is the generated header.
5. `source_gen.py` exposes `render_temp_cpp`, `render_temp_cpp_buffer` and `render_temp_cpp_into`. It renders a complete `temp.cpp` translation unit into an `io.StringIO` buffer. `compiler.py` exposes `IntegratedGcc.compile` and runs the integrated `g++` driver. `build.py` exposes `ensure_runtime` and configures and builds the native runtime with CMake and Ninja. `loader.py` exposes `run_native` and `compile_image` and compiles and runs an image.

The N0 scalar subset supports nova, undef, bool, int, num and char values, integer and number arithmetic, comparisons, logical not, negation, locals, jumps, top level `print` and `println`, and the N0 disassembler and verifier. Mixed int/num arithmetic and comparisons follow the Python VM cast order: an int left operand casts the right num to int and returns int, and a num left operand casts the right int to num and returns num. Bool comparisons follow Python truthiness. Division and modulo by zero return nova for int and num operands. Float modulo follows the divisor sign, including signed zero. An unsupported opcode fails with a clear runtime error. Integer overflow remains an N1 gap and raises a clear native error instead of promoting to bigint. Strings, containers, user types, modules, errors, references, tasks and the full host surface are N1 to N6 work.

The gate runs a real `print(1 + 2);` image through the native executable. Standard output is exactly `3` with no trailing newline, the exit code is `0`, and the native entry-code disassembly is byte-identical to the Python disassembler.

N0 exit behavior: image and verifier errors return `1`, runtime errors return `1`, and success returns `0`. Exit code `3` for image errors later in this document is a later design option, not the N0 behavior.

The N0 image parser rejects images larger than 256 MiB. The native compiler driver removes a stale output before compiling and requires a non-empty output for success. Captured diagnostics are truncated at 1 MiB of UTF-8 bytes with a `... [truncated]` marker.

Runtime error stream and text parity is not complete. `print();` is rejected by both engines with exit code 1, but the Python CLI writes its diagnostic to standard output while the native runtime writes its diagnostic to standard error. The exact error text also differs. This is an N1 parity task, not an N0 gate requirement.

The generated source is called `temp.cpp`. It is rendered into an in-memory buffer, and the default integrated compiler writes a temporary `temp.cpp` file for compilation and diagnostics. It is never committed. The output executable is temporary for `powang vm native run` and explicit for `powang vm native compile`.

## 1. Objective and non-goals

### 1.1 Objective

The native VM must be a third execution engine with the same semantics as the Python VM and the tree walker.

1. It consumes `PWB1` images produced by `src.vm.compiler`.
2. It reproduces language values, copy semantics, calls, overload scoring, errors, source positions, modules and tasks.
3. It is driven by the same opcode registry, tag order, operand widths and image format as the Python engine.
4. It exposes an integrated build API that turns a `ProgramImage` into a native executable without a checked-in C++ file.
5. It keeps the Python VM as the differential oracle at every milestone.
6. It gives the project a measurable performance path without changing language semantics.

The first concrete gate is small and exact. `print(1 + 2)` compiles through the integrated path, writes exactly `3` with no trailing newline, and exits with code `0`.

### 1.2 Non-goals

The following are out of scope for N0 to N6.

1. A JIT compiler.
2. A tracing garbage collector in the first native release. The reference native VM uses reference counting plus a frame arena.
3. Coroutine suspension at arbitrary expression boundaries. The language model stays lazy tasks plus worker tasks.
4. A native parser or type checker. The frontend remains Python.
5. A native REPL. The REPL stays on the Python VM.
6. A native package resolver. Package and project resolution happens at build time in Python.
7. Full debugger integration. The native VM keeps spans and frame metadata, but a native debug adapter is a later phase.
8. MSVC support in the first release. The target toolchain is `g++` MinGW-W64 UCRT on Windows, with `clang++` as a secondary check.
9. Claiming that the full native VM is already implemented. N0 is implemented. N1 to N6 remain planned (see the Implementation note at the top).
10. Changing the language, the bytecode format, the checker or the LSP.

### 1.3 Success definition

Semantic success means one thing, exactly as the Phase 4B design defines it. A program that passes the checker must produce the same standard output, standard error, error text, exit code and observable side effects on the Python VM and the native VM.

Performance success is separate and never overrides semantic success.

1. Native is at least three times faster than the tree walker on the CPU-bound benchmark corpus.
2. Native startup is within 1.2 times the tree walker for small scripts.
3. A warm integrated compile of a 50 KB image finishes under five seconds on the development machine.
4. A cold integrated compile of the same image finishes under ten seconds.

## 2. Architecture

### 2.1 Native layout

The native project lives under `native/`. The Python side of the integrated build lives under `src/vm/native/`. The Python VM, the compiler and the verifier are not modified by the native implementation except for the new package and the CLI wiring.

```text
native/
  CMakeLists.txt
  README.md
  include/pwb/
    version.hpp
    result.hpp
    value.hpp
    heap.hpp
    object.hpp
    image.hpp
    meta.hpp
    opcode_generated.hpp
    verifier.hpp
    frame.hpp
    dispatch.hpp
    vm.hpp
    errors.hpp
    host.hpp
    module.hpp
    task.hpp
    disasm.hpp
    trace.hpp
    embed.hpp
    runtime.hpp
  src/
    crc32.cpp
    image.cpp
    verifier.cpp
    value.cpp
    heap.cpp
    object.cpp
    bigint.cpp
    ops.cpp
    frame.cpp
    dispatch.cpp
    vm.cpp
    errors.cpp
    references.cpp
    modules.cpp
    externs.cpp
    tasks.cpp
    task_pool.cpp
    host_io.cpp
    builtins_core.cpp
    native_methods_arr.cpp
    native_methods_str.cpp
    native_methods_char.cpp
    native_methods_map.cpp
    native_methods_set.cpp
    native_methods_tup.cpp
    native_methods_file.cpp
    native_methods_task.cpp
    unicode_tables.cpp
    disasm.cpp
    trace.cpp
  tools/
    amalgamate.py
    pwb_probe.cpp
  tests/
    test_main.cpp
    test_crc32.cpp
    test_image.cpp
    test_verifier.cpp
    test_bigint.cpp
    test_value.cpp
    test_heap.cpp
    test_frames.cpp
    test_vm_core.cpp
    test_dispatch.cpp
    test_containers.cpp
    test_strings.cpp
    test_types.cpp
    test_errors.cpp
    test_modules.cpp
    test_references.cpp
    test_tasks.cpp
    test_disasm.cpp
  benches/
    arithmetic_loop.po
    recursion.po
    containers.po
    strings.po
    objects.po
    traits.po
    errors.po
    tasks.po
    module_load.po
    startup.po
```

```text
src/vm/native/
  __init__.py          public exports
  abi.py               C++ opcode, tag and operand header generation, --check mode
  sourcegen.py         TempCppOptions, render_temp_cpp, render_temp_cpp_into
  gcc.py               IntegratedGcc, CompileResult, Diagnostic, NativeBuildError
  cache.py             NativeBuildKey, NativeBuildCache
  meta.py              PWBM function, call and type spec metadata
  pack.py              module manifest, project snapshot, multi image embedding
  differential.py      native, Python VM and tree comparison runner
  bench.py             native benchmark runner
  cli.py               powang vm native subcommands
```

### 2.2 Layer boundaries

The native VM is split into libraries with one direction of dependency. Higher layers depend on lower layers, never the reverse.

| Layer | Owns | Depends on | Exposes |
|---|---|---|---|
| `value` | `Value`, tags, scalars, truthiness, equality, hashing | C++ standard library only | value constructors, predicates, hash and equality |
| `heap` and `object` | allocation, reference counting, strings, arrays, tuples, maps, sets, functions, objects, errors, tasks, references | `value` | `Heap::allocate_*`, `retain`, `release`, `copy_value`, `ensure_unique` |
| `image` | byte reader, CRC32, constants, tables, code objects, PWBM metadata | `value` | `Image::from_bytes`, table accessors |
| `verifier` | opcode decode, instruction array, stack dataflow, cross table checks | `image`, `value` | `verify_image(image, mode)` |
| `frame` | local slots, operand stack, handler stack, source span, generation | `value`, `image` | `Frame`, `FrameStack`, slot addressing |
| `dispatch` | argument binding, overload scoring, method and trait selection, builtin and native tables | `heap`, `frame` | `call_*` functions |
| `vm` | execution loop, opcode handlers, error unwinding, task entry | `dispatch`, `frame`, `errors` | `VM::run`, `VM::run_code`, `VM::call_value` |
| `host` | stdout, stderr, stdin, files, system, clock, module bytes, externs, worker pool | platform APIs | `Host` interface and `DefaultHost` |
| `disasm` and `trace` | read only views | `image`, `verifier` | text and JSON output |
| `cli` | process boundary, argument parsing, exit codes | everything above | `pwb_probe`, `pwb_run` |

Hard rules.

1. `image` never executes user code.
2. `verifier` never allocates language values except decoded instructions.
3. `value` never includes `heap`.
4. `vm` never includes a platform header. All I/O goes through `Host`.
5. `dispatch` never touches the operand stack directly. It receives values and returns a value or an error.
6. `host` never sees a `Frame`, a stack pointer or a raw slot.
7. The compiler, checker and LSP are never part of the native binary.

### 2.3 The C++17 value model

Three representations were considered.

| Criterion | Tagged union | `std::variant` | Tagged pointer |
|---|---|---|---|
| Size | 16 bytes with an 8 byte payload and a separate tag word | 24 to 32 bytes for this value set | 8 bytes |
| Tag access | one load | `index()` call, often inlined | bit mask and shift |
| Copy cost | plain 16 byte copy | visits the active alternative, may run constructors | plain 8 byte copy |
| Destructor | trivial, no hidden work | non trivial, may throw during assignment | trivial |
| ABI stability | explicit and documented | implementation defined | explicit but machine dependent |
| Debugging | every field visible | alternative hidden behind library types | pointer bits must be decoded |
| 63 bit inline integer | direct | direct | requires spare bits or boxing |
| IEEE double immediate | direct | direct | needs NaN boxing tricks |
| Exception safety | full control | library controlled | full control |
| Recommendation | yes | no | no |

#### Decision

The reference native VM uses a 16 byte tagged union.

```cpp
namespace pwb {

enum class Tag : std::uint8_t {
    Nova = 0, Undef, Bool, Int, Num, Char, Str, Arr, Tup, Map, Set,
    Fun, Obj, Module, Task, Error, Ref, Handle, Project, Any,
};

struct Value {
    std::uint64_t payload;   // int64 bits, double bits, char32, bool, or pointer
    Tag tag;                 // 1 byte
    std::uint8_t flags;      // 1 byte, defined, weak, big, const, locked
    std::uint16_t aux;       // 2 bytes, reserved for variant or future use
    std::uint32_t reserved;  // 4 bytes, keeps the size at 16
};

static_assert(sizeof(Value) == 16, "Value must stay 16 bytes");

} // namespace pwb
```

Reasons for the tagged union.

1. It is trivially copyable. Operand stack pushes, slot stores, swaps and frame copies are plain 16 byte moves.
2. The tag is explicit, so a switch dispatch reads it directly and the compiler can keep it in a register.
3. It has no hidden destructor. Language errors use explicit error values, not C++ exceptions, so value destruction must not throw or allocate.
4. It is easy to inspect in a debugger and in a crash dump.
5. It leaves room for the 63 bit inline integer and for an immediate double without NaN boxing.
6. It can later be replaced by a tagged pointer behind the same accessor API if the performance work justifies it.

Reasons against `std::variant`.

1. It is larger for this tag set.
2. `std::visit` and `index()` add indirection in the hottest loop.
3. Its assignment and destruction are non trivial and can throw, which complicates a VM that must unwind predictably.
4. It hides the tag, which makes a computed goto dispatch and inline caches harder.

Reasons against a tagged pointer.

1. NaN boxing gives 8 bytes but forces either heap boxing of some doubles or a restricted double range, which does not match the language's `num` type.
2. Low bit tagging collides with pointer alignment and makes bigint, char and bool packing awkward.
3. It saves 8 bytes per slot at the cost of much harder debugging and a more fragile ABI.
4. It is an optimization, not a first implementation.

#### Integers

The compiler already uses the signed 63 bit range. In `src/vm/compiler.py`, integer literals use `LOAD_INT` only when `-(1 << 62) <= integer < (1 << 62)`. Larger values use `LOAD_BIGINT`.

The native VM follows the same boundary.

1. Inline integers cover `[-4611686018427387904, 4611686018427387903]`.
2. An inline integer is stored in `payload` as a sign extended `std::int64_t`.
3. A value outside the range is a `BigInt` heap object with the `Int` tag and the `FlagBig` bit set.
4. `LOAD_INT` verifies the operand is inside the inline range. The current Python compiler already guarantees this.
5. `LOAD_BIGINT` parses the decimal string constant into a `BigInt`.
6. Arithmetic promotes to `BigInt` on overflow and demotes back to inline when the result fits.
7. Division and modulo follow the language rules, including the negative operand behavior and the divisor sign for modulo. Division and modulo by zero return nova, matching the Python VM.
8. A `BigInt` is immutable. Arithmetic returns a new `BigInt`.
9. The implementation is a signed magnitude value with base `2^32` limbs. It provides parse decimal, format decimal, compare, add, subtract, multiply, divide with remainder, negate and convert to double.
10. Mixed integer and number arithmetic converts the integer to double with the same rounding as Python `float`.

#### Numbers

A `num` is an IEEE 754 double stored in `payload` by bit copy. C++17 has no `std::bit_cast`, so the value layer uses a small `memcpy` helper. NaN payloads are not part of language equality. `num` equality follows the language rules in `performOperation`, including the treatment of NaN in comparisons.

#### Booleans, chars, nova and undef

1. `Bool` stores 0 or 1 in `payload`.
2. `Char` stores a `char32_t` scalar value. Surrogates and values above `U+10FFFF` are rejected at construction and by `LOAD_CHAR`.
3. `Nova` stores 0.
4. `Undef` is the internal undefined marker. `flags` carries `FlagDefined = 0`.
5. `is_defined` is true unless the tag is `Undef`.
6. `weak` and `const` are flag bits used by type checks, not separate tags.

#### Strings

The reference native VM uses UTF-32 code points.

```cpp
struct StringObject {
    std::vector<char32_t> code_points;
    std::string utf8_cache;   // lazily built for output and host calls
    bool ascii_only;
};
```

Reasons.

1. String indexing, iteration and spread return `char`. A UTF-32 array gives O(1) indexing and exact code point semantics with no index table.
2. Slicing is a direct range copy.
3. The Python VM uses Python `str`, which is code point based. UTF-32 is the closest native match.
4. Memory overhead is acceptable for the corpus. ASCII-heavy text uses four bytes per character, which is a known cost.
5. A later optimization can add an ASCII flag and a compact one byte representation behind `StringObject::code_point_at`. The public API does not change.

`StringObject` is immutable after construction. Literals from the constant pool are shared by reference. Concatenation and slicing allocate a new object. No copy-on-write is needed for strings.

#### Arrays

```cpp
struct ArrayObject {
    std::vector<Value> items;
    bool shared = false;
    bool structure_locked = false;
    bool elements_locked = false;
};
```

`COPY` implements value semantics. The reference native VM starts with a deep copy that matches `PowangCopyConstruct` exactly, including the identity memo that preserves cycles and shared references inside one copy. Once the copy corpus is green, `COPY` may become a retain plus a `shared` bit, and every mutation calls `ensure_unique`.

`ensure_unique` detaches a shared array before a structural or element write. The detach copies the container and recursively applies the same rule to values that the language copy would copy. The observable result must be identical to the deep copy. The CoW switch is behind `Heap::copy_value` and can be disabled with a build flag if a copy bug appears.

#### Maps and sets

A map is an insertion ordered table.

```cpp
struct MapObject {
    struct Entry { Value key; Value value; bool live; };
    std::vector<Entry> order;                 // insertion order, stable
    std::unordered_map<Value, std::size_t, ValueHash, ValueEq> index;
    bool shared = false;
    bool structure_locked = false;
    bool elements_locked = false;
};
```

1. Keys use language equality and hashing, not pointer identity, for scalars, strings and tuples.
2. User objects hash by identity unless the `Compare` trait participates. Identity hashing is allowed because iteration order is insertion order, never hash order.
3. Deleting a key marks the entry dead and keeps its position. Iteration skips dead entries.
4. Rehashing rebuilds the index only. The order vector is never reordered.
5. `keys`, `values` and iteration walk the order vector.
6. A set reuses the map layout with the value omitted, or a dedicated `SetObject` with the same order and index structures.
7. Hashes are deterministic for a given value and process. No randomized seed is used.
8. The hash of a string is a stable function of its code points, not of its address.
9. The hash of a tuple or array is structural. Arrays are valid keys only if the language allows them, which the runtime checks in the same place as the Python VM.

#### Tuples

A tuple is an immutable vector of values. It is always shared by reference. `COPY` of a tuple still performs the language copy of its elements, because the elements may be mutable containers. This matches `PowangCopyConstruct`.

#### User objects

```cpp
struct ObjectObject {
    const TypeInfo* type;
    std::vector<Value> fields;       // declaration order, field ID is the index
    std::uint32_t variant = 0;       // enum variant, 0 for ordinary objects
    bool is_enum = false;
    bool defined = true;
    bool weak = false;
    bool structure_locked = false;
    bool elements_locked = false;
    bool shared = false;
};
```

1. The type table is in the image. An object does not own a method table copy.
2. Field IDs are indices into `fields`. The compiler and the image type table define the order.
3. Enums are objects with `is_enum`, a type ID and a variant ID. They compare by type and variant.
4. Private properties are a compile time concern. Dynamic member access checks the same visibility rules as the Python runtime.
5. `SET_LOCKS` sets `structure_locked` and `elements_locked` from the flag operand.

#### Functions and closures

```cpp
struct FunctionObject {
    const CodeObject* code;
    const FunctionMeta* meta;
    std::vector<Value> captures;
    Value bound_this;
    bool is_async;
    bool variadic;
};
```

Defaults are code indices in `FunctionMeta`, not evaluated values. They are evaluated in the callee frame as the Python VM does. A function value shares its closure by identity, matching the language rule that function values share closures.

#### Any and union boxes

```cpp
struct AnyObject {
    Value concrete;
    std::uint32_t declared_spec;
    bool defined;
    bool weak;
    std::string concrete_type_name;
};
```

`BOX_ANY` and `UNBOX_ANY` behave exactly like `PowangAnyType` and `PowangUnwrapAny`. When the static type is concrete, the unboxed value is used directly.

#### References

```cpp
struct ReferenceObject {
    enum class Kind : std::uint8_t { Local, Global, Field, Index };
    Kind kind;
    Frame* frame;                 // local
    std::uint32_t slot;
    std::uint64_t frame_generation;
    ModuleRuntime* module;        // global
    std::uint32_t name_id;
    Value owner;                  // field or index
    std::uint32_t field;
    Value index_value;
};
```

A reference is valid only for one call. Local references check the frame generation and reject a stale frame. Field and index references hold their target value alive with a reference count. A reference cannot be copied into a variable, field or container. The verifier catches the static cases and the runtime catches the dynamic cases.

### 2.4 Heap, allocation and copy semantics

The heap is a `Heap` object owned by the VM session and shared by worker tasks.

1. Every heap object has a header with `Tag`, `HeapKind`, reference count, flags and an optional type ID.
2. `Heap::retain` and `Heap::release` are explicit. `Value` copies do not change the count automatically.
3. Slot stores, operand pushes and container writes call `retain` through the value operations layer.
4. Slot overwrites, operand pops that discard a value and container clears call `release`.
5. A per frame deferred release list prevents a release from freeing an object while the current instruction still reads it.
6. The frame local array and operand stack are the root set for a future tracing collector. The allocator interface is designed so a collector can replace reference counting without changing callers.
7. Debug builds track allocations, live counts and double releases. `PWB_DEBUG_HEAP=1` prints a leak report at shutdown.
8. N0 and N1 may use a `Heap::Policy::Arena` that never frees until VM teardown. That removes ownership bugs from the first gate. N2 switches to reference counting behind the same API and the same tests must stay green.
9. The recommendation is reference counting for the reference native VM because it gives deterministic release and avoids stop the world pauses for the corpus. A tracing collector remains a later option.

Copy semantics are the highest risk area. The native implementation follows the Python definition, not an approximation.

1. `copy_value` deep copies arrays, tuples, maps, sets and user objects.
2. It uses an identity memo so a cycle or a repeated reference inside one value is preserved.
3. Scalars and immutable strings return the same value.
4. Functions share closures.
5. Tasks, files, modules, handles, project values and references keep identity.
6. `COPY` is emitted by the compiler at the documented boundaries.
7. CoW is an optimization of `copy_value`, never a semantic change.

### 2.5 Frames, slots and the operand stack

A frame owns a fixed local array and a fixed operand stack region. Both are carved from a per VM slot arena so addresses stay stable for references.

```cpp
struct Frame {
    const CodeObject* code;
    Value* locals;
    std::uint32_t local_count;
    Value* stack;
    std::uint32_t sp;
    std::uint32_t max_stack;
    std::uint32_t ip;
    std::uint32_t span_index;
    Value receiver;
    FunctionObject* closure;
    ModuleRuntime* module;
    Task* task;
    std::vector<HandlerEntry> handlers;
    Value pending_return;
    ErrorRef pending_error;
    Transfer transfer;
    std::uint32_t scope_depth;
    std::uint64_t generation;
    bool is_function;
};
```

#### Local slots

1. The compiler assigns a slot for every parameter, declaration, destructuring binding, match binding and hidden temporary.
2. `local_count` is the exact size. The frame allocates that many `Value` slots and initializes them to `Undef`.
3. `LOAD_LOCAL` and `STORE_LOCAL` use the operand slot directly. No name lookup happens at runtime.
4. `LOAD_NAME`, `STORE_NAME`, `LOAD_GLOBAL` and `STORE_GLOBAL` use the image `global_names` table and the module store.
5. `LOAD_RAW` and `STORE_RAW` bypass the reference unwrap that `LOAD_LOCAL` performs. They are used by the compiler for hidden slots.
6. Slot values are never renumbered while a frame runs.

#### Block scopes

The Python VM uses `SCOPE_PUSH`, `SCOPE_POP` and a name map to hide block locals. The native VM has no name map for locals, so block scopes are a compile time construct.

1. `SCOPE_PUSH` increments `frame.scope_depth` and records a local watermark for debug and error parity.
2. `SCOPE_POP` restores the watermark and decrements the depth. It does not move values.
3. Hidden slots keep their values until the frame returns. Later instructions never address them.
4. A reference that escapes its block is rejected by the verifier when it can prove the case and by the frame generation and watermark at runtime.
5. The block scope corpus from `tests/test_vm_runtime.py` is part of the N1 gate.

#### Operand stack

1. `stack` is a contiguous `Value` region of `max_stack` entries.
2. `sp` is the number of live entries.
3. Every instruction checks `sp` against its stack input in debug builds. The verifier guarantees the heights in strict mode.
4. `DUP`, `DUP2`, `SWAP`, `ROT3` and `ROT` are direct array operations.
5. `ITER_NEXT` keeps the iterator on the stack and jumps on exhaustion, matching the Python behavior.

#### Exception handlers

```cpp
struct HandlerEntry {
    std::int32_t start_ip;
    std::int32_t end_ip;
    std::int32_t catch_ip;
    std::int32_t finally_ip;
    std::int32_t resume_ip;
    std::uint32_t stack_depth;
    std::uint32_t local_watermark;
    std::uint8_t kind;        // catch or finally
    std::uint8_t state;       // active, catch, finally
    std::uint32_t scope_depth;
    Value pending_return;
    ErrorRef pending_error;
};
```

1. The image exception table is decoded into `CodeObject::exceptions`.
2. `TRY_BEGIN` finds the entry whose `start_ip` equals the next instruction offset and pushes a handler. The lookup uses a precomputed map from start offset to entry index.
3. `TRY_END` pops the innermost handler.
4. `FINALLY_END` rethrows a pending error or resumes at `resume_ip`.
5. `_handle_error` in the Python VM is the reference. The native version walks handlers from innermost to outermost, restores `sp` to `stack_depth`, and transfers to catch or finally.
6. `PROPAGATE`, `RETHROW`, `SET_RETURN`, `SET_TRANSFER`, `JUMP_IF_TRANSFER`, `APPLY_TRANSFER` and `ABANDON_FINALLY` are ported together and tested together. They are the most delicate opcodes in the error model.
7. If a finally block throws, the new error replaces the original and becomes the active error. The original is attached as the cause when the language supports it.

#### Source spans

1. Every decoded instruction carries `span_index`.
2. `CodeObject::spans` carries the `SourceSpan` records.
3. `frame.span_index` is updated before each dispatch, exactly as `_execute` does.
4. Error text uses the span of the faulting instruction, not the next one.
5. When `span_table` is empty, the span index is 0 and the position is `0:0`.

#### Call frames and return values

1. `FrameStack` is a vector of `Frame` values with a stable arena for locals and stacks.
2. `max_frames` defaults to 900, matching `VMRunOptions`.
3. A call appends one `FrameInfo` to the VM call stack for error rendering.
4. `RETURN` pops the result, applies the copy when `frame.is_function`, pops the frame and pushes the result in the caller.
5. `APPLY_TRANSFER` handles the finally return path. It performs the same copy rule.
6. A native frame never exposes its stack to the host.

### 2.6 Image reader and verifier

#### Container

The reader mirrors `src/vm/image.py` byte for byte.

1. Magic `PWB1`.
2. `u16` format version, expected 1.
3. `u16` image flags.
4. `u16` language version length and UTF-8 bytes.
5. `u32` table count, expected 14.
6. Fourteen `u32` table lengths followed by table bytes in this order: `meta`, `modules`, `types`, `traits`, `functions`, `constants`, `call_sites`, `patterns`, `type_specs`, `sources`, `global_names`, `strings`, `debug_lines`, `codes`.
7. `u32` CRC32 of every byte before the checksum.

All integers are little endian. The reader never casts a table pointer to a struct. It uses explicit byte reads or `memcpy` plus a conditional byte swap on a big endian host.

#### CRC32

The checksum is the standard reflected CRC-32 used by `zlib.crc32`: polynomial `0xEDB88320`, initial value `0xFFFFFFFF`, final XOR `0xFFFFFFFF`. The implementation uses a 256 entry table generated at compile time. Tests use the standard vectors, including `""` gives `0x00000000` and `"123456789"` gives `0xCBF43926`, and a comparison against Python `zlib.crc32` over the example images.

#### Table bounds

The reader rejects an image before allocating large tables when any count or length cannot fit in the remaining bytes.

1. Total image limit: 256 MiB by default.
2. Per table limit: the remaining image size.
3. String length limit: the remaining table size.
4. Code bytecode length limit: the remaining code record size.
5. Constant count, span count, exception count, local name count and parameter name count are checked against the remaining record.
6. Trailing bytes in a table are an error, matching `_finish`.
7. Unknown constant tags, unknown exception kinds and unknown format versions are errors with the byte offset.
8. UTF-8 is validated by a strict decoder that rejects overlong encodings, surrogates and values above `U+10FFFF`.

#### Constants

1. `nova`, `bool`, `int`, `bigint`, `num`, `str`, `char` and `tuple` are decoded into native values or value descriptions.
2. `call`, `pattern`, `type`, `trait` and `function` hold u32 indices and are validated against their tables.
3. `ast`, `descriptor`, `spec` and `extern` are JSON strings in the Python image. The native reader stores the raw text and the byte range. It does not parse arbitrary AST.
4. A `spec` constant must be resolved through the PWBM metadata block. If it is missing, the image loads but the instruction that uses it reports `unsupported: missing native type spec`.
5. `descriptor` constants used by `MAKE_ERROR`, `DESTRUCTURE` and `DECLARE_EXTERN` must also have a PWBM entry. `extern` descriptors report unsupported until the host extern table exists.
6. `fallback_ast` is ignored by the native VM. It is never evaluated.

#### PWBM metadata block

The Python image stores several runtime shapes as AST JSON because the Python engine can evaluate them. A native VM cannot. The plan adds a compact, deterministic `PWBM` block derived mechanically from the same `ProgramImage`.

The block is not a second image and not a second source of truth. It is a compiled cache of shapes that already exist in the image objects.

1. Magic `PWBM`, u16 version 1, u16 flags.
2. Image SHA-256, so a stale block is rejected.
3. Function table: name, code index, min argc, variadic index, flags, parameter count, and per parameter name, type spec index, reference flag, weak flag and default code index.
4. Type spec table: a compact tree with kind, name, arguments and flags. It is produced from `src.typespec.from_ast_node` on the same nodes the compiler used.
5. Constant spec map: `(code_index, constant_index)` to type spec ID, so a `spec` operand resolves without JSON parsing.
6. Descriptor table for `MAKE_ERROR`, `DESTRUCTURE` and `PATTERN` literals that are scalar or tuple values.
7. CRC32 of the block.

The generator lives in `src/vm/native/meta.py` and exposes `build_meta(image)`, which returns `bytes`. A test builds the same image twice and asserts identical bytes, and asserts that the block hash in the generated `temp.cpp` matches the image hash.

The long term goal is a future `PWB2` format that folds these fields into the main image so a bare `PWB1` is sufficient. Until then, a bare image loads in core mode and reports a clear unsupported error for a call or cast that needs the missing metadata.

#### Opcode boundaries

1. The verifier decodes all code objects at load, not lazily.
2. Each `Instruction` stores the opcode byte, a union of decoded operands, the byte offset, the next offset and the span index.
3. `offset_to_index` maps every instruction start to its index. A jump to a non boundary is rejected.
4. A truncated operand is rejected with the opcode name and offset.
5. An unknown opcode is rejected with the byte value and offset.
6. `CodeObject::instructions` is the only form the VM executes. The raw bytecode is kept for disassembly and cache hashing.

#### Stack height dataflow

The dataflow mirrors `_analyze_stack` in `src/vm/verifier.py`.

```text
heights[0] = 0
worklist = [0]
while worklist is not empty:
    offset = pop front
    height = heights[offset]
    instruction = instructions[offset_to_index[offset]]
    stack_in, stack_out = stack_effect(instruction, image, code)
    if stack_in >= 0 and height < stack_in:
        fail stack underflow
    result_height = height - stack_in + stack_out
    for (successor, successor_height) in successor_heights(instruction, end, height, result_height):
        if heights[successor] is unset:
            heights[successor] = successor_height
            push successor
        elif heights[successor] != successor_height:
            fail merge mismatch
```

Successor rules from `verifier.py` are binding.

1. `JUMP` goes only to its target.
2. Conditional jumps, `MATCH`, `ITER_NEXT` and `JUMP_IF_TRANSFER` go to the target and to the next instruction when it differs.
3. `RETURN`, `THROW` and `RETHROW` have no successor.
4. Every other opcode goes to the next instruction when it is inside the code.
5. `ITER_NEXT` pushes one value on the continue path and pops the iterator on the exit path.

Variable height opcodes use the operand count or the call site.

1. `ROT` uses `count` in and `count` out.
2. `MAKE_ARRAY`, `MAKE_ARRAY_TYPED`, `MAKE_TUPLE`, `MAKE_TUPLE_TYPED`, `MAKE_MAP`, `MAKE_MAP_TYPED`, `MAKE_SET`, `MAKE_SET_TYPED` and `CONCAT_STR` use `count` in and one out.
3. Call opcodes use the call site argument count, plus the receiver or callee slot for the forms that need one.
4. `CONSTRUCT` uses the call site argument count.
5. `MAKE_ERROR` uses the descriptor `argument_count`.
6. `HOST_CALL` uses its own descriptor once the host table exists.

#### Strict and trusted modes

```cpp
enum class VerifyMode { Strict, Trusted };
```

Strict mode runs every check, including stack dataflow, `max_stack`, reachable return, exception ranges, span indices, cross table references and reference lifetime.

Trusted mode validates the container, the CRC, the table bounds and the opcode decode, but skips the dataflow and the deep cross table checks. It is used only for an image whose SHA-256 and CRC match an artifact that was strict verified in the same build or whose cache metadata records `verified: true`.

A bare image from disk always uses Strict mode unless the caller passes `--trusted`. The CLI never defaults to trusted.

#### Runtime guards

The verifier cannot catch dynamic failures. The native runtime still checks:

1. Index bounds and negative index normalization.
2. Division by zero.
3. Invalid cast and invalid type comparison.
4. Undefined value use.
5. Const and element lock violations.
6. Module mutation.
7. Reference escape and stale frame.
8. Task cancellation.
9. Stack and frame limits.
10. Instruction budget when configured.

### 2.7 Call dispatch and overload scoring

The native dispatcher must reproduce `src/vm/dispatch.py` and the scoring function in `src/runtime.py` exactly. A difference in overload selection is a semantic difference even when both programs produce plausible output.

#### Call site descriptor

The image `CallSite` already carries the binding shape.

1. `dispatch`: `call`, `value`, `method`, `static`, `module`, `native`, `builtin`, `trait`, `operator`, `extern`, `async`, `async_method`, `spawn`, `construct`.
2. `name`, `module`, `type_name`, `trait_name`, `operator_trait`, `native_type`.
3. `positional_count`, `argument_kinds`, `argument_names`.
4. `type_argument_count`, `return_spec`, `is_async`.

The compiler pushes receiver and arguments in a stable order. The call handler pops exactly the number of values the verifier computed.

#### Argument flattening

`flatten_arguments` is ported first, before any callee resolution.

1. Walk `argument_kinds` and `argument_names` in source order.
2. A `SpreadValue` wrapper expands through `_spread_values`.
3. A named argument goes into the named list with its declared name.
4. Everything else goes into the positional list in evaluation order.
5. A string spread produces characters. A map spread produces key value tuples. An array, tuple or set spread produces members.
6. The spread error text must match the Python `spread_values` helper.

#### Identifier calls

`call_identifier` order is binding.

1. Look up the name in the current scope function table.
2. Apply the `type_argument_count` filter when it is nonzero.
3. If named arguments are present, require exactly one overload and use it.
4. Otherwise call `getFunctionCandidate` on the positional arguments.
5. If the candidate is an external function, call it through the host extern bridge.
6. If the name is in the state extern table, use that binding.
7. If the name is in `BUILTINS`, check arity and call the builtin.
8. If the name is a variable holding a function, call the value.
9. Otherwise raise the same `identifier not found` error as the Python VM.

#### Method, static, module, native, trait and operator calls

1. `CALL_METHOD` unwraps the receiver. A module receiver goes to `callModuleMember`. A native type receiver goes to `call_native_method`. A user object uses `_resolve_instance_method` with the same trait search order.
2. `CALL_STATIC` reads the type from the scope type table, checks privacy, then selects the overload.
3. `CALL_MODULE` uses the module value or falls back to a value call.
4. `CALL_NATIVE` rejects named arguments and calls the native method table with the receiver prepended.
5. `CALL_TRAIT` requires a user object receiver, a known trait and a method in the trait table, then the unqualified table, then the default trait methods.
6. `CALL_OPERATOR` requires an object receiver and uses `_call_operator_method` with the operator trait and the site name.
7. Async variants create a lazy task instead of calling immediately.
8. `CONSTRUCT` delegates to the constructor binder and the type field initialization.

#### Overload scoring

The score is the sum of arity and parameter scores. The native implementation ports `_score_parameter` and `_score_parameter_spec` literally.

```text
score_parameter(spec, value):
    concrete = unwrap_any(value)
    source = value_type_spec(concrete)
    if spec.name == "any" or source.name == "any":
        return 1
    if spec.kind == UNION:
        if spec.args is empty:
            return 1
        return max(score_parameter(branch, concrete, source) for branch in spec.args)
    return score_parameter_spec(spec, concrete, source)

score_parameter_spec(spec, concrete, source):
    if spec.name == "any" or source.name == "any":
        return 1
    if spec == source:
        return 3
    if spec.name == concrete.type_name or spec.name == concrete.type:
        return 3
    if assignable(spec, source):
        return 2
    if explicit_cast(spec, concrete) succeeds:
        return 1
    return -1
```

```text
get_function_candidate(functions, arguments):
    scores = [0] * len(functions)
    for each function:
        if len(arguments) == len(function.params):
            score += 3
        elif len(arguments) == function.min_argc:
            score += 2
        for each (param, argument) in zip(function.params, arguments):
            score += score_parameter(param.spec, argument)
            if param.weak:
                if argument.weak:
                    score += 1
                if not argument.weak.has_value:
                    score += 2
            elif not argument.weak.it_is:
                score += 1
    choose the unique maximum
    on a tie raise OVERLOAD ambiguous call with the candidate list
```

The native `TypeSpec` must implement structural equality, `assignable`, `explicit_cast` and `runtime_type_matches` with the same results as `src/typespec.py` and `src/runtime.py`. N3 is the gate for this work because user types and traits exercise it most, but N1 needs the scalar subset for typed declarations and returns.

A scorer parity test generates a table of specifications and values in Python, runs the Python scorer and the native scorer, and compares every score and every selected candidate.

### 2.8 Error model and unwinding

#### Error value

A language error is a value, not a C++ exception.

```cpp
enum class ErrorKind : std::uint16_t {
    Generic, Syntax, Type, Argument, Index, Divide, Cast, Operation,
    Module, Const, Reference, Task, File, User, Implementation,
    Recursion, Budget, Development, Compile, Usage, Internal,
};

struct ErrorInfo {
    ErrorKind kind;
    std::string kind_name;          // the exact uppercase name used in text
    std::string message;
    std::vector<std::string> details;
    std::string where;
    std::int32_t line = 0;
    std::int32_t column = 0;
    std::vector<std::string> frames;
    std::shared_ptr<ErrorInfo> cause;
    std::string base_text;
};
```

The exact text format from `src/error.py` is binding.

```text
[KIND ERROR] (in where) message:
      | detail one
      | detail two
```

When `line` is set, `render_text` prefixes `ln: N | `. When `kind` is the generic `ERROR`, the bracket is `[ERROR]`. The native formatter must reproduce these strings byte for byte.

#### Unwinding

1. `throw_error(ErrorRef)` stores the error in the current frame and calls `handle_error`.
2. `handle_error` walks `frame.handlers` from the last entry to the first.
3. A handler matches when `start_ip <= fault_ip < end_ip` and its state is active.
4. A catch handler truncates `sp` to `stack_depth`, sets state to catch, clears pending state, sets `ip` to `catch_ip` and pushes an error value.
5. A finally handler truncates `sp`, sets state to finally, stores the pending error, sets `ip` to `finally_ip` and continues.
6. If no handler in the frame matches, the frame is popped and the error propagates to the caller with one appended frame record.
7. `FINALLY_END` rethrows a pending error, otherwise resumes at `resume_ip`.
8. `RETHROW` throws the error value on the stack.
9. `PROPAGATE` checks whether the value is an error. If it is and the frame is a function, it runs an enclosing finally with a pending return, or returns the error value as the frame result. This follows the Python code at `interpreter.py` lines 1260 to 1285.
10. `SET_RETURN`, `SET_TRANSFER`, `JUMP_IF_TRANSFER`, `APPLY_TRANSFER` and `ABANDON_FINALLY` are ported as one unit with dedicated tests.

#### Frames and positions

1. Every active call appends a `FrameInfo` with the function name and the source position of the caller.
2. The render format is `at <name> (<file>:<line>:<column>)`, exactly as `src/state.py` renders a frame.
3. Frames are attached on the way out, in reverse call order, once per error.
4. The source span of the faulting instruction is used. A span with line 0 is treated as unknown.
5. Error text, frame list and exit code are part of the differential corpus.

#### Internal errors

Internal failures such as a malformed image, a missing host callback or an unhandled opcode are not language errors. They use `Status` with a code and a message and map to CLI exit code 3. A language error maps to exit code 1. A usage error maps to exit code 2. An interrupt maps to 130. This matches the Python CLI contract. The implemented N0 native CLI returns 1 for image, verifier and runtime errors and 0 on success. Exit code 3 for image and verifier failures remains a later design option.

### 2.9 Async and tasks

The language has lazy tasks and worker tasks. It has no coroutine suspension at arbitrary expression boundaries. The native VM preserves that model exactly.

#### Task object

```cpp
struct Task {
    enum class State : std::uint8_t { Pending, Running, Completed, Failed, Cancelled };
    State state;
    std::uint64_t id;
    FunctionObject* closure;
    std::vector<Value> arguments;
    Value receiver;
    Value result;
    ErrorRef error;
    std::atomic<bool> cancelled;
    std::mutex mutex;
    std::condition_variable completed;
    std::thread::id worker;
    std::chrono::steady_clock::time_point created;
    std::chrono::steady_clock::time_point finished;
};
```

#### Lazy tasks

1. `CALL_ASYNC`, `CALL_ASYNC_METHOD` and the async forms of a call create a `Pending` task with a closure and evaluated arguments.
2. The body does not start.
3. `AWAIT` on a pending lazy task runs it on the current thread in a nested `VM::run_code` call that shares the heap, module table and host.
4. The task moves to `Running`, then `Completed` or `Failed`.
5. A second `AWAIT` returns the stored result.
6. A lazy task that is never awaited is released at VM shutdown without running.

#### Worker tasks

1. `SPAWN` creates a task and submits it to the `TaskPool`.
2. A worker takes the task, creates a `VMContext` with its own frame stack and slot arena, and shares the `Heap`, `ModuleTable` and `Host`.
3. The worker catches every C++ exception and every language error, stores the error in the task and never lets it cross the thread boundary.
4. `AWAIT` on a worker task waits on the condition variable and then returns or rethrows the stored result.
5. `wait` with a timeout returns a task status or raises a timeout error, matching the Python builtin.
6. `cancel` sets the atomic flag. A lazy task becomes cancelled. A worker task observes the flag at `CHECK_CANCEL`, at call boundaries and at backward jumps.
7. `task_status` reads the state under the mutex.
8. `shutdown` sets the stop flag, drains the queue, joins every worker and releases task objects.

#### Thread safety

1. The heap allocator uses a mutex in N5. This is correct first and fast later.
2. Heap reference counts are `std::atomic<std::uint32_t>` once worker tasks exist. A single thread build may use a plain count behind a compile time switch.
3. Container mutation on a shared object uses the same heap mutex or a per object mutex when contention is measured.
3. Module tables are immutable after initialization. Initialization uses a single module lock with a depth first state machine.
4. A task result and error are published under the task mutex.
5. The differential corpus uses deterministic programs. Output ordering across concurrent spawns is not part of language equality, so the harness runs the async corpus with one worker unless the test explicitly checks concurrency.

#### Cleanup

1. `VMSession::shutdown` joins workers, releases modules, releases the heap and reports leaks in debug builds.
2. A task that fails after the VM has begun shutdown is discarded with a recorded warning in debug mode.
3. Repeated start and shutdown cycles are a stress test.

### 2.10 Modules, project, packages, externs and the host ABI

#### Modules

1. A module is a `ModuleRuntime` with a name, resolved path, global store, function table, type table, wildcard table, export table and initialization state.
2. Initialization is depth first. A module is marked initializing before its code runs and initialized after it completes. A cycle is a `MODULE` error.
3. `IMPORT` reads `module_info.imports[0]`, asks the host for the module, checks for an alias collision, binds the module value to the local slot and applies the legacy wildcard behavior.
4. `IMPORT_WILDCARD` copies the exports into the current module scope.
5. `LOAD_MODULE_MEMBER` resolves the export name and returns the value.
6. `EXPORT` is a no-op at runtime except for the module export table built at load.
7. A module value is immutable after initialization. Member assignment is a runtime error.

#### Module images

The native VM does not compile source. Imports must be compiled to `PWB1` at build time.

1. `src/vm/native/pack.py` walks the module graph with the existing Python module loader.
2. It compiles every reachable `.po` file to a `ProgramImage` and serializes it.
3. The entry image is embedded in `temp.cpp`.
4. The imported images are either embedded in a `kModules[]` table in single file mode or written to `build/native/modules/<id>.pwb` and described by a manifest.
5. The manifest maps module name and resolved path to an image file, its SHA-256 and its exports.
6. `Host::load_module` reads the manifest and the image bytes.
7. The native module cache is keyed by resolved path and content hash, matching the Python `BytecodeCache` rules.

#### Project and packages

Project and package resolution is a build time concern.

1. `src/vm/native/pack.py` reads `project.po` and the package configuration through the existing Python code.
2. It produces a `ProjectSnapshot` with `modules`, `paths`, `logLevel`, `allowSystem` and package roots.
3. The snapshot is embedded as C++ string constants.
4. `LOAD_PROJECT` returns a `ProjectObject` built from the snapshot.
5. The native VM never parses `project.po`, never reads a lock file and never downloads a package.
6. A project that changes between build time and run time is a rebuild, not a runtime resolution.

#### Externs

`DECLARE_EXTERN` is Python specific in the current implementation. The native VM needs a stable host ABI.

1. N4 introduces an extern table keyed by name.
2. The host registers functions with `extern "C"` linkage.
3. A function receives a context handle, a pointer to 16 byte `PwbValue` arguments and a count, and returns a `PwbValue`.
4. String, array and object arguments cross the ABI as handles, not raw pointers. The host resolves handles through the VM.
5. Error propagation is a status code plus a `PwbValue` error.
6. The first version supports scalar arguments, strings and returns. Handles for files and tasks are added in N5.
7. A missing extern reports `unsupported: extern <name>` rather than crashing.

#### Host interface

```cpp
class Host {
public:
    virtual ~Host() = default;
    virtual void write_stdout(std::string_view utf8) = 0;
    virtual void write_stderr(std::string_view utf8) = 0;
    virtual bool read_stdin_line(std::string& out) = 0;
    virtual std::vector<std::uint8_t> load_module(const ModuleRequest& request) = 0;
    virtual Value project_value() = 0;
    virtual Value call_extern(std::string_view name,
                              const Value* arguments,
                              std::size_t argument_count) = 0;
    virtual Value call_builtin(std::string_view name,
                               const Value* arguments,
                               std::size_t argument_count) = 0;
    virtual Value call_native_method(std::string_view type,
                                     std::string_view name,
                                     const Value* arguments,
                                     std::size_t argument_count) = 0;
    virtual TaskPool& tasks() = 0;
};
```

The host never sees a frame, a stack or a raw slot. The builtin and native method tables can live in the runtime library, but they call the host for I/O, files, system and time.

### 2.11 Architecture decision records

#### ADR 1: Native language is C++17

Context: the request fixes C++17 and the local toolchain is `g++ 16.1.0` MinGW-W64 UCRT.

Decision: use C++17 with the standard library only. No Boost, no external runtime dependency.

Consequences: portable, familiar to the project, fast enough for the target. C++17 lacks `std::expected` and `std::bit_cast`, so the plan uses small local helpers.

Status: accepted.

#### ADR 2: Tagged union value

Context: the VM needs a compact, fast, debuggable value.

Decision: 16 byte tagged union. See 2.3.

Consequences: trivial copies and explicit ownership. The team must maintain `retain` and `release` discipline.

Status: accepted.

#### ADR 3: UTF-32 strings

Context: the language exposes code point indexing and `char`.

Decision: UTF-32 code points with a cached UTF-8 view.

Consequences: O(1) indexing and simple slicing, at the cost of memory for ASCII text. A compact representation can be added later.

Status: accepted for N0 to N6.

#### ADR 4: `PWBM` metadata sidecar

Context: `PWB1` stores function parameters, type specs and some descriptors as AST JSON. Native code cannot evaluate AST.

Decision: generate a compact `PWBM` block from the same `ProgramImage`, embed it next to the image and validate it with the image SHA-256.

Consequences: no AST parser in C++, deterministic metadata, a second artifact to keep in sync. The sync risk is mitigated by the hash and by a generator test.

Status: accepted for N0 to N6. A future format version should fold the fields into the main image.

#### ADR 5: Static runtime library by default

Context: compiling the entire runtime inside every `temp.cpp` is slow.

Decision: build `libpwb_runtime.a` once, keep the generated translation unit to the image array and a small `main`, link statically.

Consequences: fast compile, larger executable, one library to rebuild when the runtime changes. The single file mode remains available for distribution and reproduction.

Status: accepted.

#### ADR 6: Reference counting, not a tracing collector

Context: the native VM needs deterministic release and simple task cleanup.

Decision: reference counting with a frame arena and a deferred release list. No tracing collector in N0 to N6.

Consequences: predictable lifetimes, no pause, possible cycles leak. The corpus and the language do not require general cyclic container graphs, and the copy memo prevents accidental cycles in copied values. A tracing collector can replace the heap policy later.

Status: accepted.

#### ADR 7: Language errors are values, not C++ exceptions

Context: try, catch, finally, propagation and task errors need explicit stack and handler control.

Decision: language errors use `ErrorRef` values and an explicit unwinder. C++ exceptions are reserved for `std::bad_alloc` and host failures.

Consequences: predictable control flow and easier parity. Every handler must check for a pending error after a nested call.

Status: accepted.

#### ADR 8: Python VM remains the differential oracle

Context: the native VM is a new implementation and can drift.

Decision: the Python VM defines behavior for the native VM. The tree walker remains the language reference. A native difference is a native bug unless the Python VM and the tree walker also differ, in which case the native VM matches the Python VM.

Consequences: the native VM cannot be declared ready without the full differential suite.

Status: accepted.

## 3. The `temp.cpp` buffer build

### 3.1 Source generator API

The generator lives in `src/vm/native/sourcegen.py`. It is pure Python and has no side effects.

```python
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal, TextIO

from ..image import ProgramImage


@dataclass(frozen=True)
class TempCppOptions:
    mode: Literal["static_lib", "single_file"] = "static_lib"
    namespace: str = "pwb_generated"
    emit_checksum_assert: bool = False
    emit_image_comment: bool = True
    embed_metadata: bool = True
    embed_modules: bool = False
    embed_project: bool = False
    line_width: int = 16
    optimize: str = "O2"
    runtime_include: str = "pwb/embed.hpp"
    amalgamation_path: str | None = None


def render_temp_cpp(image: ProgramImage, options: TempCppOptions | None = None) -> str:
    """Render a complete C++17 translation unit and return it as text."""


def render_temp_cpp_buffer(
    image: ProgramImage, options: TempCppOptions | None = None
) -> io.StringIO:
    """Render into an in-memory text buffer and return it positioned at the start."""


def render_temp_cpp_into(
    buffer: TextIO, image: ProgramImage, options: TempCppOptions | None = None
) -> None:
    """Render into any text sink without building one large intermediate string."""
```

Implementation rules.

1. `render_temp_cpp` is a thin wrapper around `render_temp_cpp_buffer(...).getvalue()`.
2. `render_temp_cpp_into` is the real implementation. It writes many small chunks so a 1 MB source does not require a 1 MB f string.
3. The buffer is created with `io.StringIO()` and no initial value. A rough reserve is image bytes times six plus four kilobytes.
4. The generator never writes a file. The caller decides whether to send the text to `g++` or to a debug file.
5. Every generated identifier is validated. `namespace` must match `[A-Za-z_][A-Za-z0-9_]*`. `line_width` must be between 8 and 32. `mode` and `optimize` must be in their allowed sets.
6. The output is deterministic. The same image and options produce the same bytes. A test hashes the output twice.

### 3.2 What goes in the buffer and what goes in the runtime library

Recommended layout: a small generated translation unit plus a prebuilt static runtime library.

The generated `temp.cpp` contains only:

1. A header comment with the image SHA-256, image length, CRC32, language version, generator version, image flags and a warning that the file is generated and must not be committed.
2. The includes needed by `main`, normally `<cstddef>`, `<cstdint>`, `<cstdio>` and `"pwb/embed.hpp"`.
3. The image byte array.
4. The image length and CRC constants.
5. Optional `PWBM` metadata, module manifest and project snapshot arrays.
6. A `static_assert` that the array length matches the constant.
7. A small `main` that checks the CRC, loads the image and calls `pwb::run_embedded`.
8. Nothing else.

Implemented N0 note: the generated source declares `kPwbImageSize` and a `[[maybe_unused]] kPwbImageCrc`. The native image parser performs the CRC check. There is no compile time `static_assert` on the image and no separate CRC check in the generated `main`. Items 6 and 7 and the sample in section 3.3 describe the original design target.

Every item above is C++17. The generated file is a real translation unit, not a shell wrapper, and it does not start a Python process. The runtime library implements the core language natively. Host services that are not native yet go through the `Host` interface and return an explicit unsupported error.

The runtime library `libpwb_runtime.a` contains the image reader, verifier, value layer, heap, frames, dispatch, VM, host and CLI support. It is built once per toolchain and runtime version.

Reasons for this split.

1. Compile time stays low. The generated unit parses one small header, not the whole runtime.
2. The runtime is testable on its own with `pwb_probe` and `pwb_run`.
3. The cache key can include the runtime library version, so a runtime change invalidates every native artifact.
4. The generated source stays readable and reviewable.

The single file variant is still supported.

1. `mode="single_file"` writes an amalgamated runtime before the image array.
2. The amalgamation is produced by `native/tools/amalgamate.py` and cached under `build/native/runtime_amalgamated.cpp`.
3. It is intended for distribution, for reproducing a failure on a machine without the repository, and for the literal one buffer requirement.
4. It compiles slower and produces a larger source, so it is not the default.
5. The generator raises a clear error when `mode="single_file"` and the amalgamation file is missing.

The `pwb/embed.hpp` header is deliberately tiny.

```cpp
#pragma once
#include <cstddef>

namespace pwb {
int run_embedded(const unsigned char* image, std::size_t size, int argc, char** argv);
}
```

The heavy `pwb/runtime.hpp` is included only by the runtime library sources and by `pwb_run`.

### 3.3 Embedding the image bytes

The image is embedded as a byte array with a length constant and a CRC constant.

Implemented N0 note: the generated source emits `kPwbImageSize` and a `[[maybe_unused]] kPwbImageCrc`, and the native parser performs the image CRC check. The sample, the rules and the `main` below describe the original design target, which also had compile time assertions and a CRC check in `main`. The implemented N0 source has neither.

```cpp
namespace pwb_generated {

// Generated from a PWB1 image.
// image sha256: 8f0c...
// image bytes: 24545
// image crc32: 0x1a2b3c4d
// language version: 0.22.0
// generator: pwb-native-gen 1
// This file is generated in memory and is not committed.

alignas(16) const unsigned char kImageBytes[] = {
    0x50, 0x57, 0x42, 0x31, 0x01, 0x00, 0x00, 0x00,
    0x05, 0x00, 0x30, 0x2e, 0x32, 0x32, 0x2e, 0x30,
    // one line per line_width bytes
};

constexpr std::size_t kImageSize = 24545u;
constexpr std::uint32_t kImageCrc32 = 0x1a2b3c4du;

static_assert(sizeof(kImageBytes) == kImageSize, "embedded image length mismatch");
static_assert(kImageCrc32 != 0u, "embedded image checksum must be set");

} // namespace pwb_generated
```

Rules.

1. `alignas(16)` gives the reader a stable alignment and keeps the array friendly to a future zero copy path.
2. `line_width` defaults to 16 bytes per line. The generator writes `0xNN, ` tokens and a newline at the boundary.
3. The size constant is decimal with a `u` suffix.
4. The CRC constant is eight hex digits with a `u` suffix.
5. The `static_assert` catches a truncated generator output at compile time.
6. `main` performs a runtime CRC check. The compile time assert cannot catch a corrupted hand edited file, and the runtime check also protects a future load from disk.
7. A CRC mismatch prints `powang: embedded image checksum mismatch` to stderr and returns exit code 3 in this design. The N0 implementation returns 1 for image and verifier errors.
8. A zero length image is rejected by the generator with `ValueError` before any source is produced.
9. The generator never embeds the source text of the program unless `emit_image_comment` is used. Comments are metadata only and do not affect execution.

The original design `main` function is:

```cpp
int main(int argc, char** argv) {
    if (!pwb::crc32_matches(
            pwb_generated::kImageBytes,
            pwb_generated::kImageSize,
            pwb_generated::kImageCrc32)) {
        std::fputs("powang: embedded image checksum mismatch\n", stderr);
        return 3;
    }
    return pwb::run_embedded(
        pwb_generated::kImageBytes,
        pwb_generated::kImageSize,
        argc,
        argv);
}
```

### 3.4 The `g++` invocation on Windows

The product path uses `subprocess.run` with an argv list. It never uses `shell=True` and it never pipes through PowerShell.

The verified toolchain is:

```text
g++.exe (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r4) 16.1.0
```

#### Building the static runtime library

One time per toolchain and runtime version:

```powershell
cmake -S native -B build/native -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_CXX_COMPILER=g++ `
  -DCMAKE_CXX_STANDARD=17 `
  -DCMAKE_CXX_STANDARD_REQUIRED=ON `
  -DCMAKE_CXX_EXTENSIONS=OFF
cmake --build build/native --target pwb_runtime
```

The equivalent direct commands, useful when CMake is unavailable:

```powershell
New-Item -ItemType Directory -Force build\native\obj | Out-Null
g++ -std=c++17 -O2 -DNDEBUG -fno-rtti -Wall -Wextra -Wpedantic `
  -I native\include -c native\src\image.cpp -o build\native\obj\image.o
g++ -std=c++17 -O2 -DNDEBUG -fno-rtti -Wall -Wextra -Wpedantic `
  -I native\include -c native\src\verifier.cpp -o build\native\obj\verifier.o
# repeat for every source
ar rcs build\native\libpwb_runtime.a build\native\obj\*.o
```

#### Compiling `temp.cpp` from a temporary file

This is the default integrated path. The generated source is written to a temporary `temp.cpp` file for compilation and diagnostics.

```powershell
g++ -std=c++17 -O2 -DNDEBUG -fno-rtti -Wall -Wextra -Wpedantic `
  build\native\temp.cpp `
  -o build\native\app.exe `
  -I native\include `
  -L build\native -lpwb_runtime `
  -static -static-libgcc -static-libstdc++ -pthread -s
```

#### Compiling `temp.cpp` from stdin

This path is available with `use_stdin=True`, but it is not the default. The generated source is written to the child process stdin as UTF-8 bytes.

```powershell
g++ -std=c++17 -O2 -DNDEBUG -fno-rtti -Wall -Wextra -Wpedantic `
  -x c++ - `
  -o build\native\app.exe `
  -I native\include `
  -L build\native -lpwb_runtime `
  -static -static-libgcc -static-libstdc++ -pthread -s
```

In Python the same command is:

```python
command = [
    gxx,
    "-std=c++17",
    "-O2",
    "-DNDEBUG",
    "-fno-rtti",
    "-Wall",
    "-Wextra",
    "-Wpedantic",
    "-x", "c++", "-",
    "-o", str(output),
    "-I", str(include_dir),
    "-L", str(runtime_dir), "-lpwb_runtime",
    "-static",
    "-static-libgcc",
    "-static-libstdc++",
    "-pthread",
    "-s",
]
completed = subprocess.run(
    command,
    input=source.encode("utf-8"),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=str(workdir),
    timeout=timeout,
    check=False,
)
```

Manual PowerShell proof of the stdin path requires UTF-8 output encoding. Windows PowerShell 5.1 defaults `$OutputEncoding` to ASCII, which corrupts non ASCII string literals.

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-Content -Raw -Encoding utf8 .\build\native\temp.cpp |
  & g++ -std=c++17 -O2 -DNDEBUG -fno-rtti -Wall -Wextra -Wpedantic `
    -x c++ - `
    -o .\build\native\app.exe `
    -I .\native\include `
    -L .\build\native -lpwb_runtime `
    -static -static-libgcc -static-libstdc++ -pthread -s
```

The product never relies on this manual form. It passes bytes directly.

#### Flag choices

| Flag | Reason |
|---|---|
| `-std=c++17` | Required language level |
| `-O2` | Default release optimization, good compile time and runtime balance |
| `-O0 -g3` | Debug builds, assertions on, no stripping |
| `-DNDEBUG` | Release builds disable `assert` |
| `-fno-rtti` | The VM does not use `dynamic_cast` or `typeid`. Reduces binary size |
| `-Wall -Wextra -Wpedantic` | Catch portability mistakes early |
| `-Wno-unused-parameter` | Only when the host interface has intentionally unused stubs |
| `-x c++ -` | Treat stdin as C++ source |
| `-I native\include` | Runtime headers |
| `-L build\native -lpwb_runtime` | Static runtime library |
| `-static` | No MinGW runtime DLL dependency |
| `-static-libgcc` | Explicit static GCC runtime |
| `-static-libstdc++` | Explicit static C++ runtime |
| `-pthread` | `std::thread` and `std::condition_variable` on the posix threads MinGW build |
| `-s` | Strip symbols in release. Never with `-g` |
| `-Wl,--gc-sections` | Optional in N6, only with `-ffunction-sections -fdata-sections` |

Do not use `-fno-exceptions`. The standard library and `new` need exceptions for allocation failure, and the toolchain driver reports failure through a normal process exit. Language errors do not use C++ exceptions, but the runtime still needs the language facility.

Do not use `-municode` or `-mwindows` in the first release. The generated `main` is a console program and must keep standard output and standard error.

#### Output naming

1. Default: `build/native/<module>.exe`.
2. `--native-output PATH` overrides it.
3. The `.exe` suffix is added on Windows when the override has no suffix.
4. The parent directory is created if missing.
5. A stale output is deleted before the compile. If deletion fails because the file is locked, the driver returns a clear `NativeBuildError` instead of letting `g++` fail with a confusing linker message.
6. A successful compile requires the output to exist, be a regular file and be larger than zero bytes.

### 3.5 The integrated compiler API

```python
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int
    column: int
    severity: str
    message: str


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    output: Path | None
    seconds: float
    diagnostics: tuple[Diagnostic, ...] = ()
    timed_out: bool = False
    output_size: int = 0
    cache_hit: bool = False


class NativeBuildError(Exception):
    def __init__(self, message: str, result: CompileResult) -> None:
        super().__init__(message)
        self.result = result


class IntegratedGcc:
    def __init__(
        self,
        executable: str = "g++",
        *,
        timeout: float = 120.0,
        max_output_bytes: int = 128 * 1024 * 1024,
        cwd: Path | None = None,
    ) -> None:
        self.executable = executable
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self.cwd = cwd

    def available(self) -> bool:
        """Return true when the compiler executable exists and answers --version."""

    def version(self) -> str:
        """Return the first line of g++ --version, cached for the process."""

    def compile(
        self,
        source: str,
        output: Path,
        flags: Sequence[str] = (),
        *,
        use_stdin: bool = False,
    ) -> CompileResult:
        """Compile source to output and capture diagnostics."""
```

#### Behavior

1. `available()` uses `shutil.which(self.executable)` and a cached `--version` probe with a short timeout. A missing compiler returns false and does not raise.
2. `version()` runs `g++ --version` once, strips the first line and caches it. The cache key uses this exact string.
3. `compile()` builds the argv list itself. It does not accept a raw shell string.
4. `flags` is filtered through a whitelist. Allowed entries are `-O0`, `-O1`, `-O2`, `-O3`, `-g`, `-g3`, `-DNDEBUG`, `-fno-omit-frame-pointer`, `-Wno-unused-parameter`, `-Werror` in tests only, and `-DPWB_*` names defined by the runtime. An unknown flag raises `ValueError` before spawning.
5. `use_stdin=True` is an option. It uses `-x c++ -` and passes `source.encode("utf-8")` as `input`.
6. `use_stdin=False` is the default. It writes a temporary `temp.cpp` under the sandbox directory for diagnostics, compiles it and deletes it in a `finally` block.
7. The child environment is a copy of `os.environ`, with `TMP` and `TEMP` pointed at the sandbox directory and `PWB_NATIVE=1`.
8. The output is deleted before the compile. The parent directory is created.
9. The compile is timed with `time.perf_counter()`.
10. On timeout, the driver kills the process tree. On Windows it calls `taskkill /T /F /PID <pid>` and waits. On other platforms it calls `killpg`.
11. `stdout` and `stderr` are decoded as UTF-8 with `errors="replace"` and truncated at 1 MiB of UTF-8 bytes each. The truncation appends a `... [truncated]` marker.
12. `ok` is true only when the return code is zero, the output exists and the output size is within `max_output_bytes`.
13. `diagnostics` is parsed from stderr with `^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s+(?P<sev>error|warning|note):\s+(?P<msg>.*)$`. `In file included from` and caret lines are kept in `stderr` but not turned into `Diagnostic` records.
14. The logical file name `<stdin>` is rewritten to `temp.cpp` in `Diagnostic.file`.
15. A non zero return code raises `NativeBuildError` only at the call site that chooses to raise. `compile()` itself returns the structured result. The CLI and `build_native()` raise with a formatted message.
16. `NativeBuildError` has `kind="COMPILE"`, `where="native build"`, a message `Native compilation failed`, and details containing the first error diagnostic and a count of the rest. The full `CompileResult` stays on the exception as `.result`.

#### Diagnostics as a language error

`powang vm native build` maps a failed compile to a `PowangError` with kind `COMPILE`, so the CLI exit code is 1, matching a frontend compile failure. `powang vm run --engine=native` does the same. `--json` prints the structured `CompileResult` instead of throwing, which is useful for tooling and tests.

An image or verifier failure is an internal error with exit code 3 in this design, because it means the Python compiler or the generator produced something invalid. The N0 implementation returns 1 for image, verifier and runtime errors and 0 on success. Exit code 3 remains a later design option.

### 3.6 Sandbox and safety limits

1. Sandbox root: `Path(tempfile.gettempdir()) / f"powang-native-{os.getpid()}-{secrets.token_hex(6)}"`. It is created with `mkdir(parents=True, exist_ok=False)`.
2. The sandbox is removed in a `finally` block with `shutil.rmtree(..., ignore_errors=True)`.
3. Output path: `Path.resolve()` must be inside the allowed build root or the sandbox. `Path.is_relative_to` is used on Python 3.12.
4. Path quoting: `subprocess` receives an argv list. The driver never concatenates a command string and never uses `shell=True`.
5. Timeout: default 120 seconds, maximum 300 seconds. `--native-timeout` sets it.
6. Source size: 64 MiB maximum before the compiler is invoked.
7. Captured stderr and stdout: 1 MiB of UTF-8 bytes each, with a `... [truncated]` marker.
8. Output size: 128 MiB default, configurable with `--native-max-output`.
9. Flags: whitelist only. User supplied `-I`, `-L` and `-l` are rejected outside the known runtime and build directories.
10. No network access is needed or used.
11. `TMP` and `TEMP` are redirected to the sandbox so `cc1plus` temporary files do not escape.
12. The generated `temp.cpp` is never written to the repository root. `--keep-source` writes `<output-stem>.cpp` next to the executable, for example `build/main.cpp` for `build/main.exe`. It does not write a file named `temp.cpp` and does not keep the temporary compiler input.
13. `.gitignore` gains `build/native/` and `.powang/cache/native/`.
14. A cleanup test runs `git status --porcelain` after a build and asserts that no generated source appears.
15. On interrupt, `KeyboardInterrupt` triggers the same cleanup and kills the child tree.

### 3.7 Caching the native build

The cache key is a SHA-256 over a canonical byte string.

```text
PWB-NATIVE-CACHE-1 \n
image_sha256_hex \n
gcc_version_line \n
sorted_flags_joined_by_space \n
PWB_RUNTIME_VERSION \n
PWB_GENERATOR_VERSION \n
target_triple \n
```

1. `image_sha256_hex` is the SHA-256 of `image.to_bytes()`.
2. `gcc_version_line` is `IntegratedGcc.version()`.
3. `sorted_flags_joined_by_space` makes `-O2 -g` and `-g -O2` the same key.
4. `PWB_RUNTIME_VERSION` is a constant in `native/include/pwb/version.hpp`.
5. `PWB_GENERATOR_VERSION` is a constant in `src/vm/native/sourcegen.py`.
6. `target_triple` is `platform.system()`, `platform.machine()` and the compiler target from `g++ -dumpmachine`.

The cache layout:

```text
<root>/
  <first two hex chars>/
    <digest>/
      app.exe
      meta.json
```

`meta.json` contains the key fields, the image CRC32, the output size, the creation time, `verified: true` and the runtime version.

1. Default root: `%LOCALAPPDATA%\powang\native-cache` on Windows, `$XDG_CACHE_HOME/powang/native` or `~/.cache/powang/native` elsewhere.
2. `--native-cache local` uses `.powang/cache/native`.
3. `--no-native-cache` disables both read and write.
4. `lookup` checks the executable exists, is non empty, and the metadata digest matches. A miss returns `None`.
5. `store` writes to a temporary file in the same directory and uses `os.replace` for atomic publication.
6. `clean` removes entries older than a cutoff and enforces a 512 MiB cap by least recent use.
7. A cache hit returns `CompileResult(ok=True, cache_hit=True, ...)` with the original metadata and a zero compile time.
8. A cache entry from a different compiler version is ignored, never reused.
9. A corrupted `meta.json` is ignored and the entry is deleted.

The cache is an optimization only. `--no-native-cache` must always produce the same executable behavior.

## 4. Milestones N0 to N6

Every milestone follows the same rules.

1. The Python VM remains the default engine until N6 passes the full differential suite.
2. The tree walker remains available with `--engine=tree`.
3. The Python VM remains the differential oracle.
4. A milestone is `gate green` only when its acceptance tests and verification commands pass.
5. A milestone never changes an existing test to make the native engine pass.

### 4.1 N0: image reader, decoder, verifier, generator and g++ driver

#### Scope

1. Read `PWB1` images.
2. Decode every opcode into an instruction array.
3. Verify the container, CRC32, table bounds, operand widths, opcode boundaries and a minimal stack dataflow.
4. Provide a text and JSON disassembler.
5. Generate the opcode, tag and operand header from `src/vm/opcodes.py`.
6. Render `temp.cpp` into an in-memory buffer.
7. Invoke `g++` from Python and capture diagnostics.
8. Run a trivial native program that prints a literal sum.

The implemented N0 native VM supports the scalar subset listed in the Implementation note. This includes the opcodes needed by `print(1 + 2)`. Every other opcode is decoded and verified but reports `unsupported opcode` at execution. An N0 runtime error uses exit code 1. `CHECK_CANCEL` is a no-op when the frame has no task, which is the case for every N0 program.

#### Exact files

This list is the original design target. The implemented file names are in the Implementation note at the top of this document.

Create:

1. `native/CMakeLists.txt`
2. `native/README.md`
3. `native/include/pwb/version.hpp`
4. `native/include/pwb/value.hpp`
5. `native/include/pwb/image.hpp`
6. `native/include/pwb/opcode_generated.hpp`
7. `native/include/pwb/verifier.hpp`
8. `native/include/pwb/disasm.hpp`
9. `native/include/pwb/vm.hpp`
10. `native/include/pwb/host.hpp`
11. `native/include/pwb/embed.hpp`
12. `native/include/pwb/crc32.hpp`
13. `native/include/pwb/result.hpp`
14. `native/src/crc32.cpp`
15. `native/src/image.cpp`
16. `native/src/verifier.cpp`
17. `native/src/disasm.cpp`
18. `native/src/vm.cpp`
19. `native/src/host.cpp`
20. `native/tools/pwb_probe.cpp`
21. `native/tests/test_main.cpp`
22. `native/tests/test_crc32.cpp`
23. `native/tests/test_image.cpp`
24. `native/tests/test_verifier.cpp`
25. `native/tests/test_vm_core.cpp`
26. `src/vm/native/__init__.py`
27. `src/vm/native/abi.py`
28. `src/vm/native/sourcegen.py`
29. `src/vm/native/gcc.py`
30. `src/vm/native/cache.py`
31. `src/vm/native/cli.py`
32. `tests/test_vm_native_abi.py`
33. `tests/test_vm_native_sourcegen.py`
34. `tests/test_vm_native_gcc.py`
35. `tests/test_vm_native_cache.py`
36. `tests/test_vm_native_smoke.py`
37. `tests/native/corpus/n0/print_add.po`

Modify:

1. `src/vm/cli.py` to dispatch `native` to `native_main`.
2. `powang.py` usage text to mention `powang vm native`.
3. `.gitignore` to ignore `build/native/` and `.powang/cache/native/`.

#### Key classes and functions

1. `pwb::Reader` with `take`, `u8`, `u16`, `u32`, `i32`, `i64`, `f64`, `string`, `remaining`.
2. `pwb::Image::from_bytes(const std::uint8_t* bytes, std::size_t size, const MetaBlock* meta)`, returning `Result<Image>`.
3. `pwb::CodeObject::decode_instructions()`.
4. `pwb::verify_image(const Image&, VerifyMode)`.
5. `pwb::disassemble_image(const Image&)` and `pwb::disassemble_image_json(const Image&)`, both returning `std::string`.
6. `pwb::VM::run()` with handlers for `LOAD_NOVA`, `STORE_LOCAL`, `CHECK_CANCEL`, `LOAD_INT`, `ADD`, `CALL` for the `print` builtin, `STORE_RAW`, `LOAD_LOCAL` and `RETURN`.
7. `pwb::Host::write_stdout`.
8. `src.vm.native.abi.render_cpp_header()` and `check_header()`.
9. `src.vm.native.sourcegen.TempCppOptions`, `render_temp_cpp`, `render_temp_cpp_buffer`, `render_temp_cpp_into`.
10. `src.vm.native.gcc.IntegratedGcc`, `CompileResult`, `Diagnostic`, `NativeBuildError`.
11. `src.vm.native.cli.native_main`.

#### The N0 gate image

`print(1 + 2)` compiles to this exact code object with the current compiler.

```text
code 0 probe locals 1 params 0 max_stack 10
    0 LOAD_NOVA
    1 STORE_LOCAL        slot 0
    4 CHECK_CANCEL
    5 LOAD_INT           value 1
   14 LOAD_INT           value 2
   23 ADD
   24 CALL               call 0
   29 STORE_RAW          slot 0
   32 LOAD_LOCAL         slot 0
   35 RETURN
```

The call site is:

```text
dispatch=call name=print positional_count=1 argument_kinds=(positional,) argument_names=('',)
```

There are no constants and no global names.

#### Acceptance tests

The implemented coverage lives in `tests/test_native_build.py` with 18 tests. It covers the generated opcode header, the in-memory buffer, the `print(1 + 2);` gate, byte-exact disassembly parity, corrupt image rejection, compiler diagnostics, temp cleanup, CLI run, CLI compile, native info, number semantics, print arity, loop image verification, bad jump rejection, missing compiler handling and stdin compilation. The number semantics test runs 36 subtests. The list below is the original design target.

1. `tests/test_vm_native_abi.py` regenerates the C++ header and asserts it equals the checked-in file. It also asserts the header contains every opcode name, every tag and the operand kind enum.
2. `tests/test_vm_native_sourcegen.py` asserts deterministic output, the `alignas` declaration, the length constant, the CRC constant, the `static_assert`, the `main` function, and that no file is written by the generator.
3. `tests/test_vm_native_gcc.py` asserts `available()`, `version()`, a successful compile, a failed compile with parsed diagnostics, a timeout, a path with spaces, and a missing compiler.
4. `tests/test_vm_native_cache.py` asserts a cache key changes with the image, the compiler version, the flags and the runtime version, that a hit returns the same output, that a corrupted entry is ignored and that `--no-native-cache` bypasses the cache.
5. `tests/test_vm_native_smoke.py` compiles the gate image through the integrated path, runs the executable, asserts stdout is exactly `3` with no trailing newline, asserts the exit code is `0`, and asserts `git status --porcelain` has no `temp.cpp`.
6. `native/tests/test_crc32.cpp` checks the standard vectors against Python `zlib.crc32`.
7. `native/tests/test_image.cpp` round trips `examples/arithmetics.po` through the Python image writer and the native reader.
8. `native/tests/test_verifier.cpp` rejects a truncated image, a bad CRC, an unknown opcode and a jump into the middle of an instruction.

#### Verification commands

The implemented N0 commands:

```powershell
.\.venv\Scripts\python.exe -m src.vm.native.gen_opcodes --check
cmake -S native -B build/native -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++
cmake --build build/native
.\.venv\Scripts\python.exe -m unittest tests.test_native_build -v
```

The gate can also be run from the CLI on a source file:

```powershell
'print(1 + 2);' | Set-Content -Encoding ascii build\native\gate.po
.\.venv\Scripts\python.exe powang.py vm native run build\native\gate.po
```

Expected output of the last command:

```text
3
```

The output is exactly `3` with no trailing newline and the exit code is `0`.

The original design also expected `ctest` and the placeholder test modules listed in the acceptance tests. The implemented coverage is `tests/test_native_build.py` with 18 tests, including the number semantics test with 36 subtests.

#### Atomic commit plan

1. `native: add the PWB1 reader, CRC32 and generated opcode header`
2. `native: add the image verifier and disassembler`
3. `native: add the N0 execution loop for the literal gate`
4. `python(native): add the temp.cpp source generator`
5. `python(native): add the integrated g++ driver and native CLI`
6. `python(native): add the native build cache`
7. `test(native): add the N0 gate, generator, compiler and cache tests`

#### Exit gate

`print(1 + 2)` compiles through the integrated path, writes exactly `3` with no trailing newline, exits `0`, and leaves no generated file in the repository. The native entry-code disassembly is byte-identical to the Python disassembler.

### 4.2 N1: scalars, locals, globals, arithmetic, control flow and calls

#### Scope

1. All scalar tags: nova, undef, bool, int, bigint, num and char.
2. Locals, globals, names and raw slots.
3. Arithmetic, comparison, logic and typed comparison.
4. `if`, `else`, `loop`, `for` range, `break` and `continue`.
5. Functions, closures, captures, calls, returns, default arguments, named arguments and variadics.
6. Frames, source spans, runtime error formatting and the frame list.
7. The instruction budget and the frame limit.

#### Exact files

Create:

1. `native/include/pwb/bigint.hpp`
2. `native/src/bigint.cpp`
3. `native/include/pwb/ops.hpp`
4. `native/src/ops.cpp`
5. `native/include/pwb/frame.hpp`
6. `native/src/frame.cpp`
7. `native/include/pwb/dispatch.hpp`
8. `native/src/dispatch.cpp`
9. `native/include/pwb/errors.hpp`
10. `native/src/errors.cpp`
11. `native/tests/test_bigint.cpp`
12. `native/tests/test_value.cpp`
13. `native/tests/test_frames.cpp`
14. `native/tests/test_dispatch.cpp`
15. `native/tests/test_vm_n1.cpp`
16. `src/vm/native/meta.py`
17. `src/vm/native/differential.py`
18. `tests/test_vm_native_meta.py`
19. `tests/test_vm_native_corpus.py`
20. `tests/native/corpus/n1/arithmetic.po`
21. `tests/native/corpus/n1/control_flow.po`
22. `tests/native/corpus/n1/functions.po`
23. `tests/native/corpus/n1/recursion.po`
24. `tests/native/corpus/n1/errors.po`

Modify:

1. `native/src/vm.cpp` to add the scalar and control flow handlers.
2. `native/src/disasm.cpp` for the new operand forms.
3. `native/src/image.cpp` to load the PWBM block.
4. `src/vm/native/sourcegen.py` to embed the PWBM block.

#### Key classes and functions

1. `pwb::BigInt` with `parse_decimal`, `format_decimal`, `compare`, `add`, `subtract`, `multiply`, `divide`, `remainder`, `negate`, `to_double`.
2. `pwb::ValueOps` with `truthy`, `equals`, `compare`, `binary_add`, `binary_sub`, `binary_mul`, `binary_div`, `binary_mod`, `negate`, `to_string`, `to_bool`, `copy`.
3. `pwb::Frame`, `pwb::FrameStack`, `pwb::HandlerEntry`.
4. `pwb::Dispatch::bind_parameters`, `resolve_named`, `call_identifier`, `call_value`, `call_builtin`.
5. `pwb::ErrorInfo`, `pwb::ErrorRef`, `pwb::format_error`, `pwb::format_frames`.
6. `pwb::VM::execute`, `pwb::VM::dispatch`, `pwb::VM::handle_error`.
7. `pwb::VM::run_code` and `pwb::VM::call_value`.
8. `src.vm.native.meta.build_meta(image)` and `validate_meta(image, meta)`.
9. `src.vm.native.differential.compare_native_file(path)`.

#### PWBM function metadata

N1 is the first milestone that needs parameter metadata. The `PWBM` block carries:

1. Function name, code index, min argc, variadic index and flags.
2. Parameter names in declaration order.
3. Parameter type spec IDs.
4. Reference and weak flags.
5. Default code indices.
6. The image SHA-256.

`src/vm/native/meta.py` must not parse AST itself. It reads `ProgramImage.functions`, `ProgramImage.type_specs` and `CodeObject.parameter_names`, converts type nodes with `src.typespec.from_ast_node` and serializes the result.

#### Type specs for N1

N1 needs the scalar subset.

1. Named types: `nova`, `bool`, `int`, `num`, `char`, `str`, `any`.
2. Union types.
3. Weak and reference flags.
4. `assignable`, `runtime_type_matches` and `explicit_cast` for the scalar subset.

The `CAST_ASSIGN`, `CAST_RETURN`, `BOX_ANY`, `UNBOX_ANY`, `TYPE_CHECK` and `TYPE_CHECK_NOT` handlers use these functions. A missing spec reports `unsupported: type spec <id>`.

#### Acceptance tests

1. `tests/test_vm_native_meta.py` builds the same image twice, asserts identical bytes, asserts the image hash and asserts that every function parameter is represented.
2. `tests/test_vm_native_corpus.py` runs every `.po` file under `tests/native/corpus/n1` on the Python VM, the tree walker and the native engine, and compares stdout, stderr and exit code.
3. `native/tests/test_bigint.cpp` covers `2` to the power `200`, `-2` to the power `63`, division sign rules and decimal round trips.
4. `native/tests/test_value.cpp` covers equality, hashing and truthiness for every scalar.
5. `native/tests/test_frames.cpp` covers slot initialization, `DUP`, `SWAP`, `ROT3`, `ROT`, handler push and pop, and frame generation.
6. `native/tests/test_dispatch.cpp` covers the overload scorer table generated from Python.
7. `native/tests/test_vm_n1.cpp` runs the gate image and a recursive function.

The existing core tests that must stay green on the Python VM and the tree walker:

1. `tests.test_vm_runtime.CoreExpressionTests`
2. `tests.test_vm_runtime.VariableAndControlTests`
3. `tests.test_vm_runtime.FunctionTests`
4. `tests.test_vm_errors.ErrorParityTests`

#### Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_native_meta tests.test_vm_native_corpus -v
.\.venv\Scripts\python.exe -m src.vm.native.differential --corpus tests\native\corpus\n1 --fail-fast
ctest --test-dir build/native --output-on-failure
.\.venv\Scripts\python.exe powang.py vm native diff tests\native\corpus\n1\recursion.po
```

#### Atomic commit plan

1. `native: add bigint, scalar operations and value equality`
2. `native: add frames, slots and the operand stack`
3. `native: add scalar, control flow and call dispatch`
4. `python(native): add the PWBM function and type metadata`
5. `test(native): add the N1 scalar and call corpus`

#### Exit gate

The N1 corpus reports zero mismatches against the Python VM. The tree walker agrees on every case. The error parity corpus produces identical text and positions.

### 4.3 N2: strings, containers, copy semantics, builtins and native methods

#### Scope

1. Strings as UTF-32 with a cached UTF-8 view.
2. Characters and Unicode validation.
3. Arrays, tuples, maps and sets.
4. Indexing, slicing and iteration.
5. Copy semantics and copy-on-write.
6. String interpolation with `CONCAT_STR` and `TO_STRING`.
7. The core builtins and all container and string native methods.

#### Exact files

Create:

1. `native/include/pwb/heap.hpp`
2. `native/include/pwb/object.hpp`
3. `native/src/heap.cpp`
4. `native/src/object.cpp`
5. `native/src/native_methods_arr.cpp`
6. `native/src/native_methods_str.cpp`
7. `native/src/native_methods_char.cpp`
8. `native/src/native_methods_map.cpp`
9. `native/src/native_methods_set.cpp`
10. `native/src/native_methods_tup.cpp`
11. `native/src/builtins_core.cpp`
12. `native/src/unicode_tables.cpp`
13. `native/tests/test_heap.cpp`
14. `native/tests/test_containers.cpp`
15. `native/tests/test_strings.cpp`
16. `native/tests/test_native_methods.cpp`
17. `src/vm/native/unicode.py`
18. `tests/test_vm_native_unicode.py`
19. `tests/native/corpus/n2/strings.po`
20. `tests/native/corpus/n2/containers.po`
21. `tests/native/corpus/n2/copy.po`
22. `tests/native/corpus/n2/slicing.po`
23. `tests/native/corpus/n2/interpolation.po`
24. `tests/native/corpus/n2/native_methods.po`

Modify:

1. `native/src/vm.cpp` for the container, string and builtin handlers.
2. `native/src/ops.cpp` for string and container operations.
3. `native/src/image.cpp` to decode string constants into `StringObject`.
4. `src/vm/native/meta.py` for the full type spec tree.

#### Key classes and functions

1. `pwb::Heap` with `allocate_string`, `allocate_array`, `allocate_tuple`, `allocate_map`, `allocate_set`, `allocate_object`, `retain`, `release`, `copy_value`, `ensure_unique`, `stats`.
2. `pwb::StringObject`, `pwb::ArrayObject`, `pwb::TupleObject`, `pwb::MapObject`, `pwb::SetObject`.
3. `pwb::IndexGet`, `pwb::IndexSet`, `pwb::Slice`, `pwb::Size`, `pwb::IterNew`, `pwb::IterNext`.
4. `pwb::TypeSpec` with `assignable`, `runtime_type_matches`, `explicit_cast`, `coerce_value_to_type`.
5. `pwb::Builtins::call(name, args)` for the N2 subset.
6. `pwb::NativeMethods::call(type, name, args)` for the N2 subset.
7. `src.vm.native.unicode.generate_tables()` and `verify_tables()`.

#### Builtin coverage at N2

The full builtin table has 29 names. N2 implements:

1. `print`
2. `println`
3. `printf`
4. `format`
5. `size`
6. `chr`
7. `ord`
8. `digit_value`
9. `is_alnum`
10. `is_alpha`
11. `is_ascii`
12. `is_digit`
13. `is_lower`
14. `is_space`
15. `is_upper`

The remaining names are assigned as follows. N3 adds `typeof` and `typedeep`. N4 adds `error` and `fail` for the dynamic call paths, even though the compiler lowers the normal `error(...)` and `fail(...)` forms to `MAKE_ERROR`. N5 adds `open`, `close`, `read`, `write`, `input`, `inputf`, `system`, `wait`, `cancel` and `task_status`. That covers all 29 names.

#### Native method coverage at N2

The full native method table has 60 names across eight types. N2 implements 53 of them.

| Type | Count | Methods |
|---|---|---|
| `arr` | 11 | add, clear, get, pop, popget, popval, push, put, reverse, set, size |
| `str` | 9 | add, chars, count, div, get, mul, reverse, size, sub |
| `char` | 9 | code, is_alnum, is_alpha, is_ascii, is_digit, is_lower, is_space, is_upper, to_str |
| `map` | 9 | clear, get, has, keys, merge, pop, popget, size, values |
| `set` | 10 | add, clear, difference, has, intersection, pop, popget, size, to_arr, union |
| `tup` | 5 | add, get, reverse, size, to_arr |

The remaining seven methods are `file` (4) and `task` (3), deferred to N5.

#### Unicode tables

The string and char methods must match Python's Unicode behavior. The plan does not hand write Unicode tables.

1. `src/vm/native/unicode.py` uses Python's `unicodedata` and the `str` methods on the running interpreter to generate compact range tables.
2. The tables cover `isalpha`, `isdigit`, `isspace`, `islower`, `isupper`, `isalnum`, `isascii`, `digit_value` and simple case mapping.
3. The generator records the Python Unicode version in the table header.
4. The C++ table is deterministic and checked in.
5. A test regenerates the tables and compares them byte for byte.
6. A native method that needs a table entry outside the generated ranges reports a clear internal error, which the corpus catches.

#### Copy corpus

The copy corpus is the most important N2 test. It covers:

1. Array of scalars.
2. Array of arrays.
3. Map of arrays.
4. Set of strings.
5. Tuple of arrays.
6. User object with nested containers, starting at N3.
7. A self referential container created through a reference or a function.
8. A repeated reference inside one copied value, which must stay shared inside the copy but separate from the original.
9. Nested mutation after copy.
10. Copy at parameter binding, return, declaration, assignment, field write and index write.

The native copy must produce the same printed output as the Python deep copy. CoW may be enabled only after this corpus is green with deep copy.

#### Acceptance tests

1. `tests/test_vm_native_corpus.py` with `tests/native/corpus/n2` reports zero mismatches.
2. `tests/test_vm_native_unicode.py` regenerates tables.
3. `native/tests/test_heap.cpp` covers retain and release counts, CoW detach and copy with a cycle memo.
4. `native/tests/test_containers.cpp` covers insertion ordered maps and sets, negative indexes and slicing.
5. `native/tests/test_strings.cpp` covers non ASCII indexing, slicing, iteration and length.
6. `native/tests/test_native_methods.cpp` asserts every N2 method name is present and that the unsupported set is exactly `file` and `task`.

Existing tests that must stay green:

1. `tests.test_copy_semantics`
2. `tests.test_slicing`
3. `tests.test_native_methods`
4. `tests.test_characters`
5. `tests.test_vm_runtime.ContainerTests`

#### Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_native_unicode tests.test_vm_native_corpus -v
.\.venv\Scripts\python.exe -m src.vm.native.differential --corpus tests\native\corpus\n2 --fail-fast
ctest --test-dir build/native --output-on-failure
.\.venv\Scripts\python.exe powang.py vm native diff tests\native\corpus\n2\copy.po
```

#### Atomic commit plan

1. `native: add the heap, strings and copy semantics`
2. `native: add arrays, tuples, maps and sets`
3. `native: add indexing, slicing and iteration`
4. `native: add the N2 builtins and container native methods`
5. `python(native): generate Unicode tables from the Python runtime`
6. `test(native): add the N2 container, string and copy corpus`

#### Exit gate

The container, string and copy corpus reports zero mismatches. The CoW optimization is either off and green, or on and green against the same corpus.

### 4.4 N3: user types, enums, traits, operator dispatch and locks

#### Scope

1. Type declarations and constructors.
2. Fields, field access and access control.
3. Instance methods, static methods and copy constructors.
4. Enums and enum variants.
5. Traits, default methods and trait qualified calls.
6. Operator overloading and comparison dispatch.
7. Const and element locks.

#### Exact files

Create:

1. `native/src/types.cpp`
2. `native/src/traits.cpp`
3. `native/src/locks.cpp`
4. `native/tests/test_types.cpp`
5. `native/tests/test_traits.cpp`
6. `native/tests/test_operators.cpp`
7. `tests/native/corpus/n3/types.po`
8. `tests/native/corpus/n3/constructors.po`
9. `tests/native/corpus/n3/enums.po`
10. `tests/native/corpus/n3/traits.po`
11. `tests/native/corpus/n3/operators.po`
12. `tests/native/corpus/n3/locks.po`

Modify:

1. `native/src/dispatch.cpp` for method, static, trait and operator calls.
2. `native/src/ops.cpp` for operator trait dispatch.
3. `native/src/heap.cpp` for object allocation and object copy.
4. `native/src/vm.cpp` for `CONSTRUCT`, `NEW_ENUM`, `LOAD_FIELD`, `STORE_FIELD`, `LOAD_MEMBER`, `STORE_MEMBER`, `LOAD_MEMBER_SAFE`, `LOAD_ENUM_MEMBER`, `SET_LOCKS`, `CHECK_TRAIT` and `TRAIT_CAST`.

#### Key classes and functions

1. `pwb::TypeInfo`, `pwb::TraitInfo`, `pwb::FieldInfo`, `pwb::MethodTable`.
2. `pwb::construct(type_id, call_site, args)`.
3. `pwb::load_field`, `pwb::store_field`, `pwb::load_member`, `pwb::store_member`, `pwb::load_member_safe`.
4. `pwb::resolve_instance_method`, `pwb::call_static`, `pwb::call_trait`, `pwb::call_operator`.
5. `pwb::object_satisfies_trait`, `pwb::find_default_trait_method`.
6. `pwb::copy_object` with the identity memo.
7. `pwb::check_locks` and `pwb::set_locks`.

#### Operator dispatch order

The order from the design document is binding.

1. If the left operand is a user object, look up the matching operator trait method on the left type.
2. If the left type has a trait qualified method for the operator trait, use it.
3. If the left operand has no suitable method and the right operand is a user object, try the right operand with the existing right operand rule.
4. If no overload exists, apply built in semantics.
5. If no built in semantics exists, raise the same unsupported operation error as the tree walker.

The `Compare` trait returns an integer. The comparison opcode converts it to a boolean with the same rules as the tree walker.

#### Acceptance tests

1. The N3 corpus reports zero mismatches.
2. `native/tests/test_types.cpp` covers constructor binding, field order, private access and object copy.
3. `native/tests/test_traits.cpp` covers required methods, default methods, trait qualified dispatch and ambiguity errors.
4. `native/tests/test_operators.cpp` covers every arithmetic, comparison and unary operator on user types.
5. The overload scorer parity table includes user types and trait qualified candidates.

Existing tests that must stay green:

1. `tests.test_type_construction`
2. `tests.test_access_control`
3. `tests.test_enums`
4. `tests.test_traits`
5. `tests.test_operator_overloading`
6. `tests.test_vm_runtime.TypeAndTraitTests`

#### Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_native_corpus -v
.\.venv\Scripts\python.exe -m src.vm.native.differential --corpus tests\native\corpus\n3 --fail-fast
ctest --test-dir build/native --output-on-failure
.\.venv\Scripts\python.exe powang.py vm native diff tests\native\corpus\n3\operators.po
```

#### Atomic commit plan

1. `native: add type construction, fields and object copy`
2. `native: add instance and static method dispatch`
3. `native: add enums and enum member access`
4. `native: add traits and trait qualified calls`
5. `native: add operator dispatch and locks`
6. `test(native): add the N3 type, trait and operator corpus`

#### Exit gate

The type, trait and operator corpus reports zero mismatches. Error text for access control, ambiguity and locks matches the Python VM.

### 4.5 N4: modules, imports, project, externs, errors, references

#### Scope

1. Module initialization and the module cache.
2. Imports, wildcard imports, exports and aliases.
3. Project values and build time project snapshots.
4. Package aware module identities.
5. Externs through the host ABI.
6. Error values, `try`, `catch`, `finally`, rethrow and propagation.
7. References, reference parameters and reference pipelines.

#### Exact files

Create:

1. `native/include/pwb/module.hpp`
2. `native/src/modules.cpp`
3. `native/src/references.cpp`
4. `native/src/externs.cpp`
5. `native/tests/test_modules.cpp`
6. `native/tests/test_errors.cpp`
7. `native/tests/test_references.cpp`
8. `src/vm/native/pack.py`
9. `tests/test_vm_native_pack.py`
10. `tests/native/corpus/n4/modules.po`
11. `tests/native/corpus/n4/imports.po`
12. `tests/native/corpus/n4/project.po`
13. `tests/native/corpus/n4/errors.po`
14. `tests/native/corpus/n4/finally.po`
15. `tests/native/corpus/n4/references.po`
16. `tests/native/corpus/n4/propagation.po`

Modify:

1. `native/src/vm.cpp` for the error and module handlers.
2. `native/src/dispatch.cpp` for extern calls.
3. `native/src/image.cpp` to load the module manifest.
4. `src/vm/native/sourcegen.py` to embed the manifest and project snapshot.
5. `src/vm/cli.py` and `src/vm/native/cli.py` for module build options.

#### Key classes and functions

1. `pwb::ModuleRuntime`, `pwb::ModuleTable`, `pwb::ModuleRequest`, `pwb::ModuleManifest`.
2. `pwb::initialize_module`, `pwb::load_module_member`, `pwb::import_module`, `pwb::import_wildcard`.
3. `pwb::ProjectSnapshot`, `pwb::ProjectObject`.
4. `pwb::ExternTable`, `pwb::call_extern`.
5. `pwb::throw_error`, `pwb::handle_error`, `pwb::finally_end`, `pwb::propagate`, `pwb::rethrow`.
6. `pwb::ReferenceObject`, `pwb::ref_local`, `pwb::ref_global`, `pwb::ref_field`, `pwb::ref_index`, `pwb::load_ref`, `pwb::store_ref`.
7. `src.vm.native.pack.collect_module_graph`, `render_manifest`, `render_project_snapshot`.

#### Module build behavior

`src/vm/native/pack.py` uses the existing Python module loader, not a new resolver.

1. Resolve the entry module.
2. Walk imports recursively.
3. Compile each module to a `ProgramImage`.
4. Serialize each image.
5. Build a manifest with module name, resolved path, SHA-256, exports and imports.
6. Embed the entry image and the manifest in `temp.cpp`.
7. Either embed all module images or write them to `build/native/modules/`.
8. Refuse a module graph with a cycle at build time with the same `MODULE` error kind the runtime would produce.
9. A module whose resolved path changes between builds gets a new manifest entry and a new cache key.

#### Error corpus

The error corpus compares:

1. Standard output.
2. Standard error.
3. Exit code.
4. The exact error text, including `ln: N | ` and the `[KIND ERROR]` header.
5. The frame list, including `at <name> (<file>:<line>:<column>)`.
6. The order of finally blocks.
7. The cause chain when a finally block throws.

Cases:

1. `throw` of a user error.
2. `error(...)` and `fail(...)`.
3. `try` and `catch` with a binding.
4. `try`, `catch` and `finally`.
5. Nested `finally`.
6. A `finally` that throws.
7. Postfix `?` propagation inside a function.
8. Postfix `?` inside a `try` with a `finally`.
9. A task error awaited in a `try`.
10. Reference escape.
11. Reference to a constant.
12. Reference type mismatch.

#### Acceptance tests

1. The N4 corpus reports zero mismatches.
2. `tests/test_vm_native_pack.py` builds a two module program, asserts the manifest hashes and asserts a deterministic rebuild.
3. `native/tests/test_modules.cpp` covers depth first initialization, cycles, aliases and wildcard imports.
4. `native/tests/test_errors.cpp` covers every case in the error corpus and compares against golden text generated by the Python VM.
5. `native/tests/test_references.cpp` covers local, global, field and index references, plus stale frame rejection.

Existing tests that must stay green:

1. `tests.test_cross_module`
2. `tests.test_module_resolution`
3. `tests.test_packages`
4. `tests.test_project`
5. `tests.test_errors`
6. `tests.test_references`
7. `tests.test_vm_errors.ErrorParityTests`
8. `tests.test_vm_runtime.ErrorTests`
9. `tests.test_vm_runtime.ReferenceTests`
10. `tests.test_vm_runtime.ExceptionEdgeTests`

#### Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_native_pack tests.test_vm_native_corpus -v
.\.venv\Scripts\python.exe -m src.vm.native.differential --corpus tests\native\corpus\n4 --fail-fast
.\.venv\Scripts\python.exe -m src.vm.differential --examples examples --fail-fast
ctest --test-dir build/native --output-on-failure
```

#### Atomic commit plan

1. `native: add module runtimes and the module cache`
2. `native: add imports, exports and project values`
3. `python(native): add the module manifest and project snapshot`
4. `native: add error values, try, catch, finally and propagation`
5. `native: add references and reference lifetimes`
6. `native: add the extern host table`
7. `test(native): add the N4 module and error corpus`

#### Exit gate

The module and error corpus reports zero mismatches. Every error snapshot is byte identical to the Python VM. References pass their lifetime tests.

### 4.6 N5: async, tasks, worker pool, file I/O and the host bridge

#### Scope

1. Lazy tasks and worker tasks.
2. The worker pool, cancellation, wait, status and cleanup.
3. File builtins and file native methods.
4. Task builtins and task native methods.
5. The host bridge for `input`, `system` and clocks.
6. Deterministic test hooks for the async corpus.

#### Exact files

Create:

1. `native/include/pwb/task.hpp`
2. `native/src/tasks.cpp`
3. `native/src/task_pool.cpp`
4. `native/src/native_methods_file.cpp`
5. `native/src/native_methods_task.cpp`
6. `native/src/host_io.cpp`
7. `native/tests/test_tasks.cpp`
8. `native/tests/test_async.cpp`
9. `native/tests/test_files.cpp`
10. `tests/native/corpus/n5/lazy_tasks.po`
11. `tests/native/corpus/n5/worker_tasks.po`
12. `tests/native/corpus/n5/cancel.po`
13. `tests/native/corpus/n5/task_errors.po`
14. `tests/native/corpus/n5/files.po`
15. `tests/native/corpus/n5/cleanup.po`

Modify:

1. `native/src/vm.cpp` for `CALL_ASYNC`, `CALL_ASYNC_METHOD`, `SPAWN`, `AWAIT` and `CHECK_CANCEL`.
2. `native/src/dispatch.cpp` for the async call forms.
3. `native/src/host.cpp` for file, system, clock and input.
4. `native/src/builtins_core.cpp` for `open`, `close`, `read`, `write`, `input`, `inputf`, `system`, `wait`, `cancel` and `task_status`.

#### Key classes and functions

1. `pwb::Task`, `pwb::TaskPool`, `pwb::TaskHandle`.
2. `pwb::create_lazy_function_task`, `pwb::create_lazy_method_task`, `pwb::create_lazy_static_task`, `pwb::create_lazy_site_task`.
3. `pwb::create_worker_site_task`, `pwb::await_task`, `pwb::wait_task`, `pwb::cancel_task`, `pwb::task_status`.
4. `pwb::run_lazy_task`, `pwb::check_cancellation`.
5. `pwb::shutdown_tasks`.
6. `pwb::FileHandle`, `pwb::open_file`, `pwb::read_file`, `pwb::write_file`, `pwb::close_file`.
7. `pwb::DefaultHost` with stdout, stderr, stdin, files and clock.

#### Task semantics

1. A lazy task does not run until awaited. It runs on the awaiting thread.
2. A worker task starts on a pool thread.
3. A task that completes stores its result. A task that fails stores its error.
4. A cancelled task stores a `TASK` cancellation error.
5. `AWAIT` rethrows the stored error in the awaiting frame and appends the task frames.
6. `wait` with a timeout returns the Python behavior for a timeout.
7. `task_status` returns the same status strings as Python.
8. Cleanup joins every worker and releases every task.
9. The default pool size is four workers, or the hardware concurrency when it is lower. `PWB_TASK_WORKERS=1` forces deterministic single worker mode for tests.
10. A worker never throws across the thread boundary.

#### File semantics

1. `open`, `read`, `write` and `close` match the Python file behavior, including mode strings, encoding and error text.
2. A file is a `handle` value with identity semantics. It is not copied.
3. A closed file reports the same error as Python.
4. Paths are resolved by the host relative to the process working directory, matching the Python behavior.
5. File creation and modification side effects are part of the differential comparison.

#### Acceptance tests

1. The N5 corpus reports zero mismatches.
2. `native/tests/test_tasks.cpp` covers state transitions, cancellation and repeated shutdown.
3. `native/tests/test_async.cpp` covers lazy execution order, worker execution and awaited errors.
4. `native/tests/test_files.cpp` covers open, read, write, close, missing file and permission error.
5. A stress test starts and shuts down the VM 100 times and asserts no leaked tasks or threads.

Existing tests that must stay green:

1. `tests.test_async`
2. `tests.test_tasks`
3. `tests.test_vm_runtime.AsyncTests`
4. `tests.test_vm_stress`

#### Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_native_corpus -v
.\.venv\Scripts\python.exe -m src.vm.native.differential --corpus tests\native\corpus\n5 --fail-fast
ctest --test-dir build/native --output-on-failure
$env:PWB_TASK_WORKERS = "1"
.\.venv\Scripts\python.exe powang.py vm native diff tests\native\corpus\n5\worker_tasks.po
Remove-Item Env:\PWB_TASK_WORKERS
```

#### Atomic commit plan

1. `native: add the task object and the worker pool`
2. `native: add lazy and worker task creation`
3. `native: add await, wait, cancel and status`
4. `native: add file and task builtins and native methods`
5. `native: add the default host bridge`
6. `test(native): add the N5 async and file corpus`

#### Exit gate

The async corpus reports zero mismatches with one worker. The stress test passes. Every task is joined and every file is closed at shutdown.

### 4.7 N6: full parity, performance, default option and distribution

#### Scope

1. Full differential suite, examples, error snapshots and fuzz seeds.
2. Performance work: threaded dispatch, inline caches, allocation tuning and startup.
3. `--engine=native` integration and the default engine decision.
4. Distribution: static runtime library, single file mode, cache cleanup and documentation.
5. The final native contract document update.

#### Exact files

Create:

1. `native/src/inline_cache.cpp`
2. `native/src/dispatch_threaded.cpp`
3. `native/benches/*.po`
4. `src/vm/native/bench.py`
5. `tests/test_vm_native_parity.py`
6. `tests/test_vm_native_bench.py`
7. `docs/phase-4b-bytecode-vm/implementation/N6-native-parity-report.md`

Modify:

1. `native/src/vm.cpp` for the optional threaded dispatch.
2. `native/src/dispatch.cpp` for inline caches.
3. `native/src/heap.cpp` for size class allocation and the release list.
4. `src/vm/native/cli.py` for `bench`, `clean` and `pack`.
5. `powang.py` and `src/vm/cli.py` for `--engine=native`.
6. `CHANGELOG.md`, `pyproject.toml` and `README.md` for the release.
7. `docs/phase-4b-bytecode-vm/implementation/STATUS.md` for the N milestones.
8. `docs/phase-4b-bytecode-vm/implementation/V10-native-vm-contract.md` with the implemented contract.

#### Key classes and functions

1. `pwb::InlineCache` with call site, field, method and overload entries.
2. `pwb::dispatch_threaded` behind `PWB_THREADED_DISPATCH`.
3. `pwb::Heap::SizeClassAllocator`.
4. `pwb::VMSession` with a reusable heap and module table.
5. `src.vm.native.bench.run_native_benchmarks`.
6. `src.vm.native.cli.native_bench`, `native_clean`, `native_pack`.

#### Parity gates

1. The full Python VM suite passes.
2. The full tree walker suite passes with `POWANG_ENGINE=tree`.
3. The native corpus passes with zero mismatches.
4. Every example passes with zero mismatches.
5. Every error snapshot is byte identical.
6. The seeded fuzzer passes 1000 programs on seed 7 and 1000 on seed 2026.
7. The stress corpus passes.
8. The LSP is unchanged.
9. The native benchmark meets the target.

#### Performance gates

1. Native is at least three times faster than the tree walker on the CPU bound corpus.
2. Native startup is within 1.2 times the tree walker.
3. A warm integrated compile of a 50 KB image is under five seconds.
4. A cold integrated compile of a 50 KB image is under ten seconds.
5. Peak memory is within two times the Python VM on the corpus.

Performance claims require three runs on a stable machine profile and are recorded in `N6-native-parity-report.md`.

#### Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
$env:POWANG_ENGINE = "tree"
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe -m src.vm.differential --examples examples --fail-fast
.\.venv\Scripts\python.exe -m src.vm.differential --fuzz --seed 2026 --count 1000 --fail-fast
.\.venv\Scripts\python.exe -m src.vm.native.differential --corpus tests\native\corpus --fail-fast
.\.venv\Scripts\python.exe powang.py vm native bench --runs 3 --json
.\.venv\Scripts\python.exe powang.py vm disasm examples\modern.po
```

#### Atomic commit plan

1. `native: add inline caches and optional threaded dispatch`
2. `native: tune allocation, startup and the release list`
3. `python(native): add the native benchmark runner`
4. `vm: add --engine=native and the engine documentation`
5. `docs(phase-4b): record the native parity report`
6. `release: 0.25.0`

#### Exit gate

The full differential suite is green, the benchmark targets are met, and the release decision for the default engine is recorded.

### 4.8 Milestone summary

| Milestone | Scope | Gate | Status |
|---|---|---|---|
| N0 | Image reader, decoder, verifier, disassembler, generator, g++ driver | `print(1 + 2)` writes exactly `3` with no trailing newline through the integrated path | gate green |
| N1 | Scalars, locals, globals, control flow, functions, frames, errors | N1 core differential corpus, zero mismatches | not started |
| N2 | Strings, containers, copy semantics, builtins, native methods | N2 container corpus, zero mismatches | not started |
| N3 | User types, enums, traits, operator dispatch, locks | N3 type corpus, zero mismatches | not started |
| N4 | Modules, project, packages, externs, errors, references | N4 module and error corpus, zero mismatches | not started |
| N5 | Async, tasks, worker pool, file I/O, host bridge | N5 async corpus, zero mismatches | not started |
| N6 | Full parity, performance, default option, distribution | Full differential suite and benchmark target | not started |

The status column starts at `not started`, moves to `in progress` while a milestone is being implemented, and becomes `gate green` only when the gate command is recorded. N0 is `gate green`. N1 to N6 are `not started`.

## 5. Interfaces and data structures

The sketches below are binding for names, ownership and call direction. They are not full implementations. They are written so the first commit can copy the declarations and fill in the bodies milestone by milestone.

### 5.1 `native/include/pwb/value.hpp`

```cpp
#pragma once

#include <cstddef>
#include <cstdint>

namespace pwb {

enum class Tag : std::uint8_t {
    Nova = 0,
    Undef,
    Bool,
    Int,
    Num,
    Char,
    Str,
    Arr,
    Tup,
    Map,
    Set,
    Fun,
    Obj,
    Module,
    Task,
    Error,
    Ref,
    Handle,
    Project,
    Any,
};

enum ValueFlags : std::uint8_t {
    FlagNone = 0,
    FlagDefined = 1u << 0,
    FlagWeak = 1u << 1,
    FlagConst = 1u << 2,
    FlagBig = 1u << 3,
    FlagShared = 1u << 4,
    FlagLockedStructure = 1u << 5,
    FlagLockedElements = 1u << 6,
};

struct HeapObject;
struct StringObject;
struct ArrayObject;
struct TupleObject;
struct MapObject;
struct SetObject;
struct FunctionObject;
struct ObjectObject;
struct ModuleRuntime;
struct Task;
struct ErrorInfo;
struct ReferenceObject;
struct ProjectObject;
struct AnyObject;

struct Value {
    std::uint64_t payload;
    Tag tag;
    std::uint8_t flags;
    std::uint16_t aux;
    std::uint32_t reserved;

    Value() : payload(0), tag(Tag::Nova), flags(FlagDefined), aux(0), reserved(0) {}
    Value(Tag tag, std::uint64_t payload, std::uint8_t flags)
        : payload(payload), tag(tag), flags(flags), aux(0), reserved(0) {}

    static Value nova();
    static Value undef();
    static Value boolean(bool value);
    static Value integer(std::int64_t value);
    static Value big_integer(HeapObject* value);
    static Value number(double value);
    static Value character(char32_t value);
    static Value heap(Tag tag, HeapObject* object);
    static Value error(ErrorInfo* info);
    static Value reference(ReferenceObject* reference);

    bool is_nova() const;
    bool is_undef() const;
    bool is_defined() const;
    bool is_weak() const;
    bool is_heap() const;
    bool is_numeric() const;
    bool big() const;

    std::int64_t as_integer() const;
    double as_number() const;
    char32_t as_character() const;
    bool as_boolean() const;
    HeapObject* as_heap() const;
    StringObject* as_string() const;
    ArrayObject* as_array() const;
    TupleObject* as_tuple() const;
    MapObject* as_map() const;
    SetObject* as_set() const;
    FunctionObject* as_function() const;
    ObjectObject* as_object() const;
    ModuleRuntime* as_module() const;
    Task* as_task() const;
    ErrorInfo* as_error() const;
    ReferenceObject* as_reference() const;
    AnyObject* as_any() const;
};

static_assert(sizeof(Value) == 16, "Value must stay 16 bytes");
static_assert(alignof(Value) == 8, "Value must stay 8 byte aligned");

} // namespace pwb
```

### 5.2 `native/include/pwb/heap.hpp`

```cpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include "pwb/value.hpp"

namespace pwb {

struct HeapStats {
    std::uint64_t allocations;
    std::uint64_t frees;
    std::uint64_t live_objects;
    std::uint64_t live_bytes;
    std::uint64_t peak_bytes;
};

class Heap {
public:
    enum class Policy {
        Arena,      // N0 and N1, no frees until teardown
        RefCount,   // N2 onward
    };

    explicit Heap(Policy policy = Policy::RefCount,
                  std::size_t arena_size = 4u * 1024u * 1024u);
    ~Heap();

    Heap(const Heap&) = delete;
    Heap& operator=(const Heap&) = delete;

    Value allocate_string(std::u32string_view code_points);
    Value allocate_string_utf8(std::string_view utf8);
    Value allocate_array(std::vector<Value> items);
    Value allocate_tuple(std::vector<Value> items);
    Value allocate_map();
    Value allocate_set();
    Value allocate_function(const CodeObject* code, const FunctionMeta* meta);
    Value allocate_object(const TypeInfo* type, std::size_t field_count);
    Value allocate_error(ErrorInfo* info);
    Value allocate_reference(ReferenceObject* reference);
    Value allocate_any(Value concrete, std::uint32_t declared_spec);
    Value allocate_handle(void* payload, std::uint32_t kind);
    Value allocate_project(const ProjectSnapshot* snapshot);

    void retain(Value value);
    void release(Value value);

    Value copy_value(Value value);
    void ensure_unique(Value& value);

    bool unique(const Value& value) const;
    HeapStats stats() const;
    void collect_release_list();

private:
    struct Impl;
    Impl* impl_;
};

} // namespace pwb
```

### 5.3 `native/include/pwb/frame.hpp`

```cpp
#pragma once

#include <cstdint>
#include <vector>

#include "pwb/image.hpp"
#include "pwb/value.hpp"

namespace pwb {

struct ErrorInfo;
struct ModuleRuntime;
struct Task;
struct FunctionObject;

struct HandlerEntry {
    std::int32_t start_ip = 0;
    std::int32_t end_ip = 0;
    std::int32_t catch_ip = -1;
    std::int32_t finally_ip = -1;
    std::int32_t resume_ip = -1;
    std::uint32_t stack_depth = 0;
    std::uint32_t local_watermark = 0;
    std::uint32_t scope_depth = 0;
    std::uint8_t kind = 0;        // 0 catch, 1 finally
    std::uint8_t state = 0;       // 0 active, 1 catch, 2 finally
    Value pending_return;
    ErrorInfo* pending_error = nullptr;
};

struct Transfer {
    enum class Kind : std::uint8_t { None, Jump, Return };
    Kind kind = Kind::None;
    std::int32_t target = -1;
};

struct Frame {
    const CodeObject* code = nullptr;
    Value* locals = nullptr;
    std::uint32_t local_count = 0;
    Value* stack = nullptr;
    std::uint32_t sp = 0;
    std::uint32_t max_stack = 0;
    std::uint32_t ip = 0;
    std::uint32_t span_index = 0;
    Value receiver;
    FunctionObject* closure = nullptr;
    ModuleRuntime* module = nullptr;
    Task* task = nullptr;
    std::vector<HandlerEntry> handlers;
    Value pending_return;
    ErrorInfo* pending_error = nullptr;
    Transfer transfer;
    std::uint32_t scope_depth = 0;
    std::uint64_t generation = 0;
    bool is_function = false;

    void push(Value value);
    Value pop();
    Value& peek();
    void require_stack(std::uint32_t count, const char* opcode) const;
    void reset_stack(std::uint32_t depth);
};

class FrameStack {
public:
    Frame& push(const CodeObject* code, std::uint32_t local_count,
                std::uint32_t max_stack);
    void pop();
    Frame& top();
    const Frame& top() const;
    std::size_t depth() const;
    void set_limit(std::uint32_t limit);
    std::uint64_t next_generation();

private:
    std::vector<Frame> frames_;
    std::vector<Value> slots_;
    std::size_t slot_top_ = 0;
    std::uint32_t limit_ = 900;
    std::uint64_t generation_ = 0;
};

} // namespace pwb
```

### 5.4 `native/include/pwb/image.hpp`

The sketches below assume `Result<T>` and `Status` from `pwb/result.hpp`, and `MetaBlock`, `PatternDescriptor` and `TypeSpec` from `pwb/meta.hpp`. Those headers are small and have no dependency on the VM.

```cpp
#pragma once

#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <unordered_map>
#include <vector>

#include "pwb/value.hpp"

namespace pwb {

struct SourceSpan {
    std::uint32_t file_id = 0;
    std::uint32_t start_line = 0;
    std::uint32_t start_column = 0;
    std::uint32_t end_line = 0;
    std::uint32_t end_column = 0;
};

struct ExceptionEntry {
    std::int32_t start_ip = 0;
    std::int32_t end_ip = 0;
    std::int32_t catch_ip = -1;
    std::int32_t finally_ip = -1;
    std::int32_t resume_ip = -1;
    std::uint32_t stack_depth = 0;
    std::uint32_t local_watermark = 0;
    std::uint8_t kind = 0;
};

enum class ConstantKind : std::uint8_t {
    Nova, Bool, Int, BigInt, Num, Str, Char, Ast, Call, Pattern, Spec,
    Type, Trait, Function, Extern, Descriptor, Tuple,
};

struct Constant {
    ConstantKind kind;
    std::uint8_t flags = 0;
    std::int64_t int_value = 0;
    double num_value = 0.0;
    char32_t char_value = 0;
    std::string text;                 // str, bigint, ast, spec, descriptor, extern
    std::uint32_t index = 0;          // call, pattern, type, trait, function
    std::vector<Constant> tuple_items;
};

struct Instruction {
    std::uint8_t opcode = 0;
    std::uint8_t operand_count = 0;
    std::uint16_t span_index = 0;
    std::uint32_t offset = 0;
    std::uint32_t next_offset = 0;
    std::uint64_t operands[2] = {0, 0};

    std::int32_t operand_i32(std::size_t index) const;
    std::uint32_t operand_u32(std::size_t index) const;
    std::uint16_t operand_u16(std::size_t index) const;
    std::uint8_t operand_u8(std::size_t index) const;
    std::int64_t operand_i64(std::size_t index) const;
    double operand_f64(std::size_t index) const;
};

struct CodeObject {
    std::string name;
    std::string qualname;
    std::uint32_t source_file = 0;
    std::uint32_t parameter_count = 0;
    std::uint32_t local_count = 0;
    std::uint32_t capture_count = 0;
    std::uint32_t max_stack = 0;
    std::uint32_t max_frame_depth = 1;
    std::vector<std::uint8_t> bytecode;
    std::vector<std::uint32_t> constant_indices;
    std::vector<Constant> constants;
    std::vector<SourceSpan> spans;
    std::vector<std::uint32_t> span_table;
    std::vector<ExceptionEntry> exception_table;
    std::vector<std::string> local_names;
    std::vector<std::string> parameter_names;
    std::int32_t return_spec = -1;
    std::uint32_t flags = 0;
    std::optional<std::string> trait_name;
    std::optional<std::string> operator_trait;

    std::vector<Instruction> instructions;
    std::unordered_map<std::uint32_t, std::uint32_t> offset_to_index;
    std::unordered_map<std::uint32_t, std::uint32_t> try_start_to_entry;

    bool is_async() const;
    bool is_variadic() const;
    bool is_method() const;
    bool is_static() const;
    const Instruction* instruction_at(std::uint32_t offset) const;
};

struct CallSite {
    std::string dispatch;
    std::string name;
    std::optional<std::string> module;
    std::optional<std::string> type_name;
    std::optional<std::string> trait_name;
    std::optional<std::string> operator_trait;
    std::optional<std::string> native_type;
    std::uint32_t positional_count = 0;
    std::vector<std::string> argument_kinds;
    std::vector<std::string> argument_names;
    std::uint32_t type_argument_count = 0;
    std::int32_t return_spec = -1;
    bool is_async = false;
};

struct TypeInfo {
    std::string name;
    std::string kind;                 // object, enum
    std::vector<std::string> type_parameters;
    struct Property { bool is_private; std::string name; std::uint32_t index; std::optional<std::string> type_name; };
    struct Method { bool is_private; std::string name; std::uint32_t index; std::optional<std::string> type_name; bool is_static; };
    std::vector<Property> properties;
    std::vector<Method> methods;
    std::vector<std::string> variants;
};

struct TraitInfo {
    std::string name;
    std::vector<std::string> properties;
    struct Method { std::string name; std::uint32_t index; bool is_static; };
    std::vector<Method> methods;
};

struct FunctionMeta {
    std::string name;
    std::uint32_t code_index = 0;
    std::uint32_t min_argc = 0;
    std::int32_t variadic_index = -1;
    std::uint32_t flags = 0;
    struct Parameter {
        std::string name;
        std::uint32_t type_spec = 0;
        std::int32_t default_code = -1;
        bool is_reference = false;
        bool is_weak = false;
        bool is_variadic = false;
    };
    std::vector<Parameter> parameters;
};

struct ModuleInfo {
    std::string name;
    std::string path;
    std::uint32_t code_index = 0;
    std::vector<std::string> import_json;
    std::vector<std::pair<std::string, std::string>> exports;
};

class Image {
public:
    static Result<Image> from_bytes(const std::uint8_t* bytes,
                                    std::size_t size,
                                    const MetaBlock* meta = nullptr);

    const CodeObject& code(std::uint32_t index) const;
    const Constant& constant(std::uint32_t index) const;
    const CallSite& call_site(std::uint32_t index) const;
    const ModuleInfo& module(std::uint32_t index) const;
    const TypeInfo& type_info(std::uint32_t index) const;
    const TraitInfo& trait_info(std::uint32_t index) const;
    const FunctionMeta& function(std::uint32_t index) const;

    std::uint16_t format_version = 0;
    std::uint16_t flags = 0;
    std::string language_version;
    std::uint32_t entry_module = 0;
    std::uint32_t entry_code = 0;
    std::vector<ModuleInfo> modules;
    std::vector<TypeInfo> types;
    std::vector<TraitInfo> traits;
    std::vector<FunctionMeta> functions;
    std::vector<Constant> constants;
    std::vector<CallSite> call_sites;
    std::vector<PatternDescriptor> patterns;
    std::vector<TypeSpec> type_specs;
    std::vector<std::string> sources;
    std::vector<std::string> global_names;
    std::vector<std::string> strings;
    std::vector<CodeObject> codes;
    std::vector<std::uint8_t> raw_bytes;
    std::uint32_t crc32 = 0;
};

} // namespace pwb
```

### 5.5 `native/include/pwb/vm.hpp`

```cpp
#pragma once

#include <cstdint>
#include <span>

#include "pwb/frame.hpp"
#include "pwb/image.hpp"
#include "pwb/value.hpp"

namespace pwb {

struct RunOptions {
    bool trace = false;
    bool verify = true;
    bool trusted = false;
    std::uint64_t instruction_budget = 0;
    std::uint32_t max_frames = 900;
    std::uint32_t task_workers = 4;
};

struct NamedArgument {
    std::string name;
    Value value;
};

class VM {
public:
    VM(Image image, Heap& heap, Host& host, RunOptions options = {});
    ~VM();

    VM(const VM&) = delete;
    VM& operator=(const VM&) = delete;

    Result<Value> run();
    Result<Value> run_module(std::uint32_t module_index);
    Result<Value> run_code(const CodeObject& code,
                           const Value* arguments,
                           std::size_t argument_count,
                           Value receiver = Value::nova(),
                           FunctionObject* closure = nullptr,
                           Task* task = nullptr);
    Result<Value> call_value(Value callee,
                             const Value* positional,
                             std::size_t positional_count,
                             const NamedArgument* named,
                             std::size_t named_count);

    const Image& image() const;
    Heap& heap();
    Host& host();
    std::uint64_t instruction_count() const;
    const FrameStack& frames() const;

private:
    Result<Value> execute(Frame& frame);
    Result<Value> dispatch(Frame& frame, const Instruction& instruction);
    bool handle_error(Frame& frame, ErrorInfo* error, std::uint32_t fault_ip);
    void attach_frame(ErrorInfo* error, const Frame& frame);

    struct Impl;
    Impl* impl_;
};

Result<Value> run_embedded(const unsigned char* image,
                            std::size_t size,
                            int argc,
                            char** argv);

} // namespace pwb
```

### 5.6 `native/include/pwb/host.hpp`

```cpp
#pragma once

#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "pwb/value.hpp"

namespace pwb {

struct ModuleRequest {
    std::string name;
    std::string path;
    std::string alias;
    bool wildcard = false;
};

struct ProjectSnapshot {
    std::vector<std::string> modules;
    std::vector<std::string> paths;
    std::string log_level;
    bool allow_system = false;
    std::string root;
    std::vector<std::string> package_roots;
};

class TaskPool;

class Host {
public:
    virtual ~Host() = default;

    virtual void write_stdout(std::string_view utf8) = 0;
    virtual void write_stderr(std::string_view utf8) = 0;
    virtual bool read_stdin_line(std::string& out) = 0;

    virtual std::vector<std::uint8_t> load_module(const ModuleRequest& request) = 0;
    virtual Value project_value() = 0;

    virtual Value call_extern(std::string_view name,
                              const Value* arguments,
                              std::size_t argument_count) = 0;
    virtual Value call_builtin(std::string_view name,
                               const Value* arguments,
                               std::size_t argument_count) = 0;
    virtual Value call_native_method(std::string_view type,
                                     std::string_view name,
                                     const Value* arguments,
                                     std::size_t argument_count) = 0;

    virtual TaskPool& tasks() = 0;
    virtual std::int64_t now_millis() = 0;
    virtual void sleep_millis(std::int64_t millis) = 0;
};

class DefaultHost : public Host {
public:
    explicit DefaultHost(const ProjectSnapshot* project = nullptr);
    // Implementations of the interface above.
};

} // namespace pwb
```

### 5.7 `CompileResult` and the source generator

`CompileResult` and the generator are Python types because the integrated compiler runs in the Python host. The C++ binary only receives the generated translation unit. This split is deliberate and must not be moved into C++.

```python
@dataclass(frozen=True)
class CompileResult:
    ok: bool
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    output: Path | None
    seconds: float
    diagnostics: tuple[Diagnostic, ...] = ()
    timed_out: bool = False
    output_size: int = 0
    cache_hit: bool = False


@dataclass(frozen=True)
class TempCppOptions:
    mode: Literal["static_lib", "single_file"] = "static_lib"
    namespace: str = "pwb_generated"
    emit_checksum_assert: bool = False
    emit_image_comment: bool = True
    embed_metadata: bool = True
    embed_modules: bool = False
    embed_project: bool = False
    line_width: int = 16
    optimize: str = "O2"
    runtime_include: str = "pwb/embed.hpp"
    amalgamation_path: str | None = None


def render_temp_cpp(image: ProgramImage, options: TempCppOptions | None = None) -> str: ...
def render_temp_cpp_buffer(image: ProgramImage, options: TempCppOptions | None = None) -> io.StringIO: ...
def render_temp_cpp_into(buffer: TextIO, image: ProgramImage, options: TempCppOptions | None = None) -> None: ...
```

### 5.8 Generated opcode header

`native/include/pwb/opcode_generated.hpp` is generated from `src/vm/opcodes.py`. It is checked in and verified by `src/vm/native/abi.py --check`.

The implemented file is `native/include/pwb/opcodes_generated.hpp`, generated by `src/vm/native/gen_opcodes.py` and checked with `python -m src.vm.native.gen_opcodes --check`. The rest of this section keeps the original design name.

```cpp
#pragma once

#include <cstdint>

namespace pwb {

enum class Opcode : std::uint8_t {
    NOP = 0,
    POP = 1,
    // one member per registered opcode
    SCOPE_POP = 163,
};

constexpr std::uint32_t kOpcodeCount = 164;

enum class OperandKind : std::uint8_t {
    Value = 0, Slot, Target, Const, Spec, Call, Pattern, Module,
    Type, Trait, Field, Name, Export, Host, Event, Flags,
};

struct OpcodeInfo {
    Opcode opcode;
    const char* name;
    std::int32_t stack_in;
    std::int32_t stack_out;
    std::uint8_t operand_count;
    OperandKind operand_kinds[2];
    std::uint8_t operand_sizes[2];
};

extern const OpcodeInfo kOpcodeInfo[kOpcodeCount];

} // namespace pwb
```

The operand arrays are fixed at two because no registered opcode has more than two operands. A static assert verifies that invariant at generation time.

### 5.9 `PWBM` block layout

```text
offset  size  field
0       4     magic "PWBM"
4       2     version, currently 1
6       2     flags
8       32    image SHA-256
40      4     function count
44      ...   function records
...     4     type spec count
...     ...   type spec records
...     4     spec map count
...     ...   (code index u32, constant index u32, spec id u32) records
...     4     descriptor count
...     ...   descriptor records
...     4     CRC32 of every byte before this field
```

A function record:

```text
name length u16, name bytes
code index u32
min argc u32
variadic index i32
flags u32
parameter count u16
for each parameter:
  name length u16, name bytes
  type spec id u32
  default code index i32
  flags u8 (reference, weak, variadic)
```

A type spec record:

```text
kind u8
name length u16, name bytes
arg count u16
for each argument: type spec id u32
flags u8 (weak, reference, nullable)
```

The block is generated by `src/vm/native/meta.py` and validated by `pwb::MetaBlock::parse`. A missing block is allowed in core mode. A block whose image hash does not match is rejected.

## 6. Testing strategy

The native VM is accepted only through layered tests. Every layer has a clear owner and a clear failure message.

### 6.1 Unit tests

C++ tests live in `native/tests` and run with CTest. They use a small project-local assertion header, not an external framework, so the build has no dependency beyond the standard library.

| File | Coverage |
|---|---|
| `test_crc32.cpp` | Standard vectors and Python `zlib.crc32` comparisons |
| `test_image.cpp` | Every table, constant kind, string, span, exception entry and code object |
| `test_verifier.cpp` | Reject cases for every verifier rule |
| `test_bigint.cpp` | Parse, format, compare, add, subtract, multiply, divide, remainder |
| `test_value.cpp` | Tag layout, flags, equality, hashing, truthiness |
| `test_heap.cpp` | Retain, release, copy, CoW detach, identity memo, leak counters |
| `test_frames.cpp` | Slot initialization, stack operations, handler push and pop, generation |
| `test_vm_core.cpp` | N0 gate and scalar handlers |
| `test_dispatch.cpp` | Overload scorer parity table and argument binding |
| `test_containers.cpp` | Indexing, slicing, iteration, insertion order |
| `test_strings.cpp` | UTF-32 indexing, slicing, non ASCII, cached UTF-8 |
| `test_types.cpp` | Construction, fields, object copy, access control |
| `test_errors.cpp` | Error text, frames, finally order, cause chain |
| `test_modules.cpp` | Depth first initialization, cycles, exports |
| `test_references.cpp` | Local, global, field and index references, stale frame |
| `test_tasks.cpp` | Task states, cancellation, shutdown |
| `test_disasm.cpp` | Instruction offsets and operand formatting |

Python tests live in `tests/test_vm_native_*.py`.

| File | Coverage |
|---|---|
| `test_vm_native_abi.py` | Header regeneration, opcode count, tag order |
| `test_vm_native_sourcegen.py` | Determinism, buffer API, image embedding, validation |
| `test_vm_native_gcc.py` | Availability, version, success, failure, timeout, spaces |
| `test_vm_native_smoke.py` | N0 gate through the integrated path |
| `test_vm_native_meta.py` | PWBM determinism and image hash |
| `test_vm_native_corpus.py` | Corpus differential runner |
| `test_vm_native_unicode.py` | Generated Unicode tables |
| `test_vm_native_pack.py` | Module manifest and project snapshot |
| `test_vm_native_parity.py` | Full parity gate |
| `test_vm_native_bench.py` | Benchmark runner output |

### 6.2 Golden disassembly

The native disassembler and the Python disassembler must agree on structure, even if the text layout differs.

1. `pwb_probe --disasm --json` emits a deterministic JSON document with the module, type, trait, function, constant, call site, pattern, source and code tables.
2. `powang vm disasm --json` emits the Python form.
3. A test normalizes both documents to the same field order and compares them.
4. The golden corpus covers every opcode family and includes at least one program per milestone.
5. A snapshot change requires a reviewed opcode, compiler or verifier change.
6. The native JSON output must be stable across runs and across machines. No pointer values and no address-derived hashes appear in it.

### 6.3 Differential tests

The native differential runner compares three engines.

1. The tree walker with `--engine=tree`.
2. The Python VM with `--engine=vm`.
3. The native executable built through the integrated path.

It compares:

1. Standard output, normalized to `\n` line endings.
2. Standard error, normalized to `\n` line endings.
3. Exit code.
4. Created, modified and deleted files in the working directory.
5. Task completion sets for deterministic async programs.

Rules.

1. The Python VM is the oracle. If the Python VM and the tree walker differ, the case is recorded as a known mismatch and the native VM must match the Python VM.
2. Timing is recorded but never used for equality.
3. A mismatch saves the source, the image bytes, the native source hash, the `CompileResult` and all three outputs under `build/native/failures/<hash>/`.
4. The runner supports `--filter`, `--fail-fast`, `--json` and `--keep-going`.
5. The runner compiles at most once per program and reuses the cache on repeat runs.

The corpus layout:

```text
tests/native/corpus/
  n0/print_add.po
  n1/*.po
  n2/*.po
  n3/*.po
  n4/*.po
  n5/*.po
  stress/*.po
  errors/*.po
```

### 6.4 Fuzzing

The existing seeded fuzzer in `src/vm/fuzz.py` remains the generator. The native runner adds `--engine=native`.

1. Generate programs from the same grammar and the same seed.
2. Compile each program to a `PWB1` image.
3. Run the Python VM and the tree walker.
4. Build and run the native program.
5. Compare the same observable outputs.
6. Record the seed, source and image for every failure.

Compiling one native executable per fuzz case is too slow. The plan uses a batch runner for fuzzing.

1. `pwb_batch` embeds an array of images and a list of names.
2. Each image runs in a fresh `VMSession` in the same process.
3. Each program's stdout and stderr are separated by a deterministic marker.
4. The Python side splits the output and compares each program.
5. A crash or hang identifies the image index, then the single case is reproduced through the normal path.

The minimum fuzz gate is 1000 programs on seed 7 and 1000 on seed 2026, matching the Python VM status record.

### 6.5 Stress tests

1. Deep recursion up to the frame limit, expecting the same `RECURSION` error as Python.
2. A very large array, map and set, checking memory and insertion order.
3. A large string slice and a large character iteration.
4. Many closures and captures.
5. Many modules and imports.
6. Many spawned tasks with waits and cancellation.
7. Repeated VM creation and shutdown, at least 100 cycles.
8. Repeated integrated builds with the cache on and off.
9. A compile with a 50 KB image and a 1 MB image, recording time and peak memory.
10. A source path with spaces and non ASCII characters.

### 6.6 Compile error tests

1. A syntax error in the generated source.
2. A missing runtime header.
3. A missing runtime library.
4. A duplicate symbol.
5. A path with spaces.
6. A read only output directory.
7. A timeout, using a fake compiler command that sleeps.
8. A missing `g++`.
9. An output larger than the configured limit.
10. A stderr stream larger than the capture limit.

Assertions.

1. `CompileResult.ok` is false.
2. `diagnostics` is not empty for a normal compiler error.
3. `NativeBuildError.result` carries the full result.
4. The CLI prints a bounded, readable message.
5. The sandbox is removed.
6. No partial output file remains.

### 6.7 Cleanup tests

1. After a successful build, the sandbox directory does not exist.
2. After a failed build, the sandbox directory does not exist.
3. After a timeout, no child process remains and the sandbox is removed.
4. `git status --porcelain` does not list `temp.cpp`.
5. `--keep-source` writes exactly one `<output-stem>.cpp` file next to the executable.
6. The native cache is atomic. A killed process during `store` leaves either the old entry or the new entry, never a partial executable.
7. `powang vm native clean` removes the cache and leaves the rest of the build directory alone.

### 6.8 Memory tests

1. Heap live count returns to the baseline after a program finishes.
2. A copy-on-write detach does not leak the old storage.
3. A task release does not retain its frame.
4. A module cache release does not retain the whole program.
5. An error frame list does not retain the whole heap.
6. A failed compile does not retain the source buffer beyond the call.

Debug builds run with `PWB_DEBUG_HEAP=1` and fail the test when the live count is not zero at shutdown.

### 6.9 Cross platform tests

The first release targets Windows 11 with MinGW-W64 UCRT. The test matrix also includes:

1. `clang++ 22.1.8` as a second compiler on Windows.
2. Linux with `g++` and `clang++` in a later job.
3. macOS with `clang++` in a later job.
4. UTF-8 source files with non ASCII string literals.
5. CRLF and LF source files.
6. Windows path separators and drive letters.
7. A working directory with spaces.

The Windows toolchain is the only release blocker for N0 to N6. The other platforms are parity checks.

## 7. Performance plan

The Python VM remains the oracle. Performance work never changes behavior and never lands before the parity gate for its milestone.

### 7.1 Native value representation

1. 16 byte `Value`, trivially copyable.
2. No allocation for nova, undef, bool, int, num and char.
3. 63 bit inline integers.
4. Strings are immutable and shared.
5. Tuples are immutable and shared.
6. Arrays, maps, sets and objects use copy-on-write after N2.

### 7.2 Dispatch

N0 to N5 use a `switch` on the opcode. It is portable, debuggable and easy to profile.

N6 adds an optional direct threaded dispatch.

1. `-DPWB_THREADED_DISPATCH=1` compiles handler labels and a handler pointer in each `Instruction`.
2. The handler table is built once per image load.
3. The default build stays on `switch` until the threaded build passes the full corpus.
4. A build flag, not a language feature, chooses the dispatch mode.
5. The two modes must produce identical output on the full corpus.

### 7.3 Inline caches

1. Call site cache: resolved callee, arity, default code indices and overload candidate list.
2. Field cache: type ID to field index.
3. Method cache: type ID and name to method table entry.
4. Overload cache: argument type tag vector to the selected candidate.
5. A cache entry is valid only for the same image generation and type ID.
6. Caches are disabled in debug builds and in the differential oracle run when `PWB_NO_IC=1` is set.
7. A cache miss falls back to the full resolver.

### 7.4 Copy-on-write

1. `COPY` retains and marks shared after the deep copy corpus is green.
2. `ensure_unique` detaches only the mutated level.
3. A nested write detaches the path from the root to the leaf when the language copy would have separated them.
4. The copy corpus runs with CoW on and off and must produce the same output.
5. If CoW cannot be made green, deep copy remains the default and the performance target is adjusted, not the semantics.

### 7.5 Allocation strategy

1. Frame locals and operand stacks come from a per VM slot arena. A frame push and pop is a pointer bump and a reset.
2. Heap objects use size classes for small strings, arrays and objects.
3. The release list defers frees to the end of the current instruction.
4. Large containers allocate their storage separately so a small header move is cheap.
5. A future tracing collector can replace the heap policy behind `Heap`.
6. Allocation counters are always available in debug builds and behind `PWB_HEAP_STATS=1`.

### 7.6 Startup

1. No AST JSON parsing at startup. The PWBM block is a flat binary read.
2. Builtin and native method tables are static arrays, not hash maps built at startup.
3. Trusted mode skips dataflow when the cache records a strict verified image.
4. Module images are memory mapped or read once.
5. The image parser does one CRC check and one image parse. The generated `main` has no separate CRC check.
6. The static runtime library avoids dynamic loader work for the runtime itself.

### 7.7 Benchmark corpus and targets

| Benchmark | What it measures | Target |
|---|---|---|
| `arithmetic_loop.po` | Integer arithmetic and branches | 3x faster than the tree walker |
| `recursion.po` | Function calls and frames | 2.5x faster |
| `containers.po` | Array and map updates | 2x faster |
| `strings.po` | String indexing and slicing | 2x faster |
| `objects.po` | Object allocation and field access | 2x faster |
| `traits.po` | Trait and operator dispatch | 2x faster |
| `errors.po` | Throw, catch and finally | 1.5x faster |
| `tasks.po` | Lazy and worker tasks | 1.5x faster |
| `module_load.po` | Module initialization | Equal or faster |
| `startup.po` | Process startup and image load | Within 1.2x of the tree walker |

Correctness target: zero differential mismatches. A performance number without a green corpus is not reported.

### 7.8 Measurement rules

1. Three runs, median reported.
2. Same machine, same power profile, no debugger attached.
3. Record wall time, peak RSS and instruction count.
4. Record the exact compiler version and flags.
5. Record the image SHA-256 and runtime version.
6. Compare against the Python VM and the tree walker in the same session.
7. A regression above ten percent blocks the milestone until explained.

## 8. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation | Milestone |
|---|---|---|---|---|
| Host builtin surface is larger than expected | High | Medium | Implement by family, add a coverage test for the 29 names, return a clear unsupported error | N2, N5 |
| Native method surface drifts | High | Medium | Generate the 60 name coverage test from `NATIVE_METHOD_NAMES`, implement 53 at N2 and 7 at N5 | N2, N5 |
| Copy semantics differ from Python | High | High | Deep copy first, identity memo, dedicated copy corpus, CoW only after green | N2 |
| Exception and finally parity | High | High | Port the transfer opcodes as one unit, golden error snapshots, exact `PowangError` text | N4 |
| `PWBM` metadata drifts from the image | Medium | High | Image SHA-256 in the block, deterministic generator, `--check` in CI, reject a mismatch | N1 |
| Type spec and cast parity | High | High | Compile type specs from the same Python nodes, port `assignable`, `explicit_cast`, `runtime_type_matches`, scorer parity table | N1 to N3 |
| Windows toolchain differences | Medium | Medium | `g++` version probe, stdin bytes, argv lists, static link, `clang++` second check | N0 |
| Path quoting and spaces | Medium | Medium | argv only, no shell, path with spaces test | N0 |
| Timeout leaves child processes | Medium | Medium | Process tree kill with `taskkill /T /F`, sandbox cleanup test | N0 |
| Task scheduling is non deterministic | Medium | Medium | One worker test mode, deterministic corpus, stress shutdown test | N5 |
| Source positions differ | Medium | High | Predecoded spans, `ln: N | ` exact format, error position snapshots | N1, N4 |
| Bigint edge cases | Medium | Medium | Standard vectors, Python comparison table, division sign tests | N1 |
| Unicode behavior differs | Medium | Medium | Generate tables from Python `unicodedata`, regenerate check | N2 |
| Module resolution differs | Medium | High | Reuse the Python module loader at build time, manifest hashes | N4 |
| Reference lifetime bugs | Medium | High | Frame generation, verifier static cases, dedicated reference corpus | N4 |
| Debugger metadata is insufficient | Medium | Low | Keep spans, local names, parameter names and instruction boundaries in the image | N6 |
| Performance target is missed | Medium | Low | Profile after parity, inline caches, threaded dispatch, adjust the claim rather than semantics | N6 |
| Default engine switch is premature | Low | High | Keep Python VM default until the full differential suite passes one release | N6 |

### 8.1 Fallback plan

If the native VM cannot reach full parity, the project still ships the build path and a supported subset.

1. Keep the Python VM as the default engine.
2. Ship `--engine=native` as an opt-in engine for the milestones that are gate green.
3. Report `unsupported: <feature>` with the opcode or language feature and a pointer to `--engine=vm`.
4. Keep the native build path and the differential harness, because they are useful even for a subset.
5. Do not change the default engine, do not remove the tree walker and do not claim full parity.
6. Re-scope the remaining work as a new phase with its own gates.

The fallback is explicit in the CLI help and in the release notes. A partial native engine is never described as complete.

## 9. Versioning and release plan

### 9.1 Version table

| Release | Milestones | Native status | Default engine | Notes |
|---|---|---|---|---|
| `0.23.0` | N0, N1, N2 | Opt-in `--engine=native`, scalars and containers | Python VM | Build path and core subset |
| `0.24.0` | N3, N4, N5 | Opt-in, types, modules, errors and async | Python VM | Feature complete for the native corpus |
| `0.25.0` | N6 | Full parity release candidate | Python VM unless every gate passes | Default switch decision recorded in the release notes |

### 9.2 Version constants

`native/include/pwb/version.hpp`:

```cpp
#define PWB_RUNTIME_VERSION "0.1.0"
#define PWB_GENERATOR_VERSION "1"
#define PWB_HOST_ABI_VERSION 1
#define PWB_BYTECODE_FORMAT_VERSION 1
#define PWB_METADATA_FORMAT_VERSION 1
```

1. `PWB_RUNTIME_VERSION` follows semantic versioning and bumps on any behavior change.
2. `PWB_GENERATOR_VERSION` is an integer and bumps on any generated source layout change.
3. `PWB_HOST_ABI_VERSION` is an integer and bumps on any host interface change.
4. The bytecode format version stays `1`. The native VM does not change `PWB1`.
5. The metadata format version stays `1` until the sidecar is replaced by a future image format.

### 9.3 Release gates

A release is blocked when any of these is true.

1. The Python VM suite fails.
2. The tree walker suite fails with `POWANG_ENGINE=tree`.
3. The native corpus has a mismatch.
4. An example output differs.
5. An error snapshot differs.
6. A fuzz seed reports a mismatch.
7. A stress or cleanup test fails.
8. The LSP diagnostics differ.
9. The native benchmark misses its target without a recorded explanation.

### 9.4 Engine selection

1. `--engine=tree` runs the tree walker.
2. `--engine=vm` runs the Python VM. This remains the default until N6.
3. `--engine=native` runs the integrated native build and execution path.
4. `POWANG_ENGINE` accepts the same three values.
5. `project.engine` accepts the same three values.
6. An unknown engine name is a usage error with exit code 2.
7. The help text documents which engines are stable and which are opt-in.
8. The tree walker remains the fallback after any native or Python VM regression.

### 9.5 Changelog and documentation

Each release updates:

1. `CHANGELOG.md` with the native milestone, the supported subset and the known limitations.
2. `pyproject.toml` with the package version.
3. `docs/phase-4b-bytecode-vm/implementation/STATUS.md` with the N milestone rows.
4. `docs/phase-4b-bytecode-vm/implementation/N0-native-cpp17-build-plan.md` when a decision changes.
5. `docs/phase-4b-bytecode-vm/implementation/V10-native-vm-contract.md` when the implemented contract is final.
6. `README.md` with the native build prerequisites and the `powang vm native` commands.

### 9.6 Rollback

1. A native regression is fixed by changing `PWB_RUNTIME_VERSION`, which invalidates the cache.
2. A release with a native regression keeps the Python VM as the default.
3. A broken native artifact is removed from the cache with `powang vm native clean`.
4. The Python VM and the tree walker are never removed as part of a native release.
5. A rollback does not require reverting the Python VM or the compiler.

## 10. Open decisions

| Decision | Options | Recommendation | Needed by |
|---|---|---|---|
| Native language | C++17, Rust, C | C++17 per this request | decided |
| Buffer build layout | Static runtime library, single file amalgamation | Static library by default, single file opt-in | N0 |
| String storage | UTF-32, UTF-8 plus index | UTF-32 first, compact representation later | N0 |
| Integer inline range | 63 bit, 64 bit | 63 bit, matching the compiler and the design | N1 |
| Bigint implementation | Internal limbs, external library | Internal signed magnitude limbs, no dependency | N1 |
| Static linking | Static, dynamic | Static by default, dynamic for debug | N0 |
| Metadata transport | `PWBM` sidecar, `PWB2` format | `PWBM` sidecar now, `PWB2` later | N1 |
| Host ABI | C++ abstract class, C ABI | C++ abstract class for N0 to N5, C ABI for externs in N4 | N4 |
| Worker pool | Fixed, adaptive | Fixed four by default, one in deterministic tests | N5 |
| Cache location | OS cache, repository cache | OS cache by default, `--native-cache local` opt-in | N0 |
| Default engine at `0.25.0` | Python VM, native VM | Flip only if every full parity gate passes | N6 |
| MSVC support | Now, later | Later, after the MinGW-W64 release is stable | N6 |
| Native debugger | Now, later | Later, after the engine parity release | N6 |
| Tracing collector | Now, later | Later, only if reference counting shows a real limit | N6 |

A decision is recorded in this table before the milestone that needs it starts. A change after the milestone starts requires a new ADR.

## 11. A first implementation slice

The first commit is deliberately small. It creates the native skeleton, the generated opcode contract and the image reader. It does not execute bytecode yet. That keeps the first review focused on the ABI and the reader.

This section is the original first-slice plan. N0 is now implemented, so the current file names and commands are in the Implementation note at the top and in section 4.1.

### 11.1 Commit message

```text
native: add the PWB1 reader, CRC32 and generated opcode contract
```

### 11.2 Files created by the first commit

1. `native/CMakeLists.txt`
2. `native/README.md`
3. `native/include/pwb/version.hpp`
4. `native/include/pwb/value.hpp`
5. `native/include/pwb/image.hpp`
6. `native/include/pwb/opcode_generated.hpp`
7. `native/include/pwb/crc32.hpp`
8. `native/src/crc32.cpp`
9. `native/src/image.cpp`
10. `native/tools/pwb_probe.cpp`
11. `native/tests/test_main.cpp`
12. `native/tests/test_crc32.cpp`
13. `native/tests/test_image.cpp`
14. `src/vm/native/__init__.py`
15. `src/vm/native/abi.py`
16. `tests/test_vm_native_abi.py`
17. `docs/phase-4b-bytecode-vm/implementation/N0-native-cpp17-build-plan.md`

### 11.3 What each file does

1. `native/CMakeLists.txt` defines `pwb_runtime` as a static library and `pwb_probe` as a console executable, with C++17, warnings and a Release and Debug configuration.
2. `native/include/pwb/version.hpp` defines the runtime, generator, host ABI, bytecode format and metadata format versions.
3. `native/include/pwb/value.hpp` defines `Tag`, `ValueFlags` and the 16 byte `Value` with the static asserts.
4. `native/include/pwb/image.hpp` defines `SourceSpan`, `ExceptionEntry`, `Constant`, `Instruction`, `CodeObject`, `CallSite`, `TypeInfo`, `TraitInfo`, `ModuleInfo` and the `Image` class with `from_bytes`.
5. `native/include/pwb/opcode_generated.hpp` is generated by `src/vm/native/abi.py` and contains `Opcode`, `kOpcodeCount`, `OperandKind`, `OpcodeInfo` and `kOpcodeInfo`.
6. `native/include/pwb/crc32.hpp` and `native/src/crc32.cpp` implement the standard reflected CRC-32.
7. `native/src/image.cpp` reads the container, validates the magic, version, table count, lengths, CRC and UTF-8, and decodes every table into native structs.
8. `native/tools/pwb_probe.cpp` prints the image header, table counts, CRC result and a flat table dump.
9. `native/tests/test_crc32.cpp` checks the standard vectors and a Python compatibility vector.
10. `native/tests/test_image.cpp` reads an image written by the Python compiler and asserts the header, table counts, module name, code name and constant values.
11. `src/vm/native/abi.py` renders the header from `src/vm/opcodes.py` and supports `--check`.
12. `tests/test_vm_native_abi.py` regenerates the header and asserts it matches the checked-in file.
13. This plan document records the decisions and the follow-up commits.

### 11.4 Verification commands

Generate a probe image from a real program:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from src.vm.compiler import compile_source; image = compile_source('print(1 + 2);', path='probe.po', module_name='probe', check=False); Path('build/native/probe.pwb').write_bytes(image.to_bytes()); print(len(image.to_bytes()))"
```

Check the generated opcode header:

```powershell
.\.venv\Scripts\python.exe -m src.vm.native.abi --check
```

Build the native probe:

```powershell
cmake -S native -B build/native -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/native
```

Run the C++ tests:

```powershell
ctest --test-dir build/native --output-on-failure
```

Run the Python ABI tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vm_native_abi -v
```

Inspect the image:

```powershell
.\build\native\pwb_probe.exe build\native\probe.pwb
```

Expected output shape:

```text
magic: PWB1
format: 1
language: 0.22.0
flags: 0
crc32: ok
tables: meta=1 modules=1 types=0 traits=0 functions=0 constants=0 call_sites=1 patterns=0 type_specs=0 sources=1 global_names=0 strings=0 debug_lines=0 codes=1
module[0]: name=probe path=... code=0 exports=0
code[0]: name=probe locals=1 params=0 max_stack=10 instructions=10
```

The exact instruction count and offsets must match the N0 gate image in section 4.1.

### 11.5 What the first commit does not do

1. It does not execute bytecode.
2. It does not render `temp.cpp`.
3. It does not invoke `g++`.
4. It does not claim any milestone gate.
5. It does not modify the Python VM, the compiler or the checker.

The second commit adds the verifier and disassembler. The third adds the N0 execution loop and the builtin `print`. The fourth adds the source generator. The fifth adds the integrated `g++` driver. The sixth adds the N0 gate test. The commit messages are listed in section 4.1.

### 11.6 First slice acceptance

The first slice is complete when:

1. `src/vm/native/abi.py --check` exits 0.
2. `cmake --build build/native` succeeds with no warnings.
3. `ctest --test-dir build/native` passes.
4. `tests.test_vm_native_abi` passes.
5. `pwb_probe` reads a real `PWB1` image and prints the expected header and counts.
6. `git status --porcelain` shows only the intended new files.

### 11.7 Verified facts used by this plan

These facts were checked against the repository at plan time. They are the basis for the concrete numbers and commands above.

1. `src/vm/opcodes.py` registers 164 opcodes. The last entry is `SCOPE_POP` at opcode 163.
2. `src/builtins` exposes 29 builtins. The full list is `cancel`, `chr`, `close`, `digit_value`, `error`, `fail`, `format`, `input`, `inputf`, `is_alnum`, `is_alpha`, `is_ascii`, `is_digit`, `is_lower`, `is_space`, `is_upper`, `open`, `ord`, `print`, `printf`, `println`, `read`, `size`, `system`, `task_status`, `typedeep`, `typeof`, `wait`, `write`.
3. `NATIVE_METHOD_NAMES` lists 60 methods across `arr`, `char`, `file`, `map`, `set`, `str`, `task` and `tup`.
4. `src/vm/image.py` uses `PWB1`, format version 1, 14 tables and a CRC32 over the bytes before the checksum.
5. A real image for `examples/arithmetics.po` is 24545 bytes with 1 code object and 35 call sites. `examples/collections.po` is 55029 bytes with 1 code object and 69 call sites. `examples/types.po` is 38931 bytes with 4 code objects and 18 call sites.
6. The local toolchain is `g++ 16.1.0` MinGW-W64 UCRT, with `cmake 4.4.2` and `ninja 1.13.2`.
7. A stdin compile with `g++ -std=c++17 -x c++ -` and `-static -static-libgcc -static-libstdc++ -pthread -s` was tested and produces a working console executable.
8. `print(1 + 2)` produces the exact N0 gate image in section 4.1.
9. The Python VM, the compiler, the verifier and the tree walker are present and passing at `0.22.0`. At plan time the native VM was not present. N0 is now implemented under `native/` and `src/vm/native/`. N1 to N6 remain planned and the full native VM is not complete.

The plan does not assume any fact that was not checked in the repository or in the local toolchain.

---

End of plan.
