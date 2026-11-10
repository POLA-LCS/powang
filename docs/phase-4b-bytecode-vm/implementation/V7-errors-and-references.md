# V7: Errors and References

Purpose: deliver error values, try, catch and finally, error frames and source positions, postfix question mark propagation, reference expressions, reference parameters, reference pipelines and reference lifetime checks on the bytecode VM.

## Objective

At the end of V7 the VM executes the full error model and the full reference model. Errors are real values built from the same `PowangError` objects as the tree walker. `error(...)` raises, `fail(...)` returns an error value, `catch` binds an error value, `finally` runs on every exit path, and postfix `?` returns an error value from the enclosing function.

References are explicit values with a short lifetime. `&name`, `&object.field` and `&array[index]` create a reference. A `&T` parameter receives a reference and writes through it. A `&>` pipeline passes a reference to a function or native method. A reference cannot be stored in a variable, field or container. A reference cannot outlive the frame that created it.

Error text and source positions are the acceptance bar. The VM must reuse the existing error constructors, the existing frame attachment and the existing property access helper.

Semantic reference: `docs/phase-4b-bytecode-vm/01-architecture-and-execution.md` section 7.7, `docs/phase-4b-bytecode-vm/02-values-heap-and-frames.md` section 9.12, `docs/phase-4b-bytecode-vm/04-compiler-lowering.md` sections 12.12 and 12.13, and `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` section 13.7.

## Prerequisites

