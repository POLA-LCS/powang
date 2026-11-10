# V3: Containers, Strings and Native Methods

Purpose: deliver arrays, tuples, maps and sets, indexing, slicing, iteration, copy on write, strings, characters, interpolation, builtins, native methods and file and task builtin IDs on the bytecode VM.

## Objective

At the end of V3 the VM executes the container and text layer of the language. Container literals build the same heap values as the tree walker. Reads and writes go through the same index rules, including negative indexes, bounds errors, map key errors and element locks. Slicing uses the same open bound and negative index rules. Iteration produces the same element order for arrays, tuples, maps, sets and strings.

Copy on write is observable only through value semantics. A copy of an array, map or set can be mutated without changing the original. Nested containers follow the same rule because every read that can lead to mutation returns a shared wrapper and every mutation calls `ensure_unique` before writing.

Strings are code point sequences. Indexing a string returns a `char`, slicing returns a `str`, and iteration yields `char`. Interpolation uses the same display conversion as the tree walker, including the `<type: name>` fallback for user objects.

V3 also owns the container pattern forms of `match` and sequence destructuring. Object and enum patterns land in V4.

Semantic reference: `docs/phase-4b-bytecode-vm/02-values-heap-and-frames.md` sections 8.3 to 8.7 and 9.2 to 9.5, `docs/phase-4b-bytecode-vm/04-compiler-lowering.md` sections 12.2, 12.5, 12.7 and 12.8, and `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` sections 13.5 and 13.6.

## Prerequisites

