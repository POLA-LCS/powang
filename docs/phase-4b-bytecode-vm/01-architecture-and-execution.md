# Architecture and Execution

Purpose: Define the VM purpose, scope, design principles, system architecture, and execution model.

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

