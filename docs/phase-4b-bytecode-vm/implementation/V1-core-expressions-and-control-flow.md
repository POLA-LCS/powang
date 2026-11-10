# V1: Core Expressions and Control Flow

Purpose: deliver scalar literals, local and global variables, arithmetic, comparison, logic, blocks, conditionals, loops, break and continue, module returns, source spans and runtime errors on the bytecode VM.

## Objective

At the end of V1 the VM executes the core expression language without any container, function or user type support. The compiler lowers scalar literals, declarations, assignments, operators, `if`, `else`, `loop`, `loop if`, C style `for`, range `for`, labeled `break` and `continue`, and block scoping. The interpreter executes the matching opcode slice with exact tree walker semantics.

Every runtime error produced in this phase carries the same kind, message, line and column as the tree walker. Arithmetic and comparison are not reimplemented. The handlers call the shared runtime helpers that the tree walker already uses. This includes language quirks such as `1 / 0` producing `nova` and mixed weak comparisons producing a boolean.

Semantic reference: `docs/phase-4b-bytecode-vm/01-architecture-and-execution.md` section 7, `docs/phase-4b-bytecode-vm/04-compiler-lowering.md` sections 12.2, 12.3, 12.4 and 12.7, and `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` sections 13 and 14.

## Prerequisites

- V0 is `gate green`. The package skeleton, registry, image codec, builder, verifier, disassembler, engine flag and differential harness exist.
- The baseline suite is green:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

- The V0 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v0 --fail-fast
```

Contract surfaces this phase depends on:

- `src/vm/builder.py`: `Builder.emit`, `new_label`, `place`, `patch`, `new_constant`, `add_span`, `declare_local`, `reserve_local`, `finish`.
- `src/vm/image.py`: `SourceSpan`, `Constant`, `CodeObject`, `ProgramImage`.
- `src/vm/frames.py`: `LocalStore`, `VMFrame`.
- `src/vm/values.py`: `truthy`, `copy_value`, `tag_of`, `nova`, `stable_key`.
- `src/vm/interpreter.py`: `VMRunOptions`, `VM.run_code`.
- `src/vm/verifier.py`: `verify_code`.

## Deliverables

### By file

| File | Work in V1 |
|---|---|
| `src/vm/compiler.py` | Scope manager with block scopes and slot reuse, span helper, literal lowering, declaration lowering, assignment lowering, operator lowering, control flow lowering, module init return |
| `src/vm/interpreter.py` | Dispatch loop for the V1 opcode slice, frame push and pop, span update, runtime error propagation, `CHECK_CANCEL` |
| `src/vm/frames.py` | Slot backed `LocalStore`, block scope entry and exit helpers, `scope_variables` |
| `src/vm/values.py` | Scalar `copy_value`, `truthy`, `spec_type_node`, `box_any`, `unbox_any`, flag bit helpers |
| `src/vm/errors.py` | `raise_vm_error`, `error_with_span`, `span_line_column`, line and column formatting |
| `src/vm/builder.py` | `stack_effect_bound`, block scope helpers if needed by the compiler, span index plumbing |
| `src/vm/verifier.py` | Merge point stack height table, variable height rules for `ROT` and `ROT3` families, local slot range checks |
| `src/vm/tests/test_compiler_core.py` | Literal, declaration, assignment and operator lowering |
| `src/vm/tests/test_control_flow.py` | `if`, `loop`, `for`, `break`, `continue`, labels and block scopes |
| `src/vm/tests/test_interpreter_core.py` | Handler behavior for every V1 opcode |
| `src/vm/tests/test_spans.py` | Span table, line and column, runtime error position |
| `src/vm/tests/golden/` | V1 golden disassembly snapshots |
| `src/vm/tests/corpus/v1/` | V1 differential corpus |
| `tests/test_vm_core.py` | End to end VM engine test for core language behavior |

### By language feature

| Feature | Required behavior |
|---|---|
| Integer literal | `LOAD_INT` for values in signed 64 bit range, `LOAD_BIGINT` beyond it |
| Floating literal | `LOAD_NUM`, including exponent forms |
| Boolean and nova literal | `LOAD_TRUE`, `LOAD_FALSE`, `LOAD_NOVA` |
| Inferred local | `x := value` creates a local with the runtime tag of the value |
| Typed local | `x: T = value` applies `CAST_ASSIGN`, then binds with a copy |
| Undefined typed local | `x: T` creates an undefined value with the declared type and flags |
| Weak and const declarations | Weak and const flags reach `PowangAny.weak` and `PowangAny.const` |
| Global declarations | Same rules at module scope with `DECLARE_*_GLOBAL`, `LOAD_GLOBAL`, `STORE_GLOBAL` |
| Dynamic names | `LOAD_NAME` and `STORE_NAME` for names the compiler cannot resolve to a slot |
| Assignment | Plain, compound (`+=`, `-=`, `*=`, `/=`, `%=`) and typed assignment |
| Arithmetic | `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, unary `NEG` |
| Comparison | `EQ`, `NEQ`, `LT`, `LE`, `GT`, `GE` and the `_TYPED` variants |
| Logic | logical and, logical or and logical not with short circuit jumps |
| Type check | `value :: T` and `value !: T` for built in type specs |
| If and else | `if`, `else if`, `else`, with a declaration in the condition |
| Loop | `loop` and `loop if` with labels |
| C style for | `for init; condition; update { ... }` |
| Range for | `for i >> start >> end` and `for i >> start >> step >> end`, end exclusive |
| Break and continue | Unlabeled and labeled forms, missing label is a compile error |
| Blocks | Lexical block scopes with slot reuse after exit |
| Module return | Module init code object ends in `LOAD_NOVA`, `RETURN` |
| Scalar copy | Scalars copy by value at declaration, assignment, parameter-free return and native value boundaries |
| Source spans | One span index per instruction, 1 based line and column in errors |
| Runtime errors | Undefined name, unsupported operation, invalid weak comparison, invalid prefix operator, type mismatch |