- V6 is `gate green`. Modules, project and externs work.
- The V6 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v6 --fail-fast
```

- The baseline suite is green.

Contract surfaces this phase depends on:

- `src/vm/image.py`: `ExceptionEntry`, `CodeObject.exception_table`, `Constant` kinds for error specs.
- `src/vm/frames.py`: `HandlerEntry`, `VMFrame.handlers`, frame IDs.
- `src/vm/errors.py`: error construction, unwinding and frame attachment.
- `src/vm/values.py`: reference constructors, reference lifetime checks, `copy_for_task` reference rejection.
- `src/runtime.py`: `getErrorProperty`, `_attach_frames`, `powang_error_with_position`, `checkFunctionArguments` reference branch, `copy_for_task`.
- `src/error.py`: `PowangError`, `powang_error_format`, `powang_error_identifier_not_found`, `powang_throw`.

## Deliverables

### By file

| File | Work in V7 |
|---|---|
| `src/vm/compiler.py` | `error` and `fail` lowering, error property access, try, catch and finally lowering, return inside protected regions, postfix `?`, reference expressions, reference parameters, reference pipelines, lifetime markers |
| `src/vm/interpreter.py` | Handlers for `MAKE_ERROR`, `ERROR_PROPERTY`, `THROW`, `PROPAGATE`, `TRY_BEGIN`, `TRY_END`, `FINALLY_END`, `RETHROW`, `REF_LOCAL`, `REF_GLOBAL`, `REF_FIELD`, `REF_INDEX`, `LOAD_REF`, `STORE_REF` |
| `src/vm/frames.py` | Handler state machine, pending error and pending return, local watermark restore, frame IDs and live frame set |
| `src/vm/errors.py` | `make_error_value`, `throw_error`, `unwrap_error`, `attach_frames`, `propagate_return`, `resume_handler` |
| `src/vm/values.py` | `make_reference`, `reference_target`, `check_reference_live`, `store_rejects_reference`, reference constructors for local, global, field and index |
| `src/vm/dispatch.py` | Reference parameter binding, reference argument type check, reference forwarding rules |
| `src/vm/tests/test_errors.py` | `error`, `fail`, properties, throw and catch |
| `src/vm/tests/test_finally.py` | Normal, catch, return, throw and nested finally order |
| `src/vm/tests/test_propagate.py` | Postfix `?` and error union returns |
| `src/vm/tests/test_references.py` | Reference expressions, parameters, field and index references |
| `src/vm/tests/test_reference_pipelines.py` | `&>` pipelines to functions and native methods |
| `src/vm/tests/test_reference_lifetime.py` | Escape and storage rejection |
| `src/vm/tests/golden/` | V7 golden disassembly snapshots |
| `src/vm/tests/corpus/v7/` | V7 differential corpus |
| `tests/test_vm_errors.py` | End to end VM engine test for errors and references |

### By language feature

| Feature | Required behavior |
|---|---|
| `error(message, details...)` | `MAKE_ERROR` with kind `USER`, `where` `builtin: error`, then `THROW` |
| `fail(kind, message, details...)` | `MAKE_ERROR` with the given kind, `where` `builtin: fail`, no throw |
| Error property | `kind`, `message`, `details`, `where`, `line`, `column`, `cause`, `frames` |
| `try` and `catch` | Catch binds the error value to a local |
| `finally` | Runs on normal completion, catch completion, return and rethrow |
| Nested try | Innermost handler wins, outer finally still runs |
| Error frames | One `Frame` per active call, rendered in the same order |
| Error position | Line and column from the current instruction span |
| Postfix `?` | Returns the error value from the current function, leaves a non error value |
| `&name` | `REF_LOCAL` or `REF_GLOBAL` |
| `&object.field` | `REF_FIELD` |
| `&array[index]` | `REF_INDEX` |
| Reference parameter | `&T` parameter binds a `PowangReference`, reads and writes go through it |
| Reference pipeline | `target &> f(args)` passes the reference as the first argument |
| Reference lifetime | A reference is valid only while its creating frame is live |
| Reference storage | References cannot be stored in variables, fields or containers |

## Task checklist

- [ ] Add error values and `MAKE_ERROR`.
- [ ] Add `THROW` and `ERROR_PROPERTY`.
- [ ] Add `TRY_BEGIN` and the handler state machine.
- [ ] Add catch lowering.
- [ ] Add finally lowering and return through finally.
- [ ] Add `RETHROW` and the pending error path.
- [ ] Add error frame attachment and source position.
- [ ] Add `PROPAGATE` and error union returns.
- [ ] Add `REF_LOCAL` and `REF_GLOBAL`.
- [ ] Add `REF_FIELD` and `REF_INDEX`.
- [ ] Add `LOAD_REF` and `STORE_REF`.
- [ ] Add reference parameter binding and forwarding.
- [ ] Add `&>` reference pipelines.
- [ ] Add reference lifetime checks and storage rejection.
- [ ] Add V7 unit tests, corpus, golden snapshots and the error engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `error("boom", detail)` | `LOAD_STR "boom"`, evaluate `detail`, `MAKE_ERROR error_spec`, `THROW` |
| `fail("VALUE", "negative", detail)` | `LOAD_STR "VALUE"`, `LOAD_STR "negative"`, evaluate `detail`, `MAKE_ERROR error_spec` |
| `problem.kind` | evaluate `problem`, `ERROR_PROPERTY 0` |
| `problem.message` | `ERROR_PROPERTY 1` |
| `problem.details` | `ERROR_PROPERTY 2` |
| `problem.where` | `ERROR_PROPERTY 3` |
| `problem.line` | `ERROR_PROPERTY 4` |
| `problem.column` | `ERROR_PROPERTY 5` |
| `problem.cause` | `ERROR_PROPERTY 6` |
| `problem.frames` | `ERROR_PROPERTY 7` |
| `try { A } catch problem { B }` | `TRY_BEGIN catch_label, -1`, lower `A`, `TRY_END`, `JUMP end`, place `catch_label`, `STORE_LOCAL problem_slot`, lower `B`, place `end` |
| `try { A } finally { F }` | `TRY_BEGIN -1, finally_label`, lower `A`, `JUMP finally_label`, place `finally_label`, lower `F`, `FINALLY_END` |
| `try { A } catch problem { B } finally { F }` | `TRY_BEGIN catch_label, finally_label`, lower `A`, `JUMP finally_label`, place `catch_label`, `STORE_LOCAL problem_slot`, lower `B`, `JUMP finally_label`, place `finally_label`, lower `F`, `FINALLY_END` |
| `return value` inside a try with a finally | evaluate `value`, `CAST_RETURN spec`, `RETURN`. The `RETURN` handler redirects to the finally and resumes after `FINALLY_END` |
| `error_value?` | evaluate `error_value`, `PROPAGATE` |
| `&name` local | `REF_LOCAL slot` |
| `&name` global | `REF_GLOBAL name` |
| `&object.field` | evaluate `object`, `REF_FIELD field_const` |
| `&array[index]` | evaluate `array`, evaluate `index`, `REF_INDEX` |
| `value = reference` in a reference parameter | `LOAD_REF` when the value is needed, `STORE_REF` when writing through |
| `fun increment(value: &int)` | parameter metadata `reference=true`, `target_type=int`. Call site evaluates `&counter` with `REF_LOCAL` |
| `values[0] &> add_ten` | evaluate `values`, `LOAD_INT 0`, `REF_INDEX`, `CALL call_site` with the reference first |
| `object.field &> increment` | evaluate `object`, `REF_FIELD field_const`, `CALL call_site` |
| `values &> arr.push(3)` | evaluate `values`, `REF_LOCAL` or `REF_INDEX`, evaluate `3`, `CALL_NATIVE call_site` |

`MAKE_ERROR error_spec` uses a constant descriptor with this JSON shape:

```json
{
  "kind": "error",
  "error_kind": "USER",
  "where": "builtin: error",
  "raise": false,
  "message_index": 0,
  "detail_start": 1
}
```

`error(...)` sets `raise` true and `THROW` follows. `fail(...)` sets `raise` false. The handler builds `PowangErrorValue.from_error(powang_error_format(kind, where, message, details))`.

## Runtime semantics notes

### Error values

- `MAKE_ERROR spec` pops the message and detail values, checks that every value is a `PowangString` with the same `powang_error_type_match` errors as `builtin_error` and `builtin_fail`, builds a `PowangError`, wraps it with `PowangErrorValue.from_error` and pushes the value.
- The error spec `where` is `builtin: error` for `error` and `builtin: fail` for `fail`. This is part of the observable error text.
- `ERROR_PROPERTY property` calls `src.runtime.getErrorProperty(where, error_value, property_name)`. The property ID to name mapping is fixed: `0` kind, `1` message, `2` details, `3` where, `4` line, `5` column, `6` cause, `7` frames.
- `THROW` requires a `PowangErrorValue`. It calls `src.vm.errors.throw_error(error_value)`, which attaches the current source position with `powang_error_with_position`, attaches frames with `src.runtime.attach_frames`, and raises the inner `PowangError`.
- A caught error is the same `PowangErrorValue` that was thrown. `catch problem` binds it with `STORE_LOCAL`.
- An error value that is returned or propagated is not raised. The caller decides whether to raise it.

### Error frames and positions

- `state.call_frames` contains one `Frame` per active VM call. The VM pushes a frame on entry and pops it in a `finally` block. Method frames use `Type.method` as the frame name.
- `attach_frames(error)` is the public wrapper around `_attach_frames`. It reverses `state.call_frames` so the innermost frame appears first, matching the tree walker.
- The source position comes from the current instruction span. `powang_error_with_position(error, span.start_line, span.start_column)` sets line and column when the error has none. An error that already has a line keeps it.
- The `ln: N |` prefix is produced by `PowangError.render_text`. The VM must not add a second prefix.

### Handler stack

Every frame has a handler stack of `HandlerEntry` values. A handler entry has:

- `start_ip` and `end_ip` for the protected region.
- `catch_ip`: catch target or `-1`.
- `finally_ip`: finally target or `-1`.
- `resume_ip`: instruction after the protected construct.
- `stack_depth` and `local_watermark`.
- `kind`: `catch` or `finally`.
- `state`: `active`, `catching`, `finally` or `done`.
- `pending_error` and `pending_return`.

`TRY_BEGIN catch_ip, finally_ip` pushes a handler with the current stack depth, local watermark and `state="active"`. The compiler sets `start_ip` to the instruction after `TRY_BEGIN` and `end_ip` to the `JUMP` or `TRY_END` that leaves the protected region.

`THROW` uses this algorithm in the current frame:

1. Find the innermost handler with a protected range that contains the current IP and `state` in `active` or `catching`.
2. Restore the operand stack to `stack_depth`.
3. Reset locals above `local_watermark` to undefined.
4. If `finally_ip >= 0`, store the error in `pending_error`, set `state="finally"` and jump to `finally_ip`.
5. Else if `state=="active"` and `catch_ip >= 0`, set `state="catching"`, jump to `catch_ip` and push the error value.
6. Else mark the handler `done`, pop it and continue with the next outer handler.
7. If no handler remains, unwind the frame and rethrow in the caller.

`RETURN` uses this algorithm:

1. Find the innermost `active` handler with `finally_ip >= 0` covering the current IP.
2. Store the return value in `pending_return`, set `state="finally"`, jump to `finally_ip`.
3. If no such handler exists, apply the return cast, copy the value and pop the frame.

`FINALLY_END` does:

1. If `pending_error` is set, clear it and rethrow through the same unwinder.
2. If `pending_return` is set, apply the return cast, copy the value and pop the frame.
3. Else mark the handler `done`, pop it and jump to `resume_ip`.

`RETHROW` pops an error value and raises it. A finally body that wants to rethrow the pending error loads it from the handler's hidden pending error slot and executes `RETHROW`. A throw inside a finally replaces the pending error and attaches the old error as `cause` when the language supports it.

A handler in `finally` state is skipped by the `THROW` search, so an error in a finally body goes to the next outer handler or to the caller.

### Postfix question mark

- `PROPAGATE` peeks at the top value. When it is a `PowangErrorValue`, it performs a return of that error value from the current function. When it is not an error value, it leaves the value on the stack.
- The current function must have an error union return type. The checker guarantees this. At runtime, `PROPAGATE` on an error value in a non error union function returns the error value anyway and the caller sees a type mismatch, which is the same behavior as the tree walker.
- The returned error value is copied with `copy_value`. Tasks and files keep identity.

### References

- `values.make_reference(kind, frame, target, index, field)` creates the matching reference class:
  - Local and global: `PowangReference(owner_mapping, name, target_type)`.
  - Field: `PowangPropertyReference(owner, name, target_type, private)`.
  - Array index: `PowangElementReference(container, index, target_type)`.
- `REF_LOCAL slot` resolves the slot name from the frame `LocalStore`, checks that the value is not already a reference and not const, then pushes the reference. The reference records `vm_frame_id = frame.id`.
- `REF_GLOBAL name` uses the module global mapping as the owner.
- `REF_FIELD field_const` evaluates the object, checks privacy, checks const and structure locks, then pushes a property reference.
- `REF_INDEX` evaluates the array and index, normalizes a negative index, checks bounds and element locks, then pushes an element reference.
- `LOAD_REF` calls `reference.get()`. `STORE_REF` calls `reference.set(value)` after `copy_value`.
- `LOAD_LOCAL` on a slot that holds a `PowangReference` dereferences it. `STORE_LOCAL` on a reference slot writes through it. This is how a `&T` parameter reads and writes transparently.
- `LOAD_REF` is used when the compiler needs the reference value itself, for example when forwarding a reference in a `&>` pipeline.

### Reference parameters

- A parameter declared `&T` has `reference=true` and `target_type` in the function metadata.
- The binder checks that the argument is a `PowangReference`. A non reference argument raises the same `REFERENCE` error text as `checkFunctionArguments`:
  - `Expected a reference argument`
  - `parameter '<name>' is declared as &<type>`
  - `pass it as &variable`
  - `but <type> was encountered`
- The binder checks `argument.target_type` against the declared target type or `any`. A mismatch raises `Reference type does not match` with the same details.
- The binder stores the reference in the parameter slot without `assignWithChecks`, because `assignWithChecks` rejects references.
- A reference parameter slot is marked in `frame.reference_slots`. `LOAD_LOCAL` and `STORE_LOCAL` use the mark to dereference and write through.

### Reference lifetime

- Every frame has an `id`. `VM.live_frame_ids` holds the IDs of frames on the call stack.
- A reference records the creating frame ID in `vm_frame_id` and the target frame ID in `vm_target_frame_id`.
- `LOAD_REF`, `STORE_REF`, `LOAD_LOCAL` dereference and `STORE_LOCAL` write through check that the target frame ID is still live. A dead target raises:
  - Kind `REFERENCE`
  - Message `Reference escaped its frame`
  - Details: the target name and the creating frame name
- `STORE_LOCAL`, `STORE_GLOBAL`, `STORE_NAME`, `STORE_FIELD`, `STORE_REF`, `INDEX_SET`, `MAKE_ARRAY`, `MAKE_TUPLE`, `MAKE_MAP`, `MAKE_SET` and every call opcode reject a `REF` value with the same `References cannot be stored` error as `assignWithChecks`.
- `src.runtime.copy_for_task` already rejects mutable captures. It must also reject a reference with the same task error. A reference cannot cross a task boundary.
- A reference to a const value is rejected at creation with `Cannot take a reference to a constant`.
- A reference to a reference is rejected with `Cannot take a reference to a reference`.

### Reference pipelines

- `target &> f(args)` lowers the target to the matching `REF_` instruction, then evaluates the arguments left to right, then calls `f` with the reference as the first argument.
- `target &> object.method(args)` uses `CALL_METHOD` with the reference as the receiver for a reference parameter method.
- `target &> arr.push(value)` uses `CALL_NATIVE` with the reference as the receiver. The native method dispatcher sees a `PowangReference` and mutates the target through it.
- The argument order is part of the language contract. The reference comes first, then the evaluated arguments.

### Verifier rules

- `TRY_BEGIN` targets must be instruction boundaries inside the code object or `-1`.
- `ExceptionEntry` ranges must be sorted, non overlapping for one protected region, start before end, and end at or before the instruction count.
- A statically known `REF_*` producer immediately followed by `STORE_LOCAL`, `STORE_GLOBAL`, `STORE_NAME`, `STORE_FIELD`, `STORE_REF`, `INDEX_SET`, `MAKE_ARRAY`, `MAKE_TUPLE`, `MAKE_MAP`, `MAKE_SET` or a call opcode is rejected.
- `PROPAGATE` requires a return type spec that is an error union. In non strict mode this is a warning, in strict mode it is an error.

## Acceptance criteria

1. Every V7 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. `error("boom", "detail")` produces the same stdout, stderr, exit code and text as the tree walker.
3. `fail("VALUE", "negative")` returns an error value with the correct `kind`, `message` and `details`.
4. Every error property matches the tree walker, including `cause` and `frames`.
5. `try` and `catch` bind the error and continue after the catch.
6. A `finally` block runs on normal completion, catch completion, return and rethrow.
7. Nested try blocks run finally blocks in inner to outer order.
8. A return inside a try with a finally returns the saved value after the finally completes.
9. A throw inside a finally replaces the original error and preserves the original as `cause`.
10. Error frames list the same function names and order as the tree walker.
11. Error line and column match the tree walker for the V7 error corpus.
12. Postfix `?` returns the error value and leaves a non error value unchanged.
13. `&name`, `&object.field` and `&array[index]` produce references that read and write the target.
14. A `&T` parameter mutates the caller value.
15. A `&>` pipeline mutates the target through a function or native method.
16. Storing a reference in a variable or a field raises the exact `REFERENCE` error.
17. A reference that outlives its frame raises the exact escape error in the synthetic lifetime test.
18. The V7 corpus reports zero mismatches.
19. `test_references.py` passes with `POWANG_ENGINE=vm`.
20. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_errors -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_finally -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_propagate -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_references -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_reference_pipelines -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_reference_lifetime -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v7 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_references.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_errors.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v7\errors.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v7\errors.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v7/`.