- V2 is `gate green`. Functions, calls, closures, overloads, variadics and spread work.
- The V2 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v2 --fail-fast
```

- The baseline suite is green.

Contract surfaces this phase depends on:

- `src/vm/image.py`: `CodeObject.constants`, `Constant.kind` for `str`, `char`, `int`, `num`, `spec`, `pattern`, `call` and `descriptor`.
- `src/vm/values.py`: `copy_value`, `SpreadValue`, `spread_values`, `stable_key`, `constant_to_value`.
- `src/vm/interpreter.py`: `VMRunOptions`, `VM.run_code`, frame stack and operand stack.
- `src/vm/host.py`: builtin and native method ID tables.
- `src/runtime.py`: `slice_value`, `getUndefinedVariable`, `assignWithChecks`, `powang_error_index_out_of_range`, `powang_error_key`, `powang_error_not_iterable`, `powang_error_constant_assign`, `powang_error_unsupported_operation`.

## Deliverables

### By file

| File | Work in V3 |
|---|---|
| `src/vm/compiler.py` | Container literal lowering, typed container lowering, index and slice lowering, iteration lowering, destructuring, match statement lowering, string and char literals, interpolation, cast lowering, builtin and native call site lowering |
| `src/vm/values.py` | Full copy on write, `ensure_unique`, `deep_copy_value`, `index_get`, `index_set`, `slice_value`, `size_value`, `to_display_string`, `char_from_codepoint`, `is_iterable`, `VMIterator`, `make_container` helpers |
| `src/vm/interpreter.py` | Handlers for `MAKE_*`, `INDEX_GET`, `INDEX_SET`, `SLICE`, `SIZE`, `ITER_NEW`, `ITER_NEXT`, `CONCAT_STR`, `TO_STRING`, `CAST`, `REVERSE`, `CALL_BUILTIN`, `CALL_NATIVE`, `HOST_CALL`, `DESTRUCTURE`, `MATCH`, `CHECK_CANCEL` at loop edges |
| `src/vm/host.py` | Full builtin table, native method table, file builtins, task builtin IDs, host call IDs |
| `src/vm/image.py` | `PatternDescriptor` serialization for sequence patterns, `CallSite.dispatch` values `builtin` and `native` |
| `src/vm/verifier.py` | `ITER_NEXT` edge rule, variable height rules for `MAKE_*`, `CONCAT_STR`, `MATCH` and `DESTRUCTURE` |
| `src/vm/tests/test_containers.py` | Array, tuple, map and set build, read, write, locks and copy on write |
| `src/vm/tests/test_strings.py` | String and char literals, indexing, slicing, interpolation and display conversion |
| `src/vm/tests/test_iteration.py` | Iteration order and the `ITER_NEXT` jump edge |
| `src/vm/tests/test_native_methods.py` | Native method ID table and value versus reference receiver forms |
| `src/vm/tests/test_builtins.py` | Builtin arity, result and error parity |
| `src/vm/tests/test_destructure.py` | Sequence destructuring and match rest bindings |
| `src/vm/tests/test_match_containers.py` | Wildcard, literal, binding, range, array and tuple patterns |
| `src/vm/tests/golden/` | V3 golden disassembly snapshots |
| `src/vm/tests/corpus/v3/` | V3 differential corpus |
| `tests/test_vm_containers.py` | End to end VM engine test for containers, strings and native methods |

### By language feature

| Feature | Required behavior |
|---|---|
| Array literal | `[1, 2, 3]` builds `PowangArray` with element order preserved |
| Typed array | `arr[int].[1, 2]` casts each element and rejects a wrong element |
| Tuple literal | `.[1, 2]` builds `PowangTuple` |
| Map literal | `["a" >> 1]` builds insertion ordered `PowangMap` |
| Set literal | `[/1, 2, 3]` builds insertion ordered `PowangSet` with unique values |
| Empty containers | Empty array, tuple, map and set literals |
| Index read | Array, tuple, map and string indexing with negative index normalization |
| Index write | Array and map writes with element lock checks and copy semantics |
| Slice | `value[from >> to]` with open bounds, negative bounds and type rules |
| Size | `size(value)` through the `SIZE` opcode and the shared builtin |
| Iteration | `for value >> iterable` over array, tuple, map, set and string |
| Filtered iteration | `for value >> iterable if condition` |
| Copy on write | Aliases mutate independently, nested containers included |
| String literal | `LOAD_STR` with code point semantics |
| Character literal | `LOAD_CHAR` with scalar value validation |
| Interpolation | `$"text {expr}"` with `TO_STRING` and `CONCAT_STR` |
| Explicit cast | `value as T`, `int.[x]`, `num.[x]`, `str.[x]`, `char.[x]`, `bool.[x]` |
| Reverse | Unary `[-]` for int, num, str and array |
| Builtins | `print`, `println`, `format`, `printf`, `input`, `inputf`, `typeof`, `typedeep`, character helpers, `size`, file builtins and task builtin IDs |
| Native methods | Array, map, set, tuple, string, char, file and task methods through `CALL_NATIVE` |
| File builtins | `open`, `close`, `write`, `read` through `CALL_BUILTIN` and `HOST_CALL` |
| Task builtin IDs | `wait`, `cancel`, `task_status` registered. Execution parity is V8 |
| Sequence destructuring | `[a, b] := values` binds a fixed prefix of an array or tuple |
| Sequence patterns | `match` with wildcard, literal, binding, range, array and tuple patterns |
| Match guards | `case pattern if guard >> body` |

## Task checklist

- [ ] Add copy on write storage, `copy_value`, `ensure_unique` and `deep_copy_value`.
- [ ] Lower array and tuple literals, including typed forms and empty forms.
- [ ] Lower map and set literals, including typed forms and empty forms.
- [ ] Add `INDEX_GET` and `INDEX_SET` handlers with negative index and lock rules.
- [ ] Add `SLICE` and `SIZE` handlers using the shared slicing and size helpers.
- [ ] Add `ITER_NEW` and `ITER_NEXT` handlers and the verifier edge rule.
- [ ] Lower `for value >> iterable` and filtered iteration.
- [ ] Lower sequence destructuring and the `DESTRUCTURE` handler.
- [ ] Add string and character literals with code point validation.
- [ ] Add interpolation lowering with `TO_STRING` and `CONCAT_STR`.
- [ ] Add `CAST` and `REVERSE` handlers using the shared cast and unary helpers.
- [ ] Add the full builtin ID table and `CALL_BUILTIN` handler.
- [ ] Add the native method ID table and `CALL_NATIVE` handler.
- [ ] Add file builtin and task builtin IDs and the `HOST_CALL` boundary.
- [ ] Lower sequence `match` patterns and guards and add the `MATCH` handler.
- [ ] Add V3 unit tests, corpus, golden snapshots and the container engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `[1, 2, 3]` | `LOAD_INT 1`, `LOAD_INT 2`, `LOAD_INT 3`, `MAKE_ARRAY 3` |
| `arr[int].[1, 2]` | `LOAD_INT 1`, `LOAD_INT 2`, `MAKE_ARRAY_TYPED spec, 2` |
| `[]` | `MAKE_ARRAY 0` |
| `.[1, 2]` | `LOAD_INT 1`, `LOAD_INT 2`, `MAKE_TUPLE 2` |
| `tup[int, int].[1, 2]` | `LOAD_INT 1`, `LOAD_INT 2`, `MAKE_TUPLE_TYPED spec, 2` |
| `["a" >> 1, "b" >> 2]` | `LOAD_STR "a"`, `LOAD_INT 1`, `LOAD_STR "b"`, `LOAD_INT 2`, `MAKE_MAP 2` |
| `map[str, int].["a" >> 1]` | `LOAD_STR "a"`, `LOAD_INT 1`, `MAKE_MAP_TYPED spec, 1` |
| `map.[]` | `MAKE_EMPTY_MAP` |
| `[/1, 2, 3]` | `LOAD_INT 1`, `LOAD_INT 2`, `LOAD_INT 3`, `MAKE_SET 3` |
| `set[int].[1, 2]` | `LOAD_INT 1`, `LOAD_INT 2`, `MAKE_SET_TYPED spec, 2` |
| `set.[]` | `MAKE_EMPTY_SET` |
| `container[index]` | evaluate `container`, evaluate `index`, `INDEX_GET` |
| `container[index] = value` | evaluate `container`, evaluate `index`, evaluate `value`, `INDEX_SET` |
| `container[from >> to]` | evaluate `container`, evaluate `from` or `LOAD_NOVA`, evaluate `to` or `LOAD_NOVA`, `SLICE` |
| `size(value)` | evaluate `value`, `SIZE` |
| `for value >> iterable { body }` | evaluate `iterable`, `ITER_NEW`, `STORE_LOCAL iter_slot`, place `start`, `LOAD_LOCAL iter_slot`, `ITER_NEXT end`, `STORE_LOCAL value_slot`, body, `JUMP start`, place `end` |
| `for value >> iterable if cond { body }` | same as above, then evaluate `cond`, `JUMP_IF_FALSE continue_label`, body, place `continue_label`, `JUMP start` |
| `for [a, b] >> iterable { body }` | iteration stores the item in `item_slot`, then `LOAD_LOCAL item_slot`, `STORE_LOCAL source_slot`, `DESTRUCTURE descriptor, source_slot`, then body |
| `[a, b] := values` | evaluate `values`, `STORE_LOCAL source_slot`, `DESTRUCTURE descriptor, source_slot`, `STORE_LOCAL a`, `STORE_LOCAL b` |
| `"text"` | `LOAD_STR const_index` |
| `'a'` | `LOAD_CHAR 97` |
| `$"a={value}b"` | `LOAD_STR "a="`, evaluate `value`, `TO_STRING`, `LOAD_STR "b"`, `CONCAT_STR 3` |
| `value as T` | evaluate `value`, `CAST spec` |
| `int.[value]` | evaluate `value`, `CAST int_spec` |
| `[-]value` | evaluate `value`, `REVERSE` |
| `print(args)` | evaluate args left to right, `CALL_BUILTIN call_site` |
| `arr.push(value)` | `LOAD_LOCAL arr`, evaluate `value`, `CALL_NATIVE call_site` with `native_type` `arr` and name `push` |
| `str.chars()` | `LOAD_LOCAL text`, `CALL_NATIVE call_site` with `native_type` `str` and name `chars` |
| `open(path, mode)` | evaluate args, `CALL_BUILTIN call_site` with name `open` |
| `wait(task)` | evaluate `task`, `CALL_BUILTIN call_site` with name `wait` |
| `match subject { case pattern >> body }` | evaluate `subject`, `STORE_LOCAL subject_slot`, place `case_1`, `LOAD_LOCAL subject_slot`, `MATCH pattern, fail_1`, body, `JUMP end`, place `fail_1`, next case, place `end`, `LOAD_NOVA` for statement position |
| `case pattern if guard >> body` | `MATCH pattern, fail_label`, evaluate `guard`, `JUMP_IF_FALSE fail_label`, body |

The `SLICE` instruction uses `nova` for an open bound. The handler calls `src.runtime.slice_value(where, target, start_or_none, end_or_none)`.

## Runtime semantics notes

### Copy on write

- `values.copy_value(value)` returns a value with value semantics.
- Strings and tuples are immutable and are shared by reference.
- Arrays, maps and sets are shared with a `_vm_shared` flag on the wrapper. The wrapper is a new `PowangArray`, `PowangMap` or `PowangSet` that points at the same backing list or dict as the original. Both wrappers are marked shared.
- `values.ensure_unique(value)` checks `_vm_shared`. When set, it replaces that wrapper's backing storage with a shallow clone, clears the flag and returns the wrapper. The alias keeps the old backing storage. This preserves value semantics without a deep copy on every assignment.
- Every read path that can lead to mutation calls `copy_value` on the child value. This includes `INDEX_GET`, `LOAD_FIELD` in V4 and map `get` style native methods. A nested mutation then calls `ensure_unique` on the child.
- `INDEX_SET` calls `ensure_unique(container)` before writing. It checks `elements_locked` first and raises `powang_error_constant_assign` on violation.
- Array length changes through native methods check `structure_locked` and call `ensure_unique`.
- Map and set key equality and hashing use the existing `PowangAny` behavior. Iteration order is insertion order from the Python dict. Never sort keys for output.
- `values.deep_copy_value(value)` exists for boundaries that require a true deep copy, such as `copy` constructors in V4 and task argument capture. V3 uses it only in tests and in the native method value form when the existing method requires a full copy.

### Indexing

- `values.index_get(container, index, where, position)` mirrors `src.runtime.getIndexedValue`:
  - Array and tuple indexes must be `int`. Negative indexes add the length. Out of range raises `powang_error_index_out_of_range` with the same `[0; length)` detail.
  - String indexes must be `int`, normalize negative values and return `PowangChar` for one code point.
  - Map indexes accept any key. A missing key raises `powang_error_key`.
  - A `PowangAny` container is unwrapped first.
- `values.index_set(container, index, value, where, position)` mirrors the tree walker:
  - Array index must be `int`, negative normalized, bounds checked.
  - `elements_locked` raises `powang_error_constant_assign`.
  - Map assignment inserts or replaces.
  - Set index assignment is not supported and raises the same error as the tree walker.
  - The stored value is copied with `copy_value`.

### Slicing

- `SLICE` pops `container`, `start` and `end`. A `nova` bound means open.
- `src.runtime.slice_value(where, target, start, end)` is the single implementation. The VM handler must call it and must not reimplement negative bound normalization.
- String slicing returns `PowangString`. Array slicing returns `PowangArray`. Tuple slicing returns `PowangTuple`.
- A non int bound raises the same `TYPE` error as the tree walker.

### Iteration

- `values.VMIterator` is a Python object with `items`, `index` and a `next()` method. It is not a language value and never escapes the frame.
- `ITER_NEW` accepts `PowangArray`, `PowangTuple`, `PowangMap`, `PowangSet` and `PowangString`. A `PowangAny` is unwrapped first. Anything else raises `powang_error_not_iterable`.
- Map iteration yields `PowangTuple([key, value])` in insertion order. Set iteration yields keys in insertion order. String iteration yields `PowangChar`.
- `ITER_NEXT target` consumes the iterator. On success it pushes the next element. On exhaustion it jumps to `target` and pushes nothing. The verifier models the jump edge at the height before `ITER_NEW` loaded the iterator and the fallthrough at the height with one value.
- The iterator slot is a hidden local. It is initialized once before the loop. The loop body must not overwrite it.
- `CHECK_CANCEL` runs at the loop back edge.

### Strings and characters

- `LOAD_STR` reads a `str` constant and pushes `PowangString`.
- `LOAD_CHAR` reads a u32 code point. Values in the surrogate range `0xD800` to `0xDFFF` and values above `0x10FFFF` are rejected with the same character error as `chr`.
- `values.to_display_string(value)` uses `src.builtins.cast.explicitCastString`. When that returns `None` and the value is a user object, it returns `<type: {type_name}>`. When both fail it returns the empty string. This is the interpolation rule from the tree walker.
- `TO_STRING` pushes `values.to_display_string(value)`.
- `CONCAT_STR count` pops `count` values, converts each with `to_display_string` and joins them in stack order.
- `REVERSE` calls `performUnaryOperation("[-]", value, position)`.

### Builtins

- `src/vm/host.py` builds `BUILTIN_IDS` from `src.builtins.builtins.BUILTINS` with names sorted alphabetically. The ID is stable for one language version.
- `CALL_BUILTIN` reads the call site name, checks `name in BUILTINS`, applies the same arity rule as `_executeCallNode` and calls the function object with the evaluated arguments.
- Arity errors use `powang_error_format("ARGUMENT", "Function call", "too many arguments")` and `"not enought arguments"`. The misspelling is part of the current error text and must be preserved.
- File builtins reuse the existing `src.builtins.file` functions. They keep the existing stream table and error text.
- `wait`, `cancel` and `task_status` reuse `src.builtins.tasks`. They are registered in V3 and become executable in V8 when tasks exist.

### Native methods

- `src/vm/host.py` builds `NATIVE_METHOD_IDS` from `src.builtins.native_methods.NATIVE_METHOD_NAMES` keyed by `(type, method)` with a stable numeric ID.
- `CALL_NATIVE` reads `native_type` and `name`, then calls `src.builtins.native_methods.call_native_method(where, native_type, name, [receiver, *arguments])`.
- A value form receiver is copied with `copy_value` before the call. A reference form receiver is a `PowangReference` and the native method mutates the target. This is the same distinction the tree walker makes in `_is_reference`.
- Native methods that return the receiver return a copied value, not the original wrapper.
- The VM never imports `src.builtins.native_methods.array` or any other native method module directly. All access goes through `call_native_method`.

### Host boundary

- `HOST_CALL host_id` is reserved for host operations that are not language builtins. V3 registers `HOST_CLOCK`, `HOST_SLEEP`, `HOST_STDIN_READ`, `HOST_STDOUT_WRITE` and `HOST_FILE_FLUSH`.
- The host object is held on `VM.host` and is created from `src.vm.host.Host`. The interpreter calls `host.call(host_id, arguments)`.
- Host functions see values, never stack layout. They return a value or raise `PowangError`.

### Match and destructuring

- Pattern descriptors use these `kind` values in V3: `wildcard`, `literal`, `binding`, `range`, `array` and `tuple`.
- A literal pattern compares type and value after unwrapping `PowangAny`. The literal is a constant index, not an AST node.
- A binding pattern copies the subject with `PowangCopyConstruct` and writes it to a preallocated slot.
- A range pattern is inclusive on the left and exclusive on the right. The subject and both bounds must be `int` or `num`, otherwise the same `TYPE` error as `_match_pattern` is raised.
- An array pattern accepts an array or a tuple. A tuple pattern accepts only a tuple. The exact length must match unless a rest binding exists. Rest bindings produce an array for an array subject and a tuple for a tuple subject.
- `MATCH pattern, target` pops the subject. On success it writes bindings and falls through. On failure it jumps to `target`. The subject must be reloaded for the next case.
- Match guards run after bindings. A false guard jumps to the same failure target. Bindings from a failed guard are overwritten by the next case or are not observed after the match.
- A statement position match with no matching case does nothing. The compiler pushes `LOAD_NOVA` only when the match is used as an expression. Expression position match is V4.
- `DESTRUCTURE descriptor, source_slot` reads the source local, writes bindings, then pushes the source value for the statement result. A destructuring declaration binds a fixed prefix. Rest bindings belong to match patterns, where the subject type decides whether the tail becomes an array or a tuple.
- Assignment and declaration of destructured names copy each bound value with `copy_value`.

## Acceptance criteria

1. Every V3 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. Array, tuple, map and set literals produce the same printed value and iteration order as the tree walker.
3. Typed array, tuple, map and set literals reject a wrong element with the same error text as the tree walker.
4. `a := [1, 2]; b := a; b[0] = 9;` leaves `a[0]` equal to 1.
5. A nested container mutation through an alias does not change the original.
6. `container[5]` on a two element array raises the exact `INDEX ERROR` text.
7. `map["missing"]` raises the exact `KEY ERROR` text.
8. String indexing returns a `char`, string slicing returns a `str` and string iteration yields `char`.
9. Open bound slicing and negative bound slicing match the tree walker.
10. Interpolation output matches the tree walker for nova, bool, int, num, str, char, array, map, set, tuple and a user object placeholder.
11. Every builtin registered in `BUILTINS` has an ID and an arity rule that matches the tree walker.
12. Every native method registered in `NATIVE_METHOD_NAMES` has an ID and dispatches through `call_native_method`.
13. Value form native methods do not mutate the original receiver.
14. Reference form native methods mutate the target.
15. Sequence destructuring matches the tree walker.
16. Wildcard, literal, binding, range, array and tuple match patterns match the tree walker, including a failed guard.
17. The V3 corpus reports zero mismatches.
18. `test_characters.py` and `test_slicing.py` pass with `POWANG_ENGINE=vm`.
19. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_containers -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_strings -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_iteration -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_native_methods -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_builtins -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_destructure -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_match_containers -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v3 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_characters.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_slicing.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_containers.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v3\containers.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v3\containers.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v3/`.