## Task checklist

- [ ] Add the compiler scope manager, span helper and module init frame.
- [ ] Lower scalar literals and big integers.
- [ ] Lower local declarations, typed declarations, inferred declarations and undefined slots.
- [ ] Lower global declarations and global loads and stores.
- [ ] Lower assignment, compound assignment and dynamic name access.
- [ ] Add arithmetic handlers that call the shared `performOperation` helper.
- [ ] Add comparison handlers including the typed variants.
- [ ] Add short circuit logic, `NOT`, `TO_BOOL` and type check opcodes.
- [ ] Lower `if`, `else if` and `else` with block scopes.
- [ ] Lower `loop` and `loop if` with labels.
- [ ] Lower C style and range `for` loops with break and continue targets.
- [ ] Add span based runtime error formatting and line and column propagation.
- [ ] Add V1 unit tests, corpus, golden snapshots and the core engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `x := value` | evaluate `value`, `DECLARE_INFER slot`, `STORE_LOCAL slot` |
| `x: T = value` | evaluate `value`, `CAST_ASSIGN spec`, `DECLARE_TYPED slot, spec`, `STORE_LOCAL slot` |
| `x: T` | `DECLARE_LOCAL slot, spec, flags`, `STORE_LOCAL slot` |
| `x = value` | evaluate `value`, `CAST_ASSIGN spec` when annotated, `STORE_LOCAL slot` |
| `x += value` | `LOAD_LOCAL slot`, evaluate `value`, `ADD`, `CAST_ASSIGN spec` when annotated, `STORE_LOCAL slot` |
| `global := value` at module scope | evaluate `value`, `DECLARE_INFER_GLOBAL name`, `STORE_GLOBAL name` |
| `global: T = value` at module scope | evaluate `value`, `CAST_ASSIGN spec`, `DECLARE_TYPED_GLOBAL name, spec`, `STORE_GLOBAL name` |
| unresolved name read | `LOAD_NAME name` |
| unresolved name write | evaluate `value`, `STORE_NAME name` |
| `a + b` | evaluate `a`, evaluate `b`, `ADD` |
| `a - b` | evaluate `a`, evaluate `b`, `SUB` |
| `a * b` | evaluate `a`, evaluate `b`, `MUL` |
| `a / b` | evaluate `a`, evaluate `b`, `DIV` |
| `a % b` | evaluate `a`, evaluate `b`, `MOD` |
| `-a` | evaluate `a`, `NEG` |
| `!a` | evaluate `a`, `NOT` |
| `a == b` | evaluate `a`, evaluate `b`, `EQ` or `EQ_TYPED` when the checker marks the comparison typed |
| `a != b`, `a < b`, `a <= b`, `a > b`, `a >= b` | matching comparison opcode or typed variant |
| `a && b` | evaluate `a`, `JUMP_IF_FALSE_KEEP end`, `POP`, evaluate `b`, place `end` |
| `a \|\| b` | evaluate `a`, `JUMP_IF_TRUE_KEEP end`, `POP`, evaluate `b`, place `end` |
| `a :: T` | evaluate `a`, `TYPE_CHECK spec` |
| `a :: dynamic_type_value` | evaluate `a`, evaluate `dynamic_type_value`, `TYPE_CHECK_VALUE` |
| `a !: T` | evaluate `a`, `TYPE_CHECK_NOT spec` |
| `a is nova` equivalent internal check | evaluate `a`, `IS_NOVA` |
| `if cond { A } else { B }` | evaluate `cond`, `JUMP_IF_FALSE else_label`, lower `A`, `JUMP end`, place `else_label`, lower `B`, place `end` |
| `if x := value { A }` | evaluate `value`, `DUP`, `STORE_LOCAL slot`, `JUMP_IF_FALSE end`, lower `A`, place `end` |
| `loop { A }` | place `start`, lower `A`, `JUMP start`, place `end` |
| `loop if cond { A }` | place `start`, evaluate `cond`, `JUMP_IF_FALSE end`, lower `A`, `JUMP start`, place `end` |
| `loop if active := cond { A }` | place `start`, evaluate `cond`, `DUP`, `STORE_LOCAL slot`, `JUMP_IF_FALSE end`, lower `A`, `JUMP start`, place `end` |
| `for init; cond; update { A }` | lower `init`, place `cond_label`, evaluate `cond`, `JUMP_IF_FALSE end`, lower `A`, place `continue_label`, lower `update`, `JUMP cond_label`, place `end` |
| `for i >> start >> end { A }` | lower `i := start`, place `cond_label`, `LOAD_LOCAL i`, evaluate `end`, `LT`, `JUMP_IF_FALSE loop_end`, lower `A`, `LOAD_LOCAL i`, `LOAD_INT 1`, `ADD`, `STORE_LOCAL i`, `JUMP cond_label`, place `loop_end` |
| `for i >> start >> step >> end { A }` | same shape with the explicit step expression |
| `break` | `JUMP` to the innermost break label |
| `continue` | `JUMP` to the innermost continue label |
| `break label` | `JUMP` to the matching labeled break target |
| `continue label` | `JUMP` to the matching labeled continue target |
| `{ A }` | no instruction, enter and leave a compile time block scope |
| `return value` inside a function body prepared for V2 | evaluate `value`, `CAST_RETURN spec` when annotated, `RETURN` |
| module init | lower every top level statement, `LOAD_NOVA`, `RETURN` |