`errors.po`:

```po
fun validate(value: int): int? {
    if value < 0 {
        return fail("VALUE", "negative input", "value=" + (value as str));
    }
    return value;
}

fun double(value: int): int? {
    checked := validate(value)?;
    return checked * 2;
}

println(double(5));
rejected := double(-5);
println(typeof(rejected));
println(rejected.kind);
println(rejected.message);

try {
    error("boom", "first detail", "second detail");
} catch problem {
    println(problem.kind);
    println(problem.message);
    println(size(problem.details));
}
```

`finally.po`:

```po
fun normal(): int {
    try {
        println(1);
    } finally {
        println(2);
    }
    return 3;
}

fun caught(): int {
    try {
        error("boom");
    } catch problem {
        println(problem.kind);
        return 4;
    } finally {
        println(5);
    }
}

fun returned(): int {
    try {
        return 6;
    } finally {
        println(7);
    }
}

println(normal());
println(caught());
println(returned());
```

`nested_finally.po`:

```po
try {
    try {
        error("inner");
    } finally {
        println(1);
    }
} catch problem {
    println(problem.kind);
} finally {
    println(2);
}
```

`throw_in_finally.po`:

```po
try {
    try {
        error("first");
    } finally {
        error("second");
    }
} catch problem {
    println(problem.message);
    if problem.cause { println(problem.cause.message); }
}
```

