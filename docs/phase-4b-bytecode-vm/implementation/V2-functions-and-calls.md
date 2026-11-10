# V2: Functions and Calls

Purpose: deliver function declarations, expression bodies, first class function values, lambdas, closures, captures, default and named arguments, overloads, variadics, explicit type arguments, spread, value pipelines, recursion and stack limits on the bytecode VM.

## Objective

At the end of V2 the VM executes functions as first class values. A function can be declared at module scope, declared inside another function, stored in a variable, passed to another function, returned from a function, captured by a lambda and called through a value. Calls bind arguments with the same overload scoring, named argument mapping, default filling, variadic collection and spread expansion as the tree walker.

Closures are explicit. Every captured local is a cell. A by value closure receives detached snapshots at creation time. A `fun &` closure shares the cell with the enclosing frame. A named recursive lambda always shares its own binding cell so the name resolves to the function value after the store completes.

Semantic reference: `docs/phase-4b-bytecode-vm/01-architecture-and-execution.md` sections 7.3, 7.4, 7.5 and 7.6, `docs/phase-4b-bytecode-vm/04-compiler-lowering.md` sections 12.5, 12.6 and 12.16, and `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` sections 13.1 and 13.2.

## Prerequisites

- V1 is `gate green`. Scalars, locals, globals, operators, control flow, spans and runtime errors work.
- The V1 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v1 --fail-fast
```

- The baseline suite is green.

Contract surfaces this phase depends on:

- `src/vm/image.py`: `CodeObject.flags`, `CodeObject.capture_count`, `CodeObject.parameter_count`, `FunctionInfo`, `CallSite`, `ProgramImage.functions`, `ProgramImage.call_sites`, `ProgramImage.type_specs`.
- `src/vm/builder.py`: `set_parameter_names`, `declare_local`, `finish`, `new_constant`.
- `src/vm/frames.py`: `VMFrame.scope_variables`, `LocalStore`.
- `src/vm/values.py`: `SpreadValue`, `spread_values`, `copy_value`, `stable_key`.
- `src/vm/dispatch.py`: `resolve_call`, `bind_arguments`, `select_overload`.
- `src/runtime.py`: `getFunctionCandidate`, `resolveNamedArguments`, `getUndefinedVariable`, `assignWithChecks`, `areSameObjectType`, `copy_for_task`, `callFunction`.

## Deliverables

### By file

| File | Work in V2 |
|---|---|
| `src/vm/compiler.py` | Function collection pass, parameter slots, function body compilation, lambda compilation, capture analysis, call site descriptors, default metadata, pipeline lowering |
| `src/vm/image.py` | `FunctionInfo` population, `CallSite` population, code object flags, parameter metadata, `vm_defaults` metadata |
| `src/vm/dispatch.py` | `select_overload`, `bind_arguments`, `resolve_call`, `call_value`, argument kind handling, spread expansion, named argument mapping |
| `src/vm/frames.py` | Capture cells, `pending_captures`, `cells`, `frame_id`, `make_capture`, `load_capture` |
| `src/vm/interpreter.py` | `DECLARE_FUNCTION`, `CALL`, `CALL_VALUE`, `MAKE_CAPTURE`, `LOAD_CAPTURE`, `LOAD_THIS`, function `RETURN`, frame limits |
| `src/vm/values.py` | Complete `SpreadValue` and `spread_values`, function value helpers, capture cell wrapper |
| `src/vm/errors.py` | Argument errors, overload errors, recursion errors with the same text as the tree walker |
| `src/runtime.py` | `callFunction` delegation to `VM.call_function`, public `scoreFunctionCandidate` wrapper if needed |
| `src/vm/tests/test_compiler_functions.py` | Function declarations, expression bodies, parameter slots, return casts |
| `src/vm/tests/test_closure.py` | By value capture, `fun &` capture, named recursion, capture across frame exit |
| `src/vm/tests/test_dispatch.py` | Overload scoring, named arguments, defaults, variadics, spread, type arguments |
| `src/vm/tests/test_call_sites.py` | Call site descriptor encoding and decoding |
| `src/vm/tests/test_recursion.py` | Frame limit and recursion error text |
| `src/vm/tests/golden/` | V2 golden disassembly snapshots |
| `src/vm/tests/corpus/v2/` | V2 differential corpus |
| `tests/test_vm_functions.py` | End to end VM engine test for functions and lambdas |

### By language feature

| Feature | Required behavior |
|---|---|
| Function declaration with block body | Named function, implicit `nova` return when no branch returns |
| Function declaration with expression body | `>> expression` compiles to expression, `CAST_RETURN`, `RETURN` |
| Nested function declaration | Function value stored in a local slot and registered in the frame function table |
| First class function value | Pass, store, return and call through `CALL_VALUE` |
| Lambda | Anonymous function value, optional name for recursion |
| By value capture | Captured value is a detached snapshot at closure creation |
| `fun &` capture | Captured value shares a cell with the enclosing frame |
| Captured `this` | Prepared in V2, exercised by methods in V4 |
| Default arguments | Missing parameters filled in source order by the shared binder |
| Named arguments | `name >> value` mapped to slots after positional arguments |
| Overloads | Same scoring function as the tree walker, direct call only when the checker resolved a concrete candidate |
| Variadics | Remaining arguments collected into `PowangArray` with copy semantics |
| Explicit type arguments | `f[int](...)` filters candidates by `len(type_parameters)` |
| Spread | `...values` expands arrays, tuples, sets, maps and strings through `spread_values` |
| Value pipeline `:>` | Lowers to a call with the piped value as the first argument or the receiver |
| Recursion | Direct, mutual and lambda recursion work |
| Stack limit | Frame count limit 900 with the exact tree walker `RECURSION` error |
| Function type metadata | `PowangFunction.function_type` populated from the checker result |

## Task checklist

- [ ] Add the function collection pass, function table entries and parameter slot assignment.
- [ ] Lower block body and expression body function declarations.
- [ ] Add `DECLARE_FUNCTION` and the function value representation.
- [ ] Add `CALL` for named functions and direct resolved calls.
- [ ] Add `CALL_VALUE` for first class function calls.
- [ ] Add capture cells, `MAKE_CAPTURE` and `LOAD_CAPTURE`.
- [ ] Lower lambdas, named lambdas and `fun &` mutable capture.
- [ ] Add default argument binding through the shared binder.
- [ ] Add named argument binding and source order evaluation.
- [ ] Add overload selection using `getFunctionCandidate`.
- [ ] Add variadic parameter binding and spread expansion.
- [ ] Add explicit type argument filtering.
- [ ] Lower value pipelines with `:>`.
- [ ] Add frame limits and the recursion error.
- [ ] Add V2 unit tests, corpus, golden snapshots and the function engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `fun add(a: int, b: int): int >> a + b;` | code object `add` with `LOAD_LOCAL 0`, `LOAD_LOCAL 1`, `ADD`, `CAST_RETURN spec`, `RETURN`. Module init: `DECLARE_FUNCTION function_index`, `STORE_GLOBAL name` |
| `fun f(a: int): int { return a; }` | code object `f` with `LOAD_LOCAL 0`, `CAST_RETURN spec`, `RETURN`. Module init: `DECLARE_FUNCTION function_index`, `STORE_GLOBAL name` |
| `fun f(): nova { println(1); }` | body, `LOAD_NOVA`, `RETURN` |
| nested `fun inner(): int >> 1;` | `DECLARE_FUNCTION function_index`, `STORE_LOCAL slot` inside the enclosing code object |
| `fun(value: int): int >> value * 2` | code object with `LOAD_LOCAL 0`, `LOAD_INT 2`, `MUL`, `RETURN`. Enclosing code: `DECLARE_FUNCTION function_index` |
| lambda with capture `fun(value: int): int >> value + base` | `MAKE_CAPTURE base_slot`, `DECLARE_FUNCTION function_index`, then store to the target slot or pass as an argument |
| `fun &(value: int) { counter += value; }` | `MAKE_CAPTURE counter_slot` in shared mode, `DECLARE_FUNCTION function_index` with `FLAG_MUTABLE_CAPTURE` |
| named lambda `fun fact(n: int): int { ... fact(n - 1) ... }` | allocate `fact` slot first, `MAKE_CAPTURE fact_slot` in shared mode, `DECLARE_FUNCTION function_index`, `STORE_LOCAL fact_slot` |
| `add(1, 2)` direct resolved call | `LOAD_INT 1`, `LOAD_INT 2`, `CALL call_site` |
| `fn(1, 2)` first class call | `LOAD_LOCAL fn_slot`, `LOAD_INT 1`, `LOAD_INT 2`, `CALL_VALUE call_site` |
| `add(1, b >> 2)` | evaluate `1`, evaluate `2`, `CALL call_site` with argument kinds `positional`, `named` and argument names ``, `b` |
| `add(1)` with a default for `b` | evaluate `1`, `CALL call_site` with `positional_count` 1. Binder fills `b` in the callee frame |
| `sum(1, 2, 3)` where `sum(values: int...)` | three values, `CALL call_site` with variadic metadata. Binder creates `PowangArray` from the tail |
| `sum(...values)` | evaluate `values`, `CALL call_site` with argument kind `spread`. Binder calls `spread_values` |
| `identity[int](5)` | `LOAD_INT 5`, `CALL call_site` with `type_argument_count` 1 and the `int` spec |
| `value :> f(a)` | evaluate `value`, evaluate `a`, `CALL call_site` with `value` as the first argument |
| `value :> obj.method(a)` | evaluate `value` as receiver, evaluate `a`, `CALL_METHOD call_site` prepared for V4 |
| `return value;` | evaluate `value`, `CAST_RETURN spec` when annotated, `RETURN` |
| implicit return | `LOAD_NOVA`, `RETURN` |
| closure capture index read | `LOAD_CAPTURE index` |
| `this` inside a method or lambda | `LOAD_THIS` |

The compiler emits `CALL` only when the checker resolved a single concrete candidate and every argument has a concrete static type. Otherwise it emits `CALL` with an overload set descriptor or `CALL_VALUE` when the callee is a dynamic function value. The binder must reproduce the tree walker overload scoring for both cases.

## Runtime semantics notes

### Function values

A VM function value is the existing `PowangFunction` class with these added attributes:

- `code`: the `CodeObject` to execute.
- `vm_image`: the owning `ProgramImage`.
- `vm_name`: the display name used in frames and disassembly.
- `vm_captures`: a tuple of capture cells.
- `vm_defaults`: an optional tuple of code indices for compiled defaults, used from V9.
- `vm_frame_id`: the defining frame id for diagnostics.

The existing attributes `args`, `min_argc`, `return_expr`, `type_parameters`, `variadic`, `variadic_index`, `is_async`, `mutable_capture`, `lambda_name`, `captured_scopes`, `captured_this` and `function_type` keep their tree walker meaning. The VM reads them for overload scoring and binding. The VM does not replace them with a parallel signature model.

`DECLARE_FUNCTION function_index` creates the function value from `ProgramImage.function_info(index)`. It attaches `frame.pending_captures`, clears the pending list and pushes the value. When `FunctionInfo.flags.get("lambda")` is false it also registers the value in `state.scope.functions[-1]` under the declared name. Lambdas are not registered.

### Capture cells

- A frame keeps a `cells` list parallel to its local slots. A cell is created lazily on first capture.
- `MAKE_CAPTURE slot` obtains the cell for the slot, or creates one that holds the current value, and appends it to `frame.pending_captures`.
- `DECLARE_FUNCTION` attaches the pending cells. For a by value closure it snapshots each cell value into a new detached cell. For a `fun &` closure it keeps the shared cell.
- `LOAD_CAPTURE index` reads the cell value. `STORE_LOCAL` on a captured slot writes through the cell. A by reference lambda that assigns to a captured name emits `STORE_LOCAL` for the slot that is bound to the shared cell in the lambda frame.
- A cell outlives its defining frame. When a frame pops, cells keep their current values. This is what makes returned closures work.
- A named lambda always captures its own binding slot in shared mode. The compiler allocates the slot before compiling the lambda body, emits the capture, then emits `DECLARE_FUNCTION` and `STORE_LOCAL`. This is the same effect as `_bind_lambda_name` in the tree walker.
- `FLAG_MUTABLE_CAPTURE` is bit 5 of `CodeObject.flags`. It mirrors `PowangFunction.mutable_capture`.

### Call resolution

`src/vm/dispatch.py` exposes these functions:

```python
def select_overload(candidates, arguments, type_argument_count, where):
    ...