Range `for` uses the same comparison and increment rules as the tree walker. The end bound is exclusive. The step defaults to `1` and is added to the loop variable on each iteration.

## Runtime semantics notes

### Shared arithmetic and comparison

- `src/vm/interpreter.py` handlers for `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `EQ`, `NEQ`, `LT`, `LE`, `GT` and `GE` call `src.runtime.performOperation(operator, left, right, typed, position, trait_name)`.
- The operator string is the source operator: `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `<`, `<=`, `>`, `>=`.
- `typed` is true for the `_TYPED` opcode family.
- `position` is the 1 based `(line, column)` pair from the current instruction span.
- `trait_name` comes from the binary expression when it carries `resolved_operator_trait`.
- This reuse preserves the tree walker behavior for mixed types, weak values, nova and user objects. Do not add a VM only fast path that changes an error or a return value.

### Shared unary behavior

V1 adds `performUnaryOperation(operator, operand, position, trait_name, resolved_operator_trait)` next to `performOperation` in `src/runtime.py`. The tree walker's `UNARY_EXPRESSION` case calls the new function. The VM `NEG`, `NOT` and `REVERSE` handlers call the same function. The function covers:

- `!` with `PowangBoolean.cast(operand).data`.
- `-` for `PowangInteger` and `PowangNumber`.
- `-` for user objects through the `Negate` operator trait.
- `[-]` for integer, number, string and array reversal. `REVERSE` is the VM opcode, but the V1 handler can exist without a V1 lowering rule.
- The same `powang_error_invalid_type_for_prefix_operator` error for unsupported operand types.