`propagate.po`:

```po
fun validate(value: int): int? {
    if value < 0 {
        return fail("VALUE", "negative");
    }
    return value;
}

fun double(value: int): int? {
    checked := validate(value)?;
    return checked * 2;
}

println(double(5));
println(double(-5).kind);
```

`error_frames.po`:

```po
fun inner(): int {
    error("inner failure");
}

fun outer(): int {
    return inner();
}

try {
    outer();
} catch problem {
    println(size(problem.frames));
    for frame >> problem.frames {
        println(frame);
    }
}
```

`references.po`:

```po
fun increment(value: &int) {
    value += 1;
}

fun swap(first: &int, second: &int) {
    temporary := first;
    first = second;
    second = temporary;
}

fun doubled(value: &int): int >> value * 2;

counter := 10;
increment(&counter);
println(counter);

left := 1;
right := 2;
swap(&left, &right);
println(left);
println(right);
println(doubled(&counter));
```

`reference_pipeline.po`:

```po
type Counter[+] {
    | value: int;
    fun this.bump() {
        this.value &> increment;
    }
}

fun increment(value: &int) {
    value += 1;
}

fun add_ten(value: &int) {
    value += 10;
}

box := Counter.[3];
box.bump();
println(box.value);

values := [1, 2];
values[0] &> add_ten;
println(values[0]);
```