def bind_arguments(where, function, positional, named, spread_positions, frame):
    ...

def resolve_call(vm, call_site, arguments):
    ...
```

`select_overload` uses `src.runtime.getFunctionCandidate` unchanged. Before scoring it filters candidates by `len(candidate.type_parameters) == type_argument_count` when type arguments are present. When the filtered set is empty it raises the same `ARGUMENT` error text as the tree walker:

```text
No generic overload of '<name>' accepts <n> type arguments
```

`bind_arguments` follows the tree walker order:

1. Map positional arguments to fixed parameter slots.
2. Reject too many positional arguments when the function is not variadic.
3. Map named arguments by parameter name.
4. Reject a duplicate binding for one parameter.
5. Reject a named argument that targets a variadic parameter.
6. Reject a missing required argument.
7. Fill defaults through `src.runtime.resolveNamedArguments` in the callee frame.
8. Collect variadic arguments into a `PowangArray` with `src.runtime.copy_for_task` per item.
9. Expand spread arguments with `values.spread_values`.
10. Bind each parameter with `src.runtime.getUndefinedVariable` for the declared type and `src.runtime.assignWithChecks`.
11. Apply `copy_for_task` when the frame belongs to a task.

`resolveNamedArguments` is reused for defaults and named mapping. It evaluates default expressions with `evaluateAstExpression` inside the bridged callee frame. This is the tree walker oracle path. The `compile_defaults` flag on `compile_ast` is reserved for the V9 optimization and must not change observable behavior.

### Spread

`values.spread_values(value)` returns:

- Array: the element list.
- Tuple: the element list.
- Set: the insertion ordered key list.
- Map: a list of `PowangTuple([key, value])` pairs.
- String: a list of `PowangChar` values.
- Any other type: the same `powang_error_type_match` error as the tree walker.

The binder expands a spread argument in place. A string spread produces characters. A map spread produces key value tuples.

### Function calls and return

`VM.call_function(function, arguments, where)` is the single entry for a VM function call. It performs:

1. `bind_arguments` in a new frame.
2. Frame push with the module scope, receiver, closure and task references.
3. Execute the code object.
4. Apply `CAST_RETURN` when the code object carries a return spec.
5. Copy the return value.
6. Pop the frame in a `finally` block.

`src.runtime.callFunction` checks `getattr(candidate, "code", None) is not None` and `get_state().engine == "vm"` before delegating. The tree path is unchanged and remains the oracle for differential tests.

### Recursion and stack limits

- `VMRunOptions.max_frames` defaults to 900.
- Every frame push checks the limit before allocating the frame.
- The error is `powang_error_format("RECURSION", "runtime", "Maximum evaluation depth exceeded", ["depth limit: 900", "check for unbounded or deeply nested recursion"])`.
- Tail calls are not optimized in V2. A recursive call consumes one frame.

### Pipelines

`value :> f(args)` evaluates `value` first, then the arguments left to right, then calls `f` with `value` as the first argument. `value :> obj.method(args)` passes `value` as the receiver. The argument order is part of the language contract. The compiler must preserve left to right evaluation and must record the piped argument in the call site descriptor.

### Method calls in V2

`CALL_METHOD` is registered and the handler exists, but V2 only reaches it through a pipeline on a receiver whose method table is not yet implemented. V4 completes method dispatch. The V2 handler must delegate to `dispatch.call_method` and raise the same `IDENTIFIER` error when the type has no method table.

## Acceptance criteria

1. Every V2 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. A function declared with an expression body returns the expression value with the declared return cast.
3. A function declared with a block body and no return statement returns `nova`.
4. A first class function value can be passed, stored, returned and called through `CALL_VALUE`.
5. A by value closure sees the value at creation time after the enclosing variable changes.
6. A `fun &` closure sees updates to the enclosing variable.
7. A named recursive lambda computes the same result as the tree walker.
8. Default arguments are filled in source order and evaluate in the callee frame.
9. Named arguments evaluate in source order, not parameter order.
10. Overload selection matches the tree walker for exact, assignable, variadic and typed argument cases.
11. `identity[int](5)` selects the generic overload and `identity[bool](5)` raises the same error as the tree walker.
12. Variadic binding creates a `PowangArray` with the same element copies as the tree walker.
13. Spread of arrays, tuples, sets, maps and strings matches the tree walker.
14. Recursion beyond 900 frames raises the exact `RECURSION` error text.
15. The V2 corpus reports zero mismatches.
16. `tests/test_vm_functions.py` passes with `POWANG_ENGINE=vm` and covers every V2 language feature.
17. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_compiler_functions -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_closure -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_dispatch -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_call_sites -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_recursion -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v2 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_functions.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v2\function_add.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v2\function_add.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v2/`.

