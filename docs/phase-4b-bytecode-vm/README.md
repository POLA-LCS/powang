# Phase 4B: Bytecode VM

Status: design proposal. No VM code has been written yet.

Target language version: Powang `0.21.0`.

Target tooling version: powang-lsp `0.27.0`.

Phase 4A defines the debugger. This document defines the execution engine
track. The VM work can start in parallel with debugger work because both
depend on stable source spans and frame metadata. The VM should not delay the
debugger unless the project explicitly reorders the roadmap.

## 1. Purpose

The current interpreter evaluates the AST directly. That design is good for
language exploration because every feature is visible in one place. It is a
poor long-term execution model because every evaluation walks Python objects,
repeats name lookup, and allocates host objects for short-lived values.

This phase defines a bytecode virtual machine that executes the same language
with explicit instructions, explicit frames, explicit values and explicit
module boundaries. The VM must be a drop-in replacement for the tree-walker.
It must not become a second language with slightly different behavior.

The word perfect in this plan means one thing. A program that passes the
checker must produce the same output, the same runtime error, the same error
position, the same exit code and the same observable side effects on both
engines.

Performance is a goal. Semantic equality is the gate.

### 1.1 Current baseline

As of Powang `0.19.1` the repository has 501 interpreter tests, 83 LSP Python
tests, 3 Node protocol tests and a passing example suite. The VM must keep this
baseline green on every migration phase.

## 2. Scope

In scope:

- A stack-based bytecode format.
- A compiler from the existing AST to bytecode.
- A bytecode verifier.
- A reference VM implemented in Python.
- A disassembler and trace mode.
- A differential test harness that runs the existing suite on both engines.
- A native VM design that can consume the same bytecode contract later.
- The engine selection flag and migration path.
- Debug metadata and hooks that the Phase 4A debugger can consume.

Out of scope:

- Redesigning the parser or the type checker.
- Changing language syntax.
- Adding new language features.
- A JIT compiler.
- A garbage collector for the Python reference VM.
- A production native VM implementation in this phase.
- Preemptive async scheduling.
- Coroutine suspension at arbitrary expression boundaries.
- A formatter or a linter.

## 3. Goals

The VM must provide:

1. Semantic equality with the tree-walker.
2. Explicit low-level instructions for every implemented language feature.
3. A clean separation between frontend, compiler, verifier, runtime and host.
4. Enough metadata for exact runtime diagnostics and future debugging.
5. A bytecode contract that can be implemented in another language.
6. A measurable path to better performance.
7. Tests that make semantic drift impossible to ignore.

## 4. Non-goals

The first VM is not expected to be faster than the tree-walker in Python. A
Python dispatch loop may be slower than direct AST evaluation. The Python VM is
the reference implementation and the differential oracle. The native VM is
where the performance target lives.

The first VM is not a sandbox. Host capabilities such as file access and
`system` remain controlled by the existing project settings and future
capability work.

## 5. Design principles

### 5.1 One opcode registry

Every opcode must be declared once. The same declaration drives:

- The compiler emitter.
- The bytecode encoder.
- The verifier.
- The interpreter handler.
- The disassembler.
- The opcode documentation table.

The project must not maintain a compiler switch and a separate VM switch that
can drift.

The registry entry should be the only place where an opcode is introduced. A
minimal entry looks like this:

```python
@dataclass(frozen=True)
class OpcodeSpec:
    name: str
    opcode: int
    operands: tuple[Operand, ...]
    stack_in: int
    stack_out: int
    verifier: str
    handler: str
```

Generator tests assert that every opcode has a compiler emitter, a verifier
rule, an interpreter handler, a disassembler formatter and at least one test.

### 5.2 Low-level, but semantic

The instructions are low-level enough to be executed by a small loop. They are
not so low-level that a single language feature becomes hundreds of machine
operations. A `MATCH` instruction may carry a pattern descriptor. A `CALL`
instruction may carry a call site descriptor. The instruction stream remains
linear and verifiable.

### 5.3 The tree-walker is the oracle

During migration the tree-walker is not deleted. It remains the reference
implementation. Every VM feature lands with differential tests against the
tree-walker.

### 5.4 No hidden behavior in the compiler

If a language feature has observable runtime behavior, the bytecode must show
it. The compiler may lower syntax sugar to existing instructions, but the
lowering rule must be documented and tested. A pipeline operator may disappear
into a call, but the call and its argument order must be explicit.

### 5.5 Values have one representation per tag

A value is either an immediate scalar or a reference to one heap object. The
VM must not have two incompatible ways to represent the same language value.

### 5.6 Error messages are part of the ABI

Runtime errors are not implementation details. The VM must use the same error
kinds, messages, positions and frame formatting as the tree-walker.

### 5.7 Deterministic execution

Hash iteration order must not affect output. Maps and sets preserve insertion
order. Task scheduling must have deterministic test hooks. Fuzzing must be
reproducible from a seed.

### 5.8 Why a stack machine

A stack machine lowers naturally from an AST, keeps instruction encoding small
and makes stack-height verification simple. A register machine can reduce the
instruction count, but it complicates calls, copies, closures and dynamic
dispatch because every instruction must name its source and destination
registers.

The first VM is stack based. A register IR can be added later as an
optimization behind the same verifier, bytecode contract and differential test
suite.

## 6. System architecture

The system is divided into five layers.

### 6.1 Frontend

The frontend is the existing lexer, parser, simplifier and type checker.

The compiler consumes:

- The parsed program AST.
- The module graph.
- The type checker result: types, traits, signatures, overload sets and
  resolved module exports.
- Source spans for every AST node.

The frontend does not know about bytecode.

The checker must expose a stable `ResolutionResult` for the compiler. At
minimum it must provide:

- Module export tables.
- Object type layouts and method tables.
- Trait tables and trait-qualified method tables.
- Function signatures, generic metadata and variadic metadata.
- Overload sets and resolved overload candidates.
- Local and parameter types where the checker has inferred them.
- Const macro expansions.
- Resolved import paths and module identities.
- Source spans and declaration comments.

If the checker currently keeps this information in private instance fields, the
VM phase includes a refactor to expose it through a read-only result object.
The compiler must not duplicate the checker logic.

### 6.2 Compiler

The compiler has these passes:

1. Module discovery and parse.
2. Declaration collection.
3. Cross-module symbol resolution.
4. Type and signature resolution.
5. Scope and capture resolution.
6. AST lowering to an instruction builder.
7. Label resolution and jump patching.
8. Peephole optimization.
9. Code object construction.
10. Linking of module, type, trait, function and call site IDs.
11. Verification.

The compiler emits a `ProgramImage`.

### 6.3 Program image

A `ProgramImage` contains:

- Format magic and version.
- Language version.
- Entry module and entry code object.
- Module table.
- Type table.
- Trait table.
- Function table.
- Constant pool.
- Call site table.
- Pattern descriptor table.
- Type spec table.
- Source file table.
- Global name table.
- String table.
- Debug line table.

The program image is the unit that can be cached, disassembled and verified.

### 6.4 Verifier

The verifier runs before execution in development and debug builds. It checks:

- Opcode validity.
- Operand ranges.
- Constant pool types.
- Stack height at every instruction.
- Local slot ranges.
- Jump targets inside the code object.
- Exception table ranges.
- Call site arity and argument kinds.
- Module and type identifiers.
- Pattern descriptor references.
- Source span indices.
- Max stack and max frame size.

The verifier never executes user code.

### 6.5 Runtime

The runtime contains:

- The frame stack.
- The operand stack.
- The global and module stores.
- The heap.
- The type and trait registries.
- The call dispatch logic.
- The error unwinder.
- The task pool.
- The host boundary.

### 6.6 Host

The host provides:

- Standard output and input.
- File streams.
- System commands.
- Module loading and package resolution.
- Project configuration.
- Extern functions.
- Task workers.
- Clock and sleep.
- Optional debugger transport.

The host is behind a narrow interface. The VM does not import Python modules
for file or system operations directly.

## 7. Execution model

### 7.1 Stack machine

The VM is stack based. Values are pushed and popped from an operand stack. A
function frame owns a local slot array and an operand stack.

A frame contains:

- Code object reference.
- Instruction pointer.
- Local slots.
- Operand stack base and top.
- Closure reference.
- Module reference.
- Receiver reference for methods.
- Exception handler stack.
- Current source span.
- Return destination.
- Reference cleanup list.
- Task reference when the frame belongs to a task.

### 7.2 Locals and globals

Locals are indexed by slot. The compiler assigns slots for parameters,
declarations, destructuring bindings, match bindings and temporary hidden
values.

Module-level declarations are globals. They live in a module store keyed by
global ID. Modules are immutable after initialization. A module global cannot
be assigned through a module member expression.

The REPL uses a persistent module store so top-level declarations survive
between cells.

### 7.3 Captures

A closure captures slots from an enclosing frame. Captures are explicit. The
compiler emits `MAKE_CAPTURE` for each captured slot and stores the capture
indices in the code object metadata.

Captured values follow the same copy rules as ordinary values. The compiler
must follow the existing lambda capture rules exactly. Capture behavior is
defined by the tree-walker and must be covered by differential tests.

### 7.4 Calls

A call site descriptor contains:

- Dispatch kind.
- Callee name when applicable.
- Module ID when applicable.
- Type ID when applicable.
- Trait ID when applicable.
- Operator trait ID when applicable.
- Native method ID when applicable.
- Builtin ID when applicable.
- Extern ID when applicable.
- Positional argument count.
- Named argument entries.
- Spread argument positions.
- Type argument count and type specs.
- Parameter layout for default filling.
- Overload set ID when applicable.
- Expected return type spec.
- Async flag.

The compiler pushes the receiver, if any, and the evaluated arguments in a
stable order. The call instruction consumes them and pushes one result or
raises one error.

Default arguments are evaluated in the callee frame. The call site marks which
parameters are missing. The callee prologue fills them in source order.

Named arguments are mapped to parameter slots by the descriptor. Arguments are
evaluated in source order, not parameter order. This matters for side effects.

Spread arguments are expanded by the call binder. A string spread produces
characters. A map spread produces key-value tuples.

### 7.5 Return

`RETURN` pops the return value and unwinds the frame. The caller receives a
copy of the value unless the function is returning a reference, which the
language does not allow as a first-class return.

The compiler emits `CAST_RETURN` before `RETURN` when the function has a return
annotation and the runtime needs to apply a cast.

### 7.6 Copy semantics

The language has value semantics for arrays, maps, sets, tuples and user
objects. Function values share closures. Tasks, files, modules, handles,
project values and references have identity semantics.

The compiler emits `COPY` at these boundaries:

- Plain parameter binding.
- Return value delivery.
- Typed or inferred declaration binding.
- Assignment to a variable.
- Assignment to a field or container element.
- Native method value forms that return a copy.

The VM may implement `COPY` as a copy-on-write retain. The observable result
must match a deep copy. Mutation instructions call `ensure_unique` before
writing a shared heap object.

The compiler never emits `COPY` for reference parameters. A reference
parameter receives a `REF` value and writes through it.

### 7.7 Error handling

Every frame has an exception handler stack. An exception handler entry stores:

- Protected instruction range start and end.
- Catch target.
- Finally target.
- Frame stack depth.
- Operand stack depth.
- Local slot watermark.

On `THROW`, the VM walks the handler stack from the innermost entry outward. It
restores the operand stack, runs the finally block if present, and transfers
control to the catch target. If no handler exists, the frame is unwound and the
error propagates to the caller.

Errors carry:

- Kind.
- Message.
- Details.
- Where.
- Line.
- Column.
- Cause.
- Frames.

The VM appends one frame per active call, with function name and source
position. The formatting must match the tree-walker.

### 7.8 Async model

Async functions return lazy tasks. The body does not start until the task is
awaited or waited on. This is the current language model. The VM must not
introduce suspension at arbitrary expression boundaries.

`ASYNC_CALL` creates a lazy task containing a closure and evaluated arguments.
`AWAIT` runs a lazy task on the current thread or waits for a worker task and
pushes its result. `SPAWN` creates and starts a worker task.

Task errors propagate through `AWAIT` and through `try` and `catch`. Task
cancellation is checked at call boundaries and backward jumps.

### 7.9 Top-level code

A module has an init code object. Top-level statements are executed in that
code object. Top-level declarations become module globals. Top-level `await`
is allowed and uses the same `AWAIT` instruction.

## 8. Value model

### 8.1 Tags

Every value has one tag.

