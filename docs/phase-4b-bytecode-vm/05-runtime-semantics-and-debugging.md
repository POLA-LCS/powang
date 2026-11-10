# Runtime Semantics and Debugging

Purpose: Describe runtime behavior, dynamic guards, debug metadata, and runtime errors.

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