### Truthiness and assignment

- `values.truthy(value)` is `PowangBoolean.cast(value).data`. Use it for `JUMP_IF_FALSE`, `JUMP_IF_TRUE`, `JUMP_IF_FALSE_KEEP` and `JUMP_IF_TRUE_KEEP`.
- `CAST_ASSIGN` builds a declared target with `src.runtime.getUndefinedVariable(where, type_node)` and calls `src.runtime.assignWithChecks(where, target, value, force_object_assign)`.
- `values.spec_type_node(spec)` converts an image type spec into the synthetic AST node shape that `getUndefinedVariable` expects. The synthetic node has `type` set to `ParserTokenType.TYPE` and `value` set to a dict with `value`, `weak`, `const`, `generics`, `alternatives` and `element_type`.
- `STORE_LOCAL`, `STORE_GLOBAL` and `STORE_NAME` call `values.copy_value` before writing. For scalars this returns the same immutable value.
- `DECLARE_LOCAL` creates an undefined value through `getUndefinedVariable`, applies the flags and pushes it so the normal store path is used. `DECLARE_TYPED` and `DECLARE_INFER` inspect the value on the stack, record the slot type, then push the value back.

### Flags

The `flags` byte on declaration opcodes uses these bits:

| Bit | Name | Meaning |
|---|---|---|
| 0 | `FLAG_WEAK` | The declared value is weak |
| 1 | `FLAG_CONST` | The declared value is const |
| 2 | `FLAG_STRUCTURE_LOCK` | Structure changes are rejected |
| 3 | `FLAG_ELEMENTS_LOCK` | Element assignment is rejected |
| 4 | `FLAG_DEFINED` | The slot starts defined |
| 5 | `FLAG_MUTABLE_CAPTURE` | Code object flag only, used from V2 |

### Scope manager

- The compiler keeps a stack of block scopes. Each scope maps a name to a slot.
- A name lookup searches the current block scope, then enclosing block scopes, then module globals.
- A declaration reserves a new slot in the current frame. Slots are not reused inside one code object until a block exits.
- On block exit the compiler may reuse the slots of the exited block for the next sibling block. This keeps `local_count` small and must not change observable order because names are no longer visible.
- The module init code object treats top level declarations as globals. A top level block still uses local slots for block scoped names.
- `LocalStore` iteration yields declared names in slot order. This matters for debugger display and for helpers that iterate `ScopeStack.variables`.

### Source spans and errors

- `SourceSpan` stores 1 based `start_line`, `start_column`, `end_line` and `end_column`. The compiler converts parser rows and columns by adding 1.
- Every emitted instruction receives the span of the innermost source node that produced it.
- `src/vm/errors.py` `raise_vm_error(kind, message, details, where, span, frames)` creates a `PowangError` with `line` and `column` from the span and raises it.
- Runtime errors use the existing constructors: `powang_error_identifier_not_found`, `powang_error_unsupported_operation`, `powang_error_invalid_type_for_prefix_operator`, `powang_error_type_match`, `powang_error_format`.
- The VM must not prefix messages with a VM marker. The text must match the tree walker exactly, including the `ln: N |` prefix added by `PowangError.render_text`.