| Tag | Payload | Notes |
|---|---|---|
| NOVA | none | The absence value |
| UNDEF | none | Internal empty variadic marker |
| BOOL | 1 bit | true or false |
| INT | signed integer | Inline small values, big integer fallback |
| NUM | f64 | IEEE 754 double |
| CHAR | u32 | Unicode scalar value |
| STR | heap reference | Immutable code point string |
| ARR | heap reference | Mutable array with copy-on-write |
| TUP | heap reference | Immutable tuple |
| MAP | heap reference | Insertion-ordered map |
| SET | heap reference | Insertion-ordered set |
| FUN | heap reference | Function or closure |
| OBJ | heap reference | User object or enum value |
| MODULE | heap reference | Module namespace |
| TASK | heap reference | Lazy or worker task |
| ERROR | heap reference | Catchable error value |
| REF | heap reference | Reference to a slot or location |
| HANDLE | heap reference | Opaque host object |
| PROJECT | heap reference | Project configuration object |
| ANY | heap reference | Gradual or union box |

### 8.2 Immediate values

Booleans, nova, undef, small integers, finite numbers and characters should be
immediate values in the native VM. The Python reference VM may use tagged
Python objects behind a `Value` wrapper.

Small integers are inline signed 63-bit values. Larger integers use a heap
bigint. This preserves the current interpreter behavior for unbounded integers.

### 8.3 Strings

Strings are immutable sequences of Unicode scalar values. The native VM should
store strings as a UTF-32 code point array or a compact UTF-8 representation
with a code point index. The reference VM may use Python `str` directly.

String indexing, string iteration and string spread return `char`. String
slicing returns `str`. `str.chars` materializes an `arr[char]`.

### 8.4 Characters

A character is a 32-bit Unicode scalar value. Surrogates and values above
`U+10FFFF` are invalid. Character literals and `chr` validate this.

### 8.5 Any and union boxes

A value declared as `any`, a union or an uninitialized typed slot may need to
preserve both its concrete payload and its declared type. The VM uses an `ANY`
box.

An `ANY` box stores:

- Concrete value.
- Declared type spec.
- Defined flag.
- Weak flag.
- Concrete type name.

The compiler emits `BOX_ANY` and `UNBOX_ANY` at boundaries where the checker
has lost a concrete type. When the static type is concrete, the VM uses the
unboxed value directly.

### 8.6 Equality and hashing

`EQ` compares values according to language rules. Built-in scalar values
compare by value. Objects compare by identity unless the `Compare` trait
provides a comparison. Map and set keys use the same equality and hash rules as
the tree-walker.

Hashing must be stable within one process and deterministic across runs for
the same key. Map and set iteration order is insertion order, never hash order.

### 8.7 Copy-on-write

Arrays, maps, sets and user objects are value types. The VM may share their
storage until a mutation occurs.

A heap object has a `shared` flag. `COPY` increments a reference count or marks
the object shared. A mutation instruction calls `ensure_unique`. If the object
is shared, it clones the object and its immediate children according to the
language copy rules. The original object remains unchanged.

Tuples and strings are immutable and can always be shared by reference.

## 9. Heap objects

### 9.1 Object header

Every heap object has:

- Tag.
- Type ID or heap kind.
- Flags: defined, weak, const structure, const elements, shared, locked.
- Reference count in the native VM.
- Optional source type name.

### 9.2 Arrays

An array stores a contiguous element vector. The header stores length and
capacity. `ensure_unique` copies the vector. `LOCK_STRUCTURE` prevents length
changes. `LOCK_ELEMENTS` prevents element assignment.

### 9.3 Tuples

A tuple stores a fixed element vector. Tuples are immutable and share freely.

### 9.4 Maps

A map stores an insertion-ordered table. The native VM may use an open
addressing table plus an insertion order vector. Keys are values. The map
preserves insertion order for iteration, printing and `keys` and `values`.

### 9.5 Sets

A set stores unique values with insertion order. It shares the map
implementation but drops values.

### 9.6 User objects

A user object stores:

- Type ID.
- Field slots.
- Property visibility flags.
- Method table reference.
- Trait method table reference.
- Const and weak flags.
- Defined flag.

Fields are ordered by declaration order for display and copy. Field IDs are
program-image constants.

### 9.7 Enums

An enum value stores:

- Enum type ID.
- Variant ID.
- Variant name.
- Optional payload for future enum payload support.

Enums compare by type and variant.

### 9.8 Functions and closures

A function value stores:

- Code object reference.
- Captured values.
- Default argument expressions or evaluated defaults.
- Function type metadata.
- Async flag.
- Variadic metadata.
- Lambda name.

Function values are first-class. The VM must support passing them, storing
them, returning them and calling them through `CALL_VALUE`.

### 9.9 Modules

A module value stores:

- Module ID.
- Module name.
- Resolved path.
- Immutable export table.
- Host module flag.
- Initialization state.

Modules are immutable after initialization. Module member assignment is a
runtime error.

### 9.10 Tasks

A task stores:

- State: lazy, running, completed, failed, cancelled.
- Closure and arguments for a lazy task.
- Worker thread or worker identifier for a spawned task.
- Result value or error value.
- Cancellation flag.
- Creation and completion timestamps.
- Task ID for status and debugging.

### 9.11 Errors

An error stores:

- Kind.
- Message.
- Detail strings.
- Where.
- Line and column.
- Cause error.
- Frame list.
- Runtime stack snapshot in debug mode.

### 9.12 References

A reference stores:

- Kind: local, global, field or index.
- Target object.
- Target slot or field or index.
- Read and write callbacks in the reference VM.
- Lifetime frame ID.

References are valid only during one call. Storing a reference in a variable,
container or object is an error.

### 9.13 Handles

A handle wraps an opaque host object. The VM never inspects the payload. Host
functions unwrap handles after checking the capability and type.

### 9.14 Project

A project value stores the `Project` fields from `project.po`:

- `modules`: arr[str]
- `paths`: arr[str]
- `logLevel`: str
- `allowSystem`: bool

The value behaves like the existing built-in object type.

## 10. Bytecode format

### 10.1 Container

A program image starts with:

- Magic bytes `PWB1`.
- Format version.
- Language version.
- Flags.
- Counts for each table.
- Table offsets.
- Checksum.

The container is little-endian. The checksum covers the code and metadata.
Debug tables are optional.

### 10.2 Code object

A code object contains:

- Name.
- Source file ID.
- Parameter count.
- Local count.
- Capture count.
- Max operand stack depth.
- Max frame depth.
- Instruction bytes.
- Constant pool indices.
- Exception table.
- Source span table.
- Local name table.
- Parameter metadata.
- Return type spec.
- Async and variadic flags.
- Trait and operator metadata when applicable.

