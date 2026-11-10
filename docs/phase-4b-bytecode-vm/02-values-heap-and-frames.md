# Values, Heap, and Frames

Purpose: Describe tagged values, heap objects, and frame layout.

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