### Cancellation and stack limits

- `CHECK_CANCEL` calls `src.builtins.tasks.check_cancellation()`. V1 emits it at loop back edges and before calls. Cancellation is a no-op outside a task.
- Every frame push checks `len(self.frames) < options.max_frames`. The default is 900. The error is the same `RECURSION` error text as the tree walker, including `depth limit: 900`.

### Tree walker quirks that must be preserved

- `1 / 0` and `1 % 0` return `nova`, not an error.
- `1 + true` returns `true` through the existing cast rules.
- Comparing a strong value with a weak value uses the weak comparison path.
- A typed comparison returns `false` instead of raising when the operand types differ.
- An undefined typed local prints as `<int: undefined>` and raises the same undefined reference error when it is used in an operation that requires a defined value.

## Acceptance criteria

1. Every V1 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. The compiler emits no `LOAD_STR`, `LOAD_CHAR` or container opcode in V1.
3. The V1 corpus reports zero differential mismatches for stdout, stderr, exit code and created files.
4. `tests/test_vm_core.py` passes with `POWANG_ENGINE=vm` and covers every V1 language feature.
5. `println(1 / 0)` prints `nova` on both engines.
6. `println(1 + true)` prints `true` on both engines.
7. An undefined name error reports the same line and column on both engines.
8. `x: int = "text"` reports the same `TYPE ERROR` text on both engines.
9. `break missing;` fails at compile time with the same kind of error as the tree walker.
10. A program with a block scoped name cannot read that name after the block exits.
11. The disassembler shows a span line for every V1 instruction and the span line matches the source line of the construct.
12. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_compiler_core -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_control_flow -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_interpreter_core -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_spans -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v1 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_core.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v1\core_arith.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v1\core_arith.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v1/`.

`core_arith.po`:

```po
a := 7;
b := 3;
println(a + b);
println(a - b);
println(a * b);
println(a / b);
println(a % b);
println(-a);
println(a + true);
println(a / 0);
```

`declarations.po`:

```po
count: int = 1;
count = count + 1;
label := true;
empty: int;
println(count);
println(label);
println(empty);
```

`comparison.po`:

```po
println(1 == 1);
println(1 != 2);
println(1 < 2);
println(2 <= 2);
println(3 > 4);
println(3 >= 3);
println(1 == true);
println(1 :: int);
println(1 !: int);
```

`short_circuit.po`:

```po
println(false && print(1));
println(true || print(2));
println(-1);
```

`control_flow.po`:

```po
value := 4;
if value > 5 {
    println(1);
} else if value == 4 {
    println(2);
} else {
    println(3);
}

index := 0;
loop if index < 3 {
    println(index);
    index += 1;
}

sum := 0;
for i >> 0 >> 5 {
    if i == 3 { continue; }
    sum += i;
}
println(sum);

for j := 0; j < 3; j += 1 {
    if j == 1 { break; }
    println(j);
}
```

`labeled_loops.po`:

```po
for |outer| i >> 0 >> 3 {
    for j >> 0 >> 3 {
        if i == 1 && j == 1 {
            break outer;
        }
        println(i * 10 + j);
    }
}