### 10.3 Instruction encoding

The base encoding is:

- One opcode byte.
- Zero or more fixed-width operands.
- Operand widths come from the opcode registry.
- All operands are little-endian.

The compiler uses a label-based builder. The builder emits temporary operand
placeholders and patches them after jump resolution.

### 10.4 Constant pool

The constant pool stores:

- Strings.
- Integers outside the inline range.
- Floating-point numbers.
- Type specs.
- Call sites.
- Pattern descriptors.
- Function signatures.
- Source spans.
- Global names.
- Module names.
- Field names.
- Native method IDs.
- Builtin IDs.
- Extern IDs.

Constants are deduplicated by structural equality.

### 10.5 Source spans

Every instruction has a source span index. The span table stores file ID, start
line, start column, end line and end column. Runtime errors and traces use the
span of the currently executing instruction.

### 10.6 Exception table

An exception table entry contains:

- Start instruction offset.
- End instruction offset.
- Handler instruction offset.
- Handler kind: catch or finally.
- Stack depth at entry.
- Local slot watermark.

Entries are sorted and non-overlapping for a given protected region.

### 10.7 Verifier rules

The verifier decodes the instruction stream and simulates stack heights. It
must reject:

- Unknown opcodes.
- Truncated instructions.
- Invalid constant indices.
- Invalid local slots.
- Jumps outside the code object.
- Jumps into the middle of an instruction.
- Stack underflow.
- Stack height mismatch at a merge point.
- Invalid call arity.
- Invalid type spec indices.
- Invalid module and type IDs.
- Invalid exception ranges.
- Missing return on a non-nova function.
- Invalid reference lifetime markers.

The verifier can run in two modes:

- Strict mode for development and tests.
- Trusted mode for a previously verified cached image.

## 11. Instruction set

The instruction tables use this notation:

- `a, b` on the stack means two values with `b` on top.
- `a -> b` means one input becomes one output.
- `u8`, `u16`, `u32`, `i32`, `f64` are operand widths.
- `spec` is a type spec constant index.
- `call` is a call site constant index.
- `pattern` is a pattern descriptor constant index.

### 11.1 Core and stack

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| NOP | none | none | Do nothing |
| POP | none | `a ->` | Drop the top value |
| DUP | none | `a -> a, a` | Duplicate the top value |
| DUP2 | none | `a, b -> a, b, a, b` | Duplicate two values |
| SWAP | none | `a, b -> b, a` | Swap the top two values |
| ROT3 | none | `a, b, c -> b, c, a` | Rotate three values |

### 11.2 Literals

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| LOAD_NOVA | none | `-> nova` | Push nova |
| LOAD_UNDEF | none | `-> undef` | Push the empty variadic marker |
| LOAD_TRUE | none | `-> true` | Push true |
| LOAD_FALSE | none | `-> false` | Push false |
| LOAD_INT | i64 | `-> int` | Push a small integer |
| LOAD_BIGINT | u32 | `-> int` | Push a big integer constant |
| LOAD_NUM | f64 | `-> num` | Push a floating-point number |
| LOAD_CHAR | u32 | `-> char` | Push a character |
| LOAD_STR | u32 | `-> str` | Push a string constant |
| LOAD_CONST | u32 | `-> value` | Push a generic constant |

### 11.3 Slots and variables

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| DECLARE_LOCAL | slot u16, spec u32, flags u8 | `->` | Create an undefined local |
| DECLARE_GLOBAL | name u32, spec u32, flags u8 | `->` | Create an undefined module global |
| LOAD_LOCAL | slot u16 | `-> value` | Load a local |
| STORE_LOCAL | slot u16 | `value ->` | Store a local with copy |
| LOAD_GLOBAL | name u32 | `-> value` | Load a module global |
| STORE_GLOBAL | name u32 | `value ->` | Store a module global with copy |
| LOAD_CAPTURE | index u16 | `-> value` | Load a closure capture |
| MAKE_CAPTURE | slot u16 | `->` | Capture a local into the current closure |
| LOAD_THIS | none | `-> obj` | Push the current receiver |
| COPY | none | `value -> copy` | Apply value copy semantics |
| CAST_ASSIGN | spec u32 | `value -> value` | Apply an assignment cast |
| CAST_RETURN | spec u32 | `value -> value` | Apply a return cast |
| BOX_ANY | spec u32 | `value -> any` | Box a value with a declared type |
| UNBOX_ANY | none | `any -> value` | Extract the concrete value |

### 11.4 Containers

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| MAKE_ARRAY | count u16 | `v... -> arr` | Build an array |
| MAKE_ARRAY_TYPED | spec u32, count u16 | `v... -> arr` | Build a typed array with casts |
| MAKE_TUPLE | count u16 | `v... -> tup` | Build a tuple |
| MAKE_TUPLE_TYPED | spec u32, count u16 | `v... -> tup` | Build a typed tuple |
| MAKE_MAP | count u16 | `k, v ... -> map` | Build a map from pairs |
| MAKE_MAP_TYPED | spec u32, count u16 | `k, v ... -> map` | Build a typed map |
| MAKE_SET | count u16 | `v... -> set` | Build a set |
| MAKE_SET_TYPED | spec u32, count u16 | `v... -> set` | Build a typed set |
| MAKE_EMPTY_MAP | none | `-> map` | Build an empty map |
| MAKE_EMPTY_SET | none | `-> set` | Build an empty set |
| INDEX_GET | none | `container, index -> value` | Read an index |
| INDEX_SET | none | `container, index, value ->` | Write an index with copy |
| SLICE | none | `container, start, end -> value` | Slice a container |
| SIZE | none | `value -> int` | Compute language size |
| ITER_NEW | none | `iterable -> iterator` | Create an iterator |
| ITER_NEXT | target i32 | `iterator -> value` | Advance or jump when done |

