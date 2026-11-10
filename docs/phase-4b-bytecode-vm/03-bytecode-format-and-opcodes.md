# Bytecode Format and Opcodes

Purpose: Specify the program image, bytecode encoding, verifier rules, and instruction set.

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