`function_add.po`:

```po
fun add(a: int, b: int): int >> a + b;

fun block_add(a: int, b: int): int {
    return a + b;
}

println(add(2, 3));
println(block_add(4, 5));
```

`first_class.po`:

```po
fun apply(function: fun[int, int], value: int): int {
    return function(value);
}

fun make_adder(amount: int): fun[int, int] {
    return fun(value: int): int >> value + amount;
}

println(apply(fun(value: int): int >> value * 3, 5));
add_seven := make_adder(7);
println(add_seven(5));
```

`closures.po`:

```po
base := 10;
add_base := fun(value: int): int >> value + base;
base = 20;
println(add_base(1));

counter := 0;
bump := fun &(value: int) {
    counter += value;
};
bump(3);
bump(4);
println(counter);
```

`recursion.po`:

```po
fun factorial(value: int): int {
    if value <= 1 {
        return 1;
    }
    return factorial(value - 1) * value;
}

named := fun fact(value: int): int {
    if value <= 1 {
        return 1;
    }
    return fact(value - 1) * value;
};

println(factorial(6));
println(named(6));
```

`defaults_named.po`:

```po
fun describe(a: int, b: int = 10, c: int = 20): int >> a * 100 + b * 10 + c;

println(describe(1));
println(describe(1, 2));
println(describe(1, 2, 3));
println(describe(a >> 4, c >> 6));
```