### 11.5 Arithmetic, conversion and comparison

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| ADD | none | `a, b -> value` | Addition with operator dispatch |
| SUB | none | `a, b -> value` | Subtraction with operator dispatch |
| MUL | none | `a, b -> value` | Multiplication with operator dispatch |
| DIV | none | `a, b -> value` | Division with operator dispatch |
| MOD | none | `a, b -> value` | Remainder with operator dispatch |
| NEG | none | `a -> value` | Unary minus with operator dispatch |
| NOT | none | `a -> bool` | Logical not |
| EQ | none | `a, b -> bool` | Equality |
| NEQ | none | `a, b -> bool` | Inequality |
| LT | none | `a, b -> bool` | Less than |
| LE | none | `a, b -> bool` | Less than or equal |
| GT | none | `a, b -> bool` | Greater than |
| GE | none | `a, b -> bool` | Greater than or equal |
| EQ_TYPED | none | `a, b -> bool` | Typed equality |
| NEQ_TYPED | none | `a, b -> bool` | Typed inequality |
| LT_TYPED | none | `a, b -> bool` | Typed less than |
| LE_TYPED | none | `a, b -> bool` | Typed less than or equal |
| GT_TYPED | none | `a, b -> bool` | Typed greater than |
| GE_TYPED | none | `a, b -> bool` | Typed greater than or equal |
| CONCAT_STR | count u16 | `v... -> str` | Convert and concatenate |
| TO_STRING | none | `value -> str` | Language string conversion |
| TYPE_CHECK | spec u32 | `value -> bool` | Runtime `::` check |
| TYPE_CHECK_NOT | spec u32 | `value -> bool` | Runtime `!: ` check |
| IS_NOVA | none | `value -> bool` | Check nova |
| IS_DEFINED | none | `value -> bool` | Check defined |
| IS_WEAK | none | `value -> bool` | Check weak |

### 11.6 Control flow

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| JUMP | target i32 | none | Unconditional jump |
| JUMP_IF_FALSE | target i32 | `value ->` | Jump when false |
| JUMP_IF_TRUE | target i32 | `value ->` | Jump when true |
| JUMP_IF_FALSE_KEEP | target i32 | `value -> value` | Short-circuit false |
| JUMP_IF_TRUE_KEEP | target i32 | `value -> value` | Short-circuit true |
| JUMP_IF_NOVA | target i32 | `value ->` | Jump when nova |
| JUMP_IF_NOT_NOVA | target i32 | `value ->` | Jump when not nova |
| MATCH | pattern u32, target i32 | `subject ->` | Try a pattern and jump on fail |
| RETURN | none | `value ->` | Return a value |
| CHECK_CANCEL | none | none | Raise when the task is cancelled |

### 11.7 Calls

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| CALL | call u32 | `args... -> value` | Static or resolved call |
| CALL_VALUE | call u32 | `callee, args... -> value` | First-class function call |
| CALL_METHOD | call u32 | `receiver, args... -> value` | Instance method call |
| CALL_STATIC | call u32 | `args... -> value` | Static method call |
| CALL_MODULE | call u32 | `args... -> value` | Module function call |
| CALL_NATIVE | call u32 | `receiver, args... -> value` | Native method call |
| CALL_BUILTIN | call u32 | `args... -> value` | Builtin call |
| CALL_TRAIT | call u32 | `receiver, args... -> value` | Trait-qualified call |
| CALL_OPERATOR | call u32 | `receiver, args... -> value` | Explicit operator trait call |
| CALL_EXTERN | call u32 | `args... -> value` | Host extern call |
| CALL_ASYNC | call u32 | `args... -> task` | Lazy async call |
| SPAWN | call u32 | `args... -> task` | Worker task call |
| AWAIT | none | `task -> value` | Run or wait for a task |

### 11.8 Objects, enums and fields

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| CONSTRUCT | type u32, call u32 | `args... -> obj` | Construct a user object |
| NEW_ENUM | enum u32, variant u16 | `-> obj` | Create an enum value |
| LOAD_FIELD | field u32 | `obj -> value` | Load a field |
| STORE_FIELD | field u32 | `obj, value ->` | Store a field with copy |
| LOAD_MEMBER | name u32 | `obj -> value` | Dynamic member load |
| STORE_MEMBER | name u32 | `obj, value ->` | Dynamic member store |
| LOAD_MEMBER_SAFE | name u32 | `obj -> value` | Safe member load |
| LOAD_ENUM_MEMBER | enum u32, variant u16 | `-> obj` | Load an enum variant |
| SET_LOCKS | flags u8 | `obj ->` | Apply const and element locks |

### 11.9 Traits and operator overloading

Trait-qualified and operator calls use `CALL_TRAIT` and `CALL_OPERATOR` from
section 11.7. The arithmetic and comparison opcodes also perform operator
dispatch when an operand is a user object.

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| CHECK_TRAIT | trait u32 | `value -> value` | Runtime trait check |
| TRAIT_CAST | trait u32 | `value -> value` | Runtime trait cast |

### 11.10 Errors

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| MAKE_ERROR | spec u32 | `args... -> error` | Build a catchable error |
| ERROR_PROPERTY | property u8 | `error -> value` | Read an error property |
| THROW | none | `error ->` | Raise an error |
| PROPAGATE | none | `value -> value` | Postfix `?` propagation |
| TRY_BEGIN | catch i32, finally i32 | none | Push an exception handler |
| TRY_END | none | none | Pop an exception handler |
| FINALLY_END | none | none | Finish a finally block |
| RETHROW | none | `error ->` | Rethrow after finally |

### 11.11 References

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| REF_LOCAL | slot u16 | `-> ref` | Reference a local |
| REF_GLOBAL | name u32 | `-> ref` | Reference a global |
| REF_FIELD | field u32 | `obj -> ref` | Reference a field |
| REF_INDEX | none | `container, index -> ref` | Reference an index |
| LOAD_REF | none | `ref -> value` | Read through a reference |
| STORE_REF | none | `ref, value ->` | Write through a reference |

### 11.12 Modules and project

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| IMPORT | module u32, slot u16 | `->` | Import a module into a local |
| IMPORT_WILDCARD | module u32 | `->` | Import exported names |
| LOAD_MODULE_MEMBER | module u32, export u32 | `-> value` | Load a module member |
| LOAD_PROJECT | none | `-> project` | Load the implicit project |
| EXPORT | name u32 | `value ->` | Mark a module export |

### 11.13 Debug and host

| Opcode | Operands | Stack | Semantics |
|---|---|---|---|
| TRACE_EVENT | event u16 | none | Emit a debug trace event |
| HOST_CALL | host u32 | `args... -> value` | Explicit host operation |

The debug trace and host call instructions are optional in production images.

## 12. Compiler lowering

### 12.1 Module compilation

The compiler compiles a module in four passes:

1. Collect declarations into a module symbol table.
2. Resolve imported declarations through the module graph.
3. Resolve types, traits and signatures.
4. Lower statements and expressions.

Declarations are assigned stable IDs from module path and declaration order.
This keeps disassembly and debug output stable.

### 12.2 Literals and interpolation

| Source | Lowering |
|---|---|
| `nova` | LOAD_NOVA |
| `true` / `false` | LOAD_TRUE / LOAD_FALSE |
| integer literal | LOAD_INT or LOAD_BIGINT |
| floating literal | LOAD_NUM |
| string literal | LOAD_STR |
| char literal | LOAD_CHAR |
| `$"text {expr}"` | parts pushed, TO_STRING for expressions, CONCAT_STR |

### 12.3 Declarations and assignment

| Source | Lowering |
|---|---|
| `x: T;` | DECLARE_LOCAL with an undefined value |
| `x: T = value;` | evaluate value, CAST_ASSIGN, COPY, STORE_LOCAL |
| `x := value;` | evaluate value, COPY, STORE_LOCAL |
| `x = value;` | evaluate value, CAST_ASSIGN when annotated, COPY, STORE_LOCAL |
| `object.field = value` | evaluate object and value, COPY, STORE_FIELD |
| `array[index] = value` | evaluate container, index and value, INDEX_SET |
| destructuring declaration | evaluate source, MATCH bindings, COPY into locals |

The `DECLARE_LOCAL` instruction creates an undefined slot with the declared
type, weak flag and const locks. This matches the tree-walker's undefined value
behavior.

### 12.4 Operators

Binary operators lower to the arithmetic opcodes. The opcode handler performs
built-in semantics, then operator trait dispatch for user objects.

Short-circuit boolean operators lower to jumps.

Type comparisons lower to `TYPE_CHECK` or `TYPE_CHECK_NOT`.

The `typed` flag on a binary expression selects the `_TYPED` comparison
opcodes.

### 12.5 Calls

The compiler emits one call instruction per call shape.

| Source | Lowering |
|---|---|
| `fun_name(args)` | CALL with a function call site |
| `value(args)` | CALL_VALUE |
| `object.method(args)` | CALL_METHOD |
| `Type.method(args)` | CALL_STATIC |
| `module.function(args)` | CALL_MODULE |
| `Type.[args]` | CONSTRUCT |
| `arr[int].[args]` | MAKE_ARRAY_TYPED |
| `map[K, V].[...]` | MAKE_MAP_TYPED |
| `set[T].[...]` | MAKE_SET_TYPED |
| `tup[...].[...]` | MAKE_TUPLE_TYPED |
| `str.[value]` | CAST to str |
| `char.[value]` | CAST to char |
| `bool.[value]` | CAST to bool |
| `int.[value]` | CAST to int |
| `num.[value]` | CAST to num |
| `Trait.method(value, args)` | CALL_TRAIT |
| `arr.push(...)` | CALL_NATIVE |
| `print(...)` | CALL_BUILTIN |
| `spawn call(...)` | SPAWN |
| `async call(...)` | CALL_ASYNC |

Default arguments, named arguments, spread arguments and type arguments are
encoded in the call site descriptor. The call instruction consumes the
evaluated argument list.

### 12.6 Pipelines

The pipeline operators are syntax sugar and have no dedicated instruction.

| Source | Lowering |
|---|---|
| `value :> f(args)` | evaluate value, evaluate args, CALL with value first |
| `value :> object.method(args)` | CALL_METHOD with value as receiver |
| `value &> f(args)` | REF target, evaluate args, CALL with the reference first |
| `value &> arr.push(x)` | REF target, CALL_NATIVE |

The argument order is part of the language contract. The compiler must preserve
left-to-right evaluation.

### 12.7 Control flow

`if` and `else` lower to condition evaluation and jumps.

`for start >> end` lowers to an initialization, a condition, a body, an
increment and a backward jump. The loop variable is a local. Labels and
break and continue are compile-time jump targets.

`for x >> iterable` lowers to `ITER_NEW`, `ITER_NEXT` and a body. The iterator
variable is bound with `STORE_LOCAL` and the same copy rules as a declaration.

`loop` lowers to a forward body and a backward jump. `loop if condition` adds a
condition at the top.

`break` and `continue` lower to jumps to the matching label targets. A missing
label is a compile error.

### 12.8 Match

A match statement or expression lowers to a sequence of `MATCH` instructions,
one per case. Each `MATCH` carries a pattern descriptor and a failure target.

A pattern descriptor contains:

- Pattern kind: wildcard, binding, literal, range, array, tuple, object.
- Literal or range constants.
- Binding slots.
- Nested patterns.
- Object type ID and field patterns.
- Rest binding slot for sequence patterns.
- Guard expression instructions or a guard code object.

On success, `MATCH` writes bindings into the preallocated slots and continues.
On failure, it jumps to the next case target.

Guards are evaluated after a successful pattern match. A false guard jumps to
the next case.

Exhaustiveness and unreachable cases remain checker concerns. The VM does not
need to repeat them.

### 12.9 User types and enums

A type declaration produces a type table entry with:

- Type ID.
- Name.
- Field layout.
- Constructor signatures.
- Method table.
- Static method table.
- Trait-qualified method table.
- Generic parameter metadata.
- Access level flags.
- Copy behavior.

`Type.[args]` lowers to `CONSTRUCT`. The constructor call uses a call site
descriptor with named argument support.

`Type.method(args)` lowers to `CALL_STATIC`.

`object.method(args)` lowers to `CALL_METHOD`.

Enum declarations produce an enum table entry and variant IDs. Enum member
access lowers to `LOAD_ENUM_MEMBER`.

### 12.10 Traits

Trait declarations produce a trait table entry with:

- Trait ID.
- Name.
- Required properties.
- Required methods and signatures.
- Default method code objects.

Trait satisfaction is a checker concern. At runtime, a trait annotation behaves
like an object with a concrete payload. `CHECK_TRAIT` and `TRAIT_CAST` verify
the contract when a value crosses a dynamic boundary.

Trait-qualified method definitions are stored in the type's trait method table.
Trait-qualified calls use `CALL_TRAIT` with the trait ID and method name.

Default trait methods are ordinary code objects with a receiver. They are
called through the trait method table.

### 12.11 Operator overloading

The arithmetic and comparison opcodes perform operator trait dispatch for user
objects. The dispatch order is:

1. If the left operand is a user object, look up the matching operator trait
   method on the left type.
2. If the left type has a trait-qualified method for the operator trait, use it.
3. If the left operand has no suitable method and the right operand is a user
   object, try the right operand according to the existing right-operand rule.
4. If no overload exists, apply built-in semantics.
5. If no built-in semantics exists, raise the same unsupported operation error
   as the tree-walker.

The `Compare` trait returns an integer. The comparison opcode converts that
integer to a boolean with the same rules as the tree-walker.

### 12.12 Errors

`try` and `catch` lower to protected regions and exception handlers.

`catch problem` binds the thrown error to a local.

`finally` runs on normal completion, on catch completion and on rethrow.

`error(message, details...)` lowers to `MAKE_ERROR` followed by `THROW`.

`fail(kind, message, details...)` lowers to `MAKE_ERROR` without throwing.

Postfix `?` lowers to `PROPAGATE`. If the value is an error, the current
function returns it. Otherwise the concrete value is left on the stack.

Error property access lowers to `ERROR_PROPERTY`.

### 12.13 References

`&name` lowers to `REF_LOCAL` or `REF_GLOBAL`.

`&object.field` lowers to `REF_FIELD`.

`&container[index]` lowers to `REF_INDEX`.

A reference parameter call site marks the parameter as a reference. The caller
emits the matching `REF_` instruction. The callee reads and writes the
reference with `LOAD_REF` and `STORE_REF`.

A reference value cannot be copied into a variable, field or container. The
verifier and runtime reject this.

### 12.14 Modules and project

`use` lowers to `IMPORT` or `IMPORT_WILDCARD`. The compiler resolves the module
path with the existing module loader. Built-in modules, relative modules,
explicit paths and package modules all use the same module ID space.

Module member access lowers to `LOAD_MODULE_MEMBER`.

Export declarations add entries to the module export table.

The implicit `project` binding lowers to `LOAD_PROJECT` when a module uses it.

Module initialization is a code object. The runtime initializes dependencies
first. Import cycles remain an error.

### 12.15 Async and tasks

`async fun` produces a code object with the async flag.

An async call lowers to `CALL_ASYNC`, which creates a lazy task.

`spawn call(...)` lowers to `SPAWN`, which creates a worker task.

`await task` lowers to `AWAIT`.

Top-level await uses the same instruction.

The VM does not suspend a task at arbitrary expression boundaries. This matches
the current language model. A future coroutine model would need a new bytecode
version and a new task state machine.

### 12.16 Const macros

`const` declarations are compile-time macros. The parser substitutes the
stored expression at each use site. The compiler sees the expanded expression.
No runtime global is created for a const.

### 12.17 Feature map

| Language area | Main instructions |
|---|---|
| Literals | LOAD_NOVA, LOAD_INT, LOAD_NUM, LOAD_STR, LOAD_CHAR |
| Interpolation | TO_STRING, CONCAT_STR |
| Variables | DECLARE_LOCAL, LOAD_LOCAL, STORE_LOCAL, CAST_ASSIGN, COPY |
| Globals | DECLARE_GLOBAL, LOAD_GLOBAL, STORE_GLOBAL |
| Arrays and tuples | MAKE_ARRAY, MAKE_TUPLE, INDEX_GET, INDEX_SET, SLICE |
| Maps and sets | MAKE_MAP, MAKE_SET, INDEX_GET, INDEX_SET |
| Strings and chars | LOAD_CHAR, INDEX_GET, SLICE, TO_STRING, CALL_NATIVE |
| Arithmetic | ADD, SUB, MUL, DIV, MOD, NEG |
| Comparison | EQ, NEQ, LT, LE, GT, GE and typed variants |
| Logic | JUMP_IF_FALSE_KEEP, JUMP_IF_TRUE_KEEP, NOT |
| Pipelines | CALL, CALL_METHOD, CALL_NATIVE, REF_* |
| Safe access | JUMP_IF_NOVA, LOAD_MEMBER_SAFE |
| Coalesce | JUMP_IF_NOT_NOVA |
| Functions | CALL, CALL_VALUE, MAKE_CAPTURE, RETURN |
| Overloads | CALL with a call site descriptor |
| Defaults and named args | Call site argument layout |
| Variadics and spread | Call site spread positions and argument binder |
| User types | CONSTRUCT, LOAD_FIELD, STORE_FIELD, CALL_METHOD |
| Static methods | CALL_STATIC |
| Enums | NEW_ENUM, LOAD_ENUM_MEMBER |
| Traits | CHECK_TRAIT, TRAIT_CAST, CALL_TRAIT |
| Operator overloading | ADD, SUB, MUL, DIV, MOD, NEG, comparisons |
| Match | MATCH with pattern descriptors |
| Errors | MAKE_ERROR, THROW, PROPAGATE, TRY_BEGIN, TRY_END |
| References | REF_LOCAL, REF_GLOBAL, REF_FIELD, REF_INDEX, LOAD_REF, STORE_REF |
| Modules | IMPORT, IMPORT_WILDCARD, LOAD_MODULE_MEMBER, EXPORT |
| Project | LOAD_PROJECT |
| Async | CALL_ASYNC, SPAWN, AWAIT |
| Builtins | CALL_BUILTIN |
| Native methods | CALL_NATIVE |
| Externs | CALL_EXTERN |
| Debug | Source span table, TRACE_EVENT |

## 13. Runtime semantics

### 13.1 Function calls

A call performs these steps:

1. Resolve the callee.
2. Evaluate or collect arguments in source order.
3. Bind named and spread arguments.
4. Select an overload.
5. Create a frame.
6. Bind parameters with casts and copies.
7. Fill default arguments in the callee frame.
8. Execute the code object.
9. Apply the return cast.
10. Copy the return value.
11. Pop the frame.

### 13.2 Overload resolution

The runtime overload scorer must match the tree-walker. It scores:

- Exact argument count.
- Exact type matches.
- Assignable type matches.
- Variadic matches.
- Explicit type arguments.
- Default argument matches.

The compiler can emit a direct call when the checker has resolved an overload
and all argument types are concrete. It must emit an overload set call when any
argument has type `any`, a union or a dynamic function value.

### 13.3 Method dispatch

Instance method dispatch searches the concrete type method table. Trait
annotations expose only the trait contract at compile time, but the runtime
payload remains the concrete object. Trait-qualified methods are searched in
the trait method table before unqualified methods when a trait-qualified call
is used.