`containers.po`:

```po
values := [1, 2, 3];
pair := .[10, 20];
pairs := ["a" >> 1, "b" >> 2];
unique := [/1, 2, 3];

println(values);
println(pair);
println(pairs);
println(unique);
println(values[0]);
println(values[-1]);
println(pair[1]);
println(pairs["b"]);
```

`index_write.po`:

```po
values := [1, 2, 3];
values[1] = 9;
println(values);

pairs := ["a" >> 1];
pairs["b"] = 2;
pairs["a"] = 3;
println(pairs);
println(pairs["a"]);
println(pairs["b"]);
```

`copy_on_write.po`:

```po
original := [1, 2, 3];
alias := original;
alias[0] = 9;
println(original);
println(alias);

nested := [[1, 2], [3, 4]];
nested_alias := nested;
nested_alias[0][0] = 7;
println(nested);
println(nested_alias);
```

`slicing.po`:

```po
text := "abcdef";
numbers := [10, 20, 30, 40];

println(text[>>]);
println(text[2 >>]);
println(text[>> 3]);
println(text[1 >> 4]);
println(text[-3 >>]);
println(text[>> -1]);
println(numbers[1 >> 3]);
println(numbers[>> 2]);
println(numbers[-2 >>]);
```

`iteration.po`:

```po
numbers := [10, 20, 30];
for number >> numbers {
    println(number);
}

for letter >> "abc" {
    println(letter);
}

for pair >> ["a" >> 1, "b" >> 2] {
    println(pair[0]);
    println(pair[1]);
}

for value >> numbers if value > 15 {
    println(value);
}
```

`strings_chars.po`:

```po
text := "powang";
println(text[0]);
println(text[1 >> 3]);
println(text.chars());
println('a');
println(ord('a'));
println(chr(98));
```

`interpolation.po`:

```po
name := "world";
count := 3;
letter := 'x';
numbers := [1, 2];
println($"hello {name}");
println($"count={count} letter={letter}");
println($"numbers={numbers}");
println($"nova={nova}");
```

`builtins.po`:

```po
println(size([1, 2, 3]));
println(typeof(1));
println(typeof("text"));
println(format("{0}/{1}", "a", "b"));
println(typedeep([1, 2]));
```

`native_methods.po`:

```po
values := [3, 1, 2];
copy := values;
copy &> arr.push(4);
println(values);
println(copy);
println(copy &> arr.pop(0));
println(copy);

text := "a,b,c";
println(text.div(","));
println(text.reverse());
println(text.chars());
```

`destructure.po`:

```po
values := [1, 2, 3];
[a, b] := values;
println(a);
println(b);

pair := .[10, 20];
[left, right] := pair;
println(left);
println(right);
```