for |outer| i >> 0 >> 2 {
    for j >> 0 >> 2 {
        if j == 1 { continue outer; }
        println(i * 10 + j);
    }
}
```

`range_step.po`:

```po
for i >> 0 >> 2 >> 7 {
    println(i);
}
for i >> 0 >> 4 {
    println(i);
}
```

`error_undefined.po`:

```po
print(missing_name);
```

`error_type_mismatch.po`:

```po
x: int = nova;
println(x);
```

`block_scope.po`:

```po
if true {
    hidden := 5;
    println(hidden);
}
println(1);
```

The error corpus files must produce a nonzero exit code and a stderr string identical to the tree walker. The harness compares the full stderr text, not a substring.

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v1_core_arith` | `src/vm/tests/corpus/v1/core_arith.po` | `LOAD_INT`, `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `NEG`, `COPY`, `STORE_LOCAL`, span lines |
| `v1_declarations` | `src/vm/tests/corpus/v1/declarations.po` | `DECLARE_TYPED`, `DECLARE_INFER`, `DECLARE_LOCAL`, `CAST_ASSIGN`, flags value |
| `v1_control_flow` | `src/vm/tests/corpus/v1/control_flow.po` | `JUMP_IF_FALSE`, `JUMP_IF_TRUE_KEEP`, `JUMP`, backward jump offset, `LT` |
| `v1_labeled_loops` | `src/vm/tests/corpus/v1/labeled_loops.po` | Outer and inner break targets differ, `CONTINUE` target lands after the body |
| `v1_range_step` | `src/vm/tests/corpus/v1/range_step.po` | Step 2 loop uses `LOAD_INT 2` and `ADD`, simple range uses `LOAD_INT 1` |
| `v1_error_span` | `src/vm/tests/corpus/v1/error_undefined.po` | `LOAD_NAME`, span line equals the source line, disassembly contains no VM marker |

Golden files are exact text snapshots. Offsets are part of the snapshot. A change to an operand width is a reviewed change and must include a format version note.

## Atomic commit plan

1. `vm(v1): add compiler scope manager and span plumbing`
2. `vm(v1): lower scalar literals and big integers`
3. `vm(v1): lower local and global declarations`
4. `vm(v1): lower assignment and compound assignment`
5. `vm(v1): add arithmetic handlers with shared runtime helpers`
6. `vm(v1): add comparison and typed comparison handlers`
7. `vm(v1): add short circuit logic and type checks`
8. `vm(v1): lower if and else with block scopes`
9. `vm(v1): lower loop and loop if`
10. `vm(v1): lower c style and range for loops`
11. `vm(v1): lower break and continue with labels`
12. `vm(v1): add span based runtime error formatting`
13. `vm(v1): add v1 corpus golden snapshots and core engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Reimplemented arithmetic drifts from the tree walker | All operator handlers call `performOperation` or `performUnaryOperation` | Revert the handler commit. The compiler still emits the opcodes and the differential corpus fails visibly |
| Slot reuse changes closure behavior | V1 has no closures. Document the slot reuse rule and revisit it in V2 with capture cells | Revert the scope manager commit and disable slot reuse until V2 |
| Line or column off by one | `SourceSpan` is 1 based and `test_spans.py` asserts exact lines for every construct | Revert the span commit. Error text tests fail and block the gate |
| Verifier merge point false positives | Track stack height per instruction boundary and allow the variable height opcodes through explicit rules | Relax only the failing family in strict mode with a documented TODO, then fix before the gate |
| Big integer encoding changes value | Store big integers as decimal strings in the constant pool and parse with Python `int` | Revert the big integer commit. Values above the inline range then fail loudly |
| Dynamic name lookup bypasses globals | `LOAD_NAME` uses the same lookup order as `ScopeStack.get_variable`, including wildcards | Revert the name lookup commit. V1 corpus uses only resolvable names |
| `POWANG_ENGINE=vm` leaks into developer shells | Verification commands always clear the variable in the same block | Run `Remove-Item Env:\POWANG_ENGINE` and rerun the tree suite |

## Exit gate

V1 is closed when all of these are true:

- [ ] Every V1 opcode has a handler, a verifier rule and a unit test.
- [ ] The V1 corpus reports zero mismatches.
- [ ] `tests/test_vm_core.py` passes with `POWANG_ENGINE=vm`.
- [ ] Runtime error text and source positions match the tree walker for the V1 error corpus.
- [ ] Scalar copy semantics match at declaration and assignment boundaries.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