Ambiguous unqualified methods across traits raise the same runtime error as the
tree-walker.

### 13.4 Field access

Concrete field access uses a resolved field ID. Dynamic member access uses a
name ID and the runtime member table. Access control is checked by the
compiler for static access and by the runtime for dynamic access.

### 13.5 Indexing and slicing

Array indexing accepts negative indexes and checks bounds. Map indexing inserts
or replaces. String indexing returns a character. String slicing returns a
string. Tuple indexing returns an element. Index assignment follows the same
locks as the tree-walker.

### 13.6 Builtins and native methods

Builtins and native methods are host functions behind a stable ID table. The VM
passes values and receives values or errors. The host function must not see VM
stack layout.

A native method value form copies its receiver. A reference form mutates the
receiver and returns the reference or a value as documented.

### 13.7 Error unwinding

Error unwinding restores the operand stack and local slot watermark for each
handler. Finally blocks run in the correct order. If a finally block throws,
the new error replaces the original error and the original error is attached
as a cause when the language supports it.

### 13.8 Module initialization

Module initialization is depth first. A module is marked initializing before
its code runs. A cycle is an error. A module is marked initialized after its
code completes. Imports after that return the cached module value.

### 13.9 Task lifecycle

A lazy task starts in the pending state. `AWAIT` moves it to running and runs
it on the current thread. A spawned task moves to running on a worker. A task
that completes stores its result. A task that fails stores an error. A task
that is cancelled stores a cancellation error. `wait`, `cancel` and
`task_status` read the same states as the tree-walker.

### 13.10 REPL

The REPL compiles each cell into a module init fragment. Globals, types,
traits, functions and modules persist in a session object. The VM keeps the
global store and module table alive between cells. A cell can reference names
defined in earlier cells. A failed cell does not commit partial declarations
unless the language explicitly supports it.

## 14. Verification and runtime guards

The verifier catches malformed bytecode. The runtime still needs guards for
valid but dynamically failing programs:

- Index out of bounds.
- Negative index normalization.
- Division by zero.
- Invalid cast.
- Invalid type comparison.
- Undefined value use.
- Const and element lock violation.
- Module mutation.
- Reference escaping its frame.
- Task cancellation.
- Stack and frame limits.
- Instruction budget.

## 15. Debug metadata

Every code object exposes:

- Source file.
- Function name.
- Parameter names.
- Local names and slots.
- Source span per instruction.
- Instruction boundaries.
- Exception ranges.
- Breakpointable instruction offsets.

The debugger can pause at an instruction boundary, inspect locals, inspect the
operand stack, step into, step over and step out. The VM must not optimize
away source spans in debug builds.

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

## Appendix A: Frame layout

A frame contains:

- Code object.
- Instruction pointer.
- Local slot base.
- Operand stack base.
- Operand stack top.
- Closure.
- Module.
- Receiver.
- Current source span.
- Exception handler stack.
- Return destination.
- Reference cleanup list.
- Task.
- Debug state.

The local array is a contiguous slot region. The operand stack is a contiguous
value region. The compiler computes the maximum operand depth for each code
object.

## Appendix B: Instruction encoding examples

A simple addition function:

```po
fun add(a: int, b: int): int >> a + b;
```

Possible disassembly:

```text
code add(a: int, b: int): int
  0000  LOAD_LOCAL       0
  0003  LOAD_LOCAL       1
  0006  ADD
  0007  CAST_RETURN      0
  0011  RETURN
```

A method call:

```text
CALL_METHOD call_site=4
```

A match case:

```text
MATCH pattern=2 fail=0042
```

## Appendix C: Feature inventory

| Feature | Status | VM coverage |
|---|---|---|
| nova, bool, int, num, str, char | implemented | literal and arithmetic opcodes |
| arrays, tuples, maps, sets | implemented | container opcodes |
| indexing, slicing, negative indexes | implemented | INDEX_GET, SLICE |
| string and char access | implemented | INDEX_GET, ITER, CALL_NATIVE |
| typed, weak and const declarations | implemented | DECLARE_LOCAL, CAST_ASSIGN, SET_LOCKS |
| copy semantics | implemented | COPY and copy-on-write |
| functions, lambdas, closures | implemented | CALL, CALL_VALUE, MAKE_CAPTURE |
| generics and type arguments | implemented | call site type arguments |
| overloads, defaults, named args | implemented | call site descriptors |
| variadics and spread | implemented | call site spread positions |
| if, else, for, for-each, loop | implemented | jumps, ITER_NEW, ITER_NEXT |
| break and continue labels | implemented | compile-time jumps |
| match patterns and guards | implemented | MATCH descriptors |
| user types, constructors, methods | implemented | CONSTRUCT, CALL_METHOD |
| static methods and enums | implemented | CALL_STATIC, NEW_ENUM |
| access control and locks | implemented | field flags, SET_LOCKS |
| traits and default methods | implemented | CHECK_TRAIT, CALL_TRAIT |
| operator overloading | implemented | ADD, SUB, MUL, DIV, MOD, NEG, comparisons |
| errors and try/catch/finally | implemented | MAKE_ERROR, THROW, TRY_* |
| postfix error propagation | implemented | PROPAGATE |
| references and reference pipelines | implemented | REF_* and LOAD_REF/STORE_REF |
| modules, imports and exports | implemented | IMPORT, LOAD_MODULE_MEMBER, EXPORT |
| project configuration | implemented | LOAD_PROJECT |
| packages and lock file | implemented | module loader integration |
| async and await | implemented | CALL_ASYNC, AWAIT |
| spawn, wait, cancel, status | implemented | SPAWN, CALL_BUILTIN |
| extern functions | implemented | CALL_EXTERN |
| file I/O | implemented | CALL_BUILTIN and HOST_CALL |
| native methods | implemented | CALL_NATIVE |
| builtins | implemented | CALL_BUILTIN |
| REPL and top-level await | implemented | module init fragments |
| LSP parser, checker and diagnostics | implemented | unchanged frontend |

## Appendix D: Runtime error catalog

The VM must preserve these error families:

- Syntax and parse errors are frontend only.
- Type errors are checker errors.
- Runtime type mismatch.
- Undefined reference.
- Index out of range.
- Division by zero.
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

Every runtime error carries a source span and a frame list. The VM must format
them with the same wording as the tree-walker.

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