`match_containers.po`:

```po
values := [1, 2, 3];
match values {
    case [first, ...rest] >> {
        println(first);
        println(size(rest));
    }
    case _ >> println(0);
}

pair := .[10, 20];
match pair {
    case .[a, b] >> println(a + b);
}

nested := [[1, 2], .[3, 4]];
match nested {
    case [[a, b], .[c, d]] >> println(a + b + c + d);
}

value := 15;
match value {
    case -10 >> 0 >> println(0);
    case 0 >> 10 >> println(1);
    case 10 >> 20 >> println(2);
    case _ >> println(3);
}

match [1, 2] {
    case [a, b] if a < b >> println(4);
    case _ >> println(5);
}
```

`error_index.po`:

```po
values := [1, 2];
println(values[5]);
```

`error_key.po`:

```po
pairs := ["a" >> 1];
println(pairs["missing"]);
```

`error_lock.po`:

```po
values: arr[int!] = [1, 2];
values[0] = 9;
```

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v3_containers` | `src/vm/tests/corpus/v3/containers.po` | `MAKE_ARRAY`, `MAKE_TUPLE`, `MAKE_MAP`, `MAKE_SET`, `INDEX_GET`, types of constants |
| `v3_copy_on_write` | `src/vm/tests/corpus/v3/copy_on_write.po` | `COPY` before stores, `INDEX_SET`, no hidden deep copy loop |
| `v3_slicing` | `src/vm/tests/corpus/v3/slicing.po` | `LOAD_NOVA` for open bounds, `SLICE` stack order |
| `v3_iteration` | `src/vm/tests/corpus/v3/iteration.po` | `ITER_NEW`, `ITER_NEXT` target, hidden iterator slot, backward jump |
| `v3_interpolation` | `src/vm/tests/corpus/v3/interpolation.po` | `TO_STRING` before `CONCAT_STR`, part count |
| `v3_native_methods` | `src/vm/tests/corpus/v3/native_methods.po` | `CALL_NATIVE`, `native_type`, native method ID |
| `v3_match_containers` | `src/vm/tests/corpus/v3/match_containers.po` | `MATCH` pattern index, failure target, rest binding slot, guard jump |
| `v3_destructure` | `src/vm/tests/corpus/v3/destructure.po` | `DESTRUCTURE`, source slot, binding slots |

## Atomic commit plan

1. `vm(v3): add copy on write storage helpers`
2. `vm(v3): lower array and tuple literals`
3. `vm(v3): lower map and set literals`
4. `vm(v3): add index get and index set handlers`
5. `vm(v3): add slice and size handlers`
6. `vm(v3): add iteration handlers and verifier edge rule`
7. `vm(v3): lower for each and filtered iteration`
8. `vm(v3): lower sequence destructuring`
9. `vm(v3): add string and character literals`
10. `vm(v3): add interpolation lowering`
11. `vm(v3): add cast and reverse handlers`
12. `vm(v3): add full builtin table and call builtin`
13. `vm(v3): add native method table and call native`
14. `vm(v3): add file and task builtin ids and host calls`
15. `vm(v3): add sequence match patterns and guards`
16. `vm(v3): add v3 corpus golden snapshots and container engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Copy on write breaks alias isolation | Golden copy on write corpus with nested containers, plus unit tests for `ensure_unique` | Revert the copy on write commit and fall back to deep copy at every boundary until fixed. Correctness is preserved, performance is not |
| Copy on write leaks shared storage | Track `_vm_shared` and clear it on clone. Add a test that mutates the original after a copy | Revert the copy on write commit |
| Index error text differs | Use the existing error constructors and compare full stderr | Revert the index handler commit |
| Map iteration order changes | Never sort keys. Rely on Python dict insertion order | Revert the map handler commit |
| String index returns a one character string | `INDEX_GET` on a string always returns `PowangChar`, tested for length, ord and type | Revert the string index commit |
| Native method value form mutates the receiver | `copy_value` before the value form call and a dedicated test | Revert the native method commit |
| Builtin ID table changes when a builtin is added | IDs are sorted by name and pinned by a test snapshot | Revert the host commit and regenerate the snapshot |
| `ITER_NEXT` verifier edge is wrong | Explicit edge model and a test with an empty iterable and a non empty iterable | Revert the iteration commit |
| Match bindings leak from a failed guard | Bindings are written only to case scoped slots and overwritten by the next case | Revert the match commit |

## Exit gate

V3 is closed when all of these are true:

- [ ] Every V3 opcode has a handler, a verifier rule and a unit test.
- [ ] The V3 corpus reports zero mismatches.
- [ ] Copy on write preserves value semantics for arrays, maps, sets and nested containers.
- [ ] Index, slice, key and lock errors match the tree walker exactly.
- [ ] String indexing, slicing, iteration and interpolation match the tree walker.
- [ ] Every builtin and native method has a stable ID and a parity test.
- [ ] Sequence destructuring and sequence match patterns match the tree walker.
- [ ] `test_characters.py` and `test_slicing.py` pass with `POWANG_ENGINE=vm`.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
