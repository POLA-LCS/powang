# Compiler Lowering

Purpose: Describe AST lowering and include encoding examples and the language feature inventory.

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