`overloads.po`:

```po
fun pick(value: int): int >> 1;
fun pick(value: num): int >> 2;

println(pick(1));
println(pick(1.5));
println(pick(true));
```

`variadics_spread.po`:

```po
fun sum3(a: int, b: int, c: int): int >> a + b + c;

fun forward(values: int...): int >> sum3(...values);

fun forward_named(first: int, values: int...): int >> sum3(first, ...values);

println(forward(1, 2, 3));
println(forward_named(1, 2, 3));
```

`type_arguments.po`:

```po
fun identity[T](value: T): T >> value;

fun choose(value: int): int >> 1;
fun choose[T](value: T): T >> 2;

println(identity[int](5));
println(choose(5));
println(choose[int](5));
```

`pipeline.po`:

```po
fun double(value: int): int >> value * 2;
fun add(left: int, right: int): int >> left + right;

println(5 :> double);
println(5 :> double :> double);
println(5 :> add(3));
```

`recursion_limit.po`:

```po
fun overflow(value: int): int >> overflow(value + 1);
println(overflow(0));
```

The recursion limit file must produce exit code 1 and the exact `RECURSION ERROR` text. The harness compares the full stderr.

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v2_function_add` | `src/vm/tests/corpus/v2/function_add.po` | Two code objects, parameter count 2, `LOAD_LOCAL 0`, `LOAD_LOCAL 1`, `ADD`, `CAST_RETURN`, `RETURN`, `DECLARE_FUNCTION` in module init |
| `v2_first_class` | `src/vm/tests/corpus/v2/first_class.po` | `CALL_VALUE`, `LOAD_LOCAL` for the callee, nested code objects for both lambdas |
| `v2_closures` | `src/vm/tests/corpus/v2/closures.po` | `MAKE_CAPTURE`, `LOAD_CAPTURE`, `FLAG_MUTABLE_CAPTURE` visible in the code flags column |
| `v2_defaults_named` | `src/vm/tests/corpus/v2/defaults_named.po` | Call site argument kind `named`, argument names `a` and `c`, `positional_count` matches the pushed values |
| `v2_variadics_spread` | `src/vm/tests/corpus/v2/variadics_spread.po` | Variadic flag, spread argument kind, `CALL` descriptor with spread position |
| `v2_type_arguments` | `src/vm/tests/corpus/v2/type_arguments.po` | `type_argument_count` 1 and the `int` spec index |
| `v2_pipeline` | `src/vm/tests/corpus/v2/pipeline.po` | Piped value is the first argument, nested pipeline order is left to right |

## Atomic commit plan

1. `vm(v2): add function collection and function table entries`
2. `vm(v2): lower block and expression body function declarations`
3. `vm(v2): add function values and declare function`
4. `vm(v2): add named function calls`
5. `vm(v2): add first class function calls`
6. `vm(v2): add capture cells and closure creation`
7. `vm(v2): lower lambdas and mutable capture`
8. `vm(v2): add default argument binding`
9. `vm(v2): add named argument binding`
10. `vm(v2): add overload selection with shared scoring`
11. `vm(v2): add variadics and spread expansion`
12. `vm(v2): add explicit type argument filtering`
13. `vm(v2): add value pipelines`
14. `vm(v2): add frame limits and recursion errors`
15. `vm(v2): add v2 corpus golden snapshots and function engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Closure capture semantics drift | Cell model is tested for by value, `fun &`, returned closures and named recursion | Revert the capture commit. The function corpus fails and blocks the gate |
| Named argument evaluation order changes | Call site descriptor records source order and the binder maps names after evaluation | Revert the named argument commit |
| Overload scoring diverges | `select_overload` calls `getFunctionCandidate` directly | Revert the dispatch commit and fall back to direct calls for concrete types |
| Defaults evaluate in the wrong scope | Defaults run through `resolveNamedArguments` after the callee frame is pushed | Revert the default commit and require explicit arguments in V2 |
| Variadic copies are shallow | Variadic binding uses `copy_for_task` per item | Revert the variadic commit |
| Recursion limit differs | One frame per call, limit 900, exact error text | Revert the limit commit and keep the tree walker as the only engine for deep recursion |
| `callFunction` delegation changes tree behavior | Delegation requires both `code` and `state.engine == "vm"` | Revert the `src/runtime.py` commit. The tree path is a single conditional |
| Capture cell leaks a frame value | Cells own their value and do not hold a frame reference | Revert the cell commit and return detached snapshots only |

## Exit gate

V2 is closed when all of these are true:

- [ ] Every V2 opcode has a handler, a verifier rule and a unit test.
- [ ] The V2 corpus reports zero mismatches.
- [ ] `tests/test_vm_functions.py` passes with `POWANG_ENGINE=vm`.
- [ ] By value and by reference capture match the tree walker.
- [ ] Defaults, named arguments, overloads, variadics, spread and type arguments match the tree walker.
- [ ] Recursion and the 900 frame limit produce the exact `RECURSION` error.
- [ ] First class functions can be passed, stored, returned and called.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