`reference_property.po`:

```po
type Box[+] {
    | value: int;
}

fun add(value: &int, amount: int) {
    value += amount;
}

box := Box.[5];
add(&box.value, 3);
println(box.value);
```

`error_reference_store.po`:

```po
counter := 1;
reference := &counter;
```

`error_reference_store_field.po`:

```po
type Box[+] {
    | value: int;
}

box := Box.[1];
reference := &box.value;
```

These files must produce the same `references cannot be stored` error text as the tree walker. Some of them may be rejected by the checker before execution. In that case the harness compares stdout, stderr and exit code, and the VM path is never reached. That is still a valid parity check.

The dead frame lifetime case is covered by `src/vm/tests/test_reference_lifetime.py` with a synthetic reference whose frame ID is no longer live. The language has no source level way to return a reference, so a source corpus file cannot exercise it.

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v7_errors` | `src/vm/tests/corpus/v7/errors.po` | `MAKE_ERROR`, `THROW`, `ERROR_PROPERTY`, error spec constant |
| `v7_finally` | `src/vm/tests/corpus/v7/finally.po` | `TRY_BEGIN` catch and finally targets, `JUMP` to finally, `FINALLY_END` |
| `v7_nested_finally` | `src/vm/tests/corpus/v7/nested_finally.po` | Nested `TRY_BEGIN` entries, inner and outer finally targets |
| `v7_propagate` | `src/vm/tests/corpus/v7/propagate.po` | `PROPAGATE` after the call, no hidden throw |
| `v7_references` | `src/vm/tests/corpus/v7/references.po` | `REF_LOCAL`, `LOAD_REF`, `STORE_REF`, reference parameter metadata |
| `v7_reference_pipeline` | `src/vm/tests/corpus/v7/reference_pipeline.po` | `REF_FIELD`, `REF_INDEX`, `CALL` with the reference first |
| `v7_reference_lifetime` | `src/vm/tests/test_reference_lifetime.py` | A synthetic reference to a dead frame is rejected, a live frame reference is accepted |

## Atomic commit plan

1. `vm(v7): add error values and make error`
2. `vm(v7): add throw and error property access`
3. `vm(v7): add try begin and the handler state machine`
4. `vm(v7): add catch lowering`
5. `vm(v7): add finally lowering and return through finally`
6. `vm(v7): add rethrow and nested handlers`
7. `vm(v7): add error frames and source positions`
8. `vm(v7): add postfix propagation`
9. `vm(v7): add reference values and ref local`
10. `vm(v7): add ref global field and index`
11. `vm(v7): add load ref and store ref`
12. `vm(v7): add reference parameter binding`
13. `vm(v7): add reference pipelines`
14. `vm(v7): add reference lifetime and storage checks`
15. `vm(v7): add v7 corpus golden snapshots and error engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Finally order differs | Explicit handler state machine and nested finally corpus | Revert the finally commit and block V7 |
| A return inside try skips finally | `RETURN` redirects to the finally and `FINALLY_END` resumes | Revert the return redirect commit |
| Error frames duplicate or reverse incorrectly | `attach_frames` is shared and the VM pushes one `Frame` per call in a `finally` block | Revert the frame commit |
| Error text gets a VM prefix | Use only existing constructors and compare full stderr | Revert the error commit |
| Reference stores are allowed | Verifier plus runtime rejection in every store opcode and call binder | Revert the reference store commit |
| Reference lifetime check is too strict | A reference is valid while its target frame is on the stack, not only in its own frame | Revert the lifetime commit |
| `PROPAGATE` raises instead of returning | `PROPAGATE` performs a return of the error value, never a throw | Revert the propagate commit |
| A throw in finally loses the original cause | Store the original in `pending_error` and attach it as `cause` when the new error is built | Revert the finally error commit |

## Exit gate

V7 is closed when all of these are true:

- [ ] Every V7 opcode has a handler, a verifier rule and a unit test.
- [ ] The V7 corpus reports zero mismatches.
- [ ] Error text, line, column and frame order match the tree walker.
- [ ] `try`, `catch` and `finally` match the tree walker on every exit path.
- [ ] Postfix `?` matches the tree walker.
- [ ] Reference expressions, parameters and pipelines match the tree walker.
- [ ] Reference storage and lifetime errors match the tree walker.
- [ ] `test_references.py` passes with `POWANG_ENGINE=vm`.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
