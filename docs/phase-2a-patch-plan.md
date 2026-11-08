# Phase 2A patch plan: loops, slicing, annotations, frames

## 0. Scope

Phase 2A adds language ergonomics that do not require the `TypeSpec` rewrite, lambdas, variadics, or traits.

In scope:

- `loop` and `loop if`.
- `break` and `continue`.
- Labels on `for` and `loop`.
- Dead-branch simplification for literal boolean conditions.
- Slicing and negative indexing.
- Annotations for `obj`, `task`, `file`, `handle`, and `error`.
- Error frames.
- `spawn` on method calls.
- LSP grammar, diagnostics, semantic tokens, and label completion.

Out of scope:

- Lambdas and function types.
- Variadics and spread.
- Traits.
- Async and await.
- Formatter and linter.
- Debugger.
- Cross-module type checking.
- Package registry.
- First-class `module` or `reference` types.

## 1. Locked design

### 1.1 Loops

```po
loop {
    if done {
        break;
    }
}

loop if index < 10 {
    index += 1;
}

loop if line := input("") {
    if line == "quit" {
        break;
    }
    print(line);
}
```

`loop if` uses the same condition grammar as `if`, including declarations. The condition is evaluated before each iteration. A declared variable is scoped to the loop body and re-created on each iteration. `continue` re-evaluates the condition. `break` exits the loop.

`loop` without `if` is unconditional. It must be exited with `break`, or it runs forever.

### 1.2 Labels and control flow

```po
for |rows| row >> matrix {
    for cell >> row {
        if cell == target {
            break rows;
        }
    }
}
```

Labels are optional on every loop form: `for`, `loop`, and `loop if`.

The label syntax is `|identifier|` after the loop keyword. It is not part of the identifier. `break` and `continue` accept an optional label:

```po
break;
continue;
break rows;
continue rows;
```

Semantics:

- Unlabeled `break` or `continue` targets the innermost loop.
- Labeled `break` or `continue` targets the loop with that label.
- Labels are scoped to the loop body.
- Labels do not cross function or lambda boundaries.
- Duplicate active labels are a checker error.
- Unknown labels are a checker error.
- `break` or `continue` outside a loop is a checker error.
- `continue` in a C-style `for` runs the update expression.
- `continue` in `loop if` re-evaluates the condition.
- `continue` in `loop` jumps to the top of the body.
- `break` skips the update expression in a C-style `for`.
- `break` and `continue` inside `try` run `finally` and are not caught by `catch`.
- `break` and `continue` inside `match` target the enclosing loop.

Runtime control flow uses dedicated `BreakSignal` and `ContinueSignal` exceptions with an optional label.

### 1.3 Constant conditions and dead branches

The simplifier runs after parsing and before checking and execution:

```text
source -> tokenizer -> parser -> simplify -> checker -> evaluator
```

Only literal boolean conditions are folded.

| Source | Warning | Tree result |
|---|---|---|
| `if false { A }` | `PW211 condition is always false, this branch has no effect` | Empty block |
| `if false { A } else { B }` | `PW211` | `B` |
| `if true { A } else { B }` | `PW214 else branch is unreachable` | `A` |
| `loop if false { A }` | `PW212 loop condition is always false, this loop has no effect` | Empty block |
| `loop if true { A }` | `PW213 use loop instead of loop if true` | Keep the loop |
| `loop { A }` with no targeting `break` | `PW210 loop has no break` | Keep the loop |

Rules:

- Warnings are emitted before the branch is removed.
- Remaining nodes keep their line and column data.
- Blocks are kept as scope boundaries.
- The simplifier recurses through `else if` chains.
- The simplifier does not evaluate expressions with side effects.
- `--ast` shows the simplified tree.
- The LSP still sees the original text, so warning ranges remain accurate.

### 1.4 Slicing and negative indexing

```po
text[>>]        ## copy
text[2 >>]      ## from index 2
text[>> 5]      ## from 0 to index 5
text[1 >> 4]    ## from 1 to 4
text[-3 >>]     ## last three characters
text[>> -1]     ## everything except the last character
```

Slicing is supported for `str`, `arr`, and `tup`. Bounds are clamped. Negative indices resolve from the end. If `from` is greater than `to`, the result is empty.

Negative indexing is also supported in ordinary indexing:

```po
values[-1]
text[-1]
```

### 1.5 Type annotations

Add these built-in annotations:

- `obj`: top type for user-defined type instances.
- `task`: task handle.
- `file`: file handle.
- `handle`: opaque FFI handle.
- `error`: error value.

`obj` is compatible with every user-defined type. Member access on `obj` requires a cast or a trait. `any` remains the dynamic top type that also accepts primitives.

Not added in Phase 2A:

- `fun` function types.
- `ref` or first-class `reference` types.
- `module` annotations.

### 1.6 Error frames

`PowangError.frames` becomes a real call stack.

Format:

```text
at divide (main.po:4:12)
at run (main.po:9:5)
```

Implementation:

- A per-state call stack of frames.
- Push in `callFunction`, `callMethod`, and module evaluation.
- Pop in `finally`.
- Attach frames to an error when it is raised, if the error has no frames.
- Build formatted strings lazily.
- Keep the innermost frame first.

### 1.7 `spawn` on method calls

```po
task := spawn counter.bump();
task := spawn worker.run(value);
```

The parser accepts `METHOD_CALL` in `spawn`. The runtime resolves the owner and method in the cloned task state, then runs the call on the worker.

## 2. Commit sequence

| Commit | Objective | Main files | Done when |
|---|---|---|---|
| A0 | Add design document and test fixtures | `docs/phase-2a-patch-plan.md`, `tests/fixtures/` | Plan committed |
| A1 | Add simplifier and `if false` warnings | `src/simplify.py`, `src/parser.py`, `src/state.py`, `tests/test_simplify.py` | `if false` branches removed, `PW211` emitted |
| A2 | Add `loop`, `break`, `continue` | `src/lexer/token.py`, `src/lexer/tokenizer.py`, `src/parser.py`, `src/runtime.py`, `src/typecheck.py` | Basic loops and unlabeled control flow work |
| A3 | Add labels and `PW210` | parser, runtime, checker, `tests/test_loops.py` | Nested labeled loops and loop warning work |
| A4 | Add `loop if` declarations and loop constant warnings | parser, runtime, simplifier, tests | `loop if` conditions and `PW212`, `PW213` work |
| A5 | Add slicing and negative indexing | parser, runtime, `powang_types.py`, `tests/test_slicing.py` | `str`, `arr`, `tup` slicing work |
| A6 | Add `obj`, `task`, `file`, `handle`, `error` annotations | `src/parser.py`, `src/typecheck.py`, `src/powang_types.py`, tests | Annotations check and run |
| A7 | Add error frames | `src/error.py`, `src/state.py`, `src/runtime.py`, tests | Caught errors expose frames |
| A8 | Add `spawn` method calls | parser, runtime, tests | Spawned methods run with isolated state |
| A9 | Update LSP grammar, tokens, diagnostics, label completion | `server/powang_lsp.py`, `syntax/powang.tmLanguage.json`, theme, tests | LSP highlights and completes new syntax |
| A10 | Update docs, changelog, and CI | README, CHANGELOG, workflows | Exit checks pass |

## 3. Detailed changes

### 3.1 Simplifier

Create `src/simplify.py` with `simplify_program(program_ast, warn)`.

It walks statements and expressions and handles:

- `IF_STATEMENT` with a literal boolean condition.
- `LOOP_STATEMENT` with a literal boolean condition.
- Nested blocks and `else if` chains.

Warnings use `get_state().warn(...)` so `--no-warnings` and the LSP warning sink keep working.

### 3.2 Loop parser and runtime

Add token types:

- `LOOP_STATEMENT`
- `BREAK_STATEMENT`
- `CONTINUE_STATEMENT`
- `SLICE_EXPRESSION`

Add keywords:

- `loop`
- `break`
- `continue`

Parser helpers:

- `helper_LoopStatement`
- `helper_BreakStatement`
- `helper_ContinueStatement`
- A shared `_parse_if_condition` used by `if` and `loop if`.

Runtime:

- `BreakSignal` and `ContinueSignal`.
- Loop evaluation catches matching signals.
- C-style `for` runs the update on `continue`.
- `loop if` evaluates the condition and binds condition declarations per iteration.

### 3.3 Slicing

Parser:

- Extend the index parser to detect `>>` inside brackets.
- Build a `SLICE_EXPRESSION` node with optional start and end.

Runtime:

- `slice_value(target, start, end)` for `str`, `arr`, and `tup`.
- Clamp bounds and resolve negative indices.
- Return the same container type.

Checker:

- Return `str` for string slices.
- Return `arr[element]` for array slices.
- Return the same tuple type for tuple slices.

### 3.4 Type annotations

Parser:

- Add `obj`, `task`, and `file` to `NATI_TYPES`.
- Confirm `handle` and `error` are present.

Checker:

- Normalize `obj` to the user-type top type.
- Allow assignment from any user type to `obj`.
- Reject member access on `obj` without a cast or trait.
- Map `task`, `file`, `handle`, and `error` to their runtime types.

Runtime:

- `getUndefinedVariable` and cast helpers accept the new annotations.

### 3.5 Error frames

Add a `Frame` dataclass with name, file, line, and column.

`InterpreterState` owns `call_frames`.

`callFunction` and `callMethod` push and pop frames in `try/finally`.

On error, attach a copy of the current frames if `frames` is empty.

### 3.6 Spawn method calls

Parser:

- Allow `METHOD_CALL` after `spawn`.

Runtime:

- Add a `_prepareTaskCall` branch for `METHOD_CALL`.
- Resolve the owner in the task state, resolve the method, and bind arguments.
- Reuse the named-argument and overload logic.

### 3.7 LSP

Server:

- Add `loop`, `break`, and `continue` to keywords and docs.
- Add `label` to the semantic token types.
- Track loop labels and their line ranges in the document index.
- Complete active labels after `break` and `continue`.
- Publish the new `PW210` to `PW214` warnings through the existing diagnostics path.

Grammar and theme:

- Highlight loop labels and the new keywords.
- Highlight slicing.
- Add a color for the `label` semantic token.

Tests:

- Capability tests stay unchanged.
- Add tests for label completion, warnings, and semantic token legend.

## 4. Regression test matrix

| Area | Test file | Cases |
|---|---|---|
| Simplifier | `tests/test_simplify.py` | `if false`, `if false else`, `if true else`, `loop if false`, `loop if true` |
| Loops | `tests/test_loops.py` | `loop`, `loop if`, `break`, `continue`, C-style update, nested labels |
| Control flow and try | `tests/test_loops.py` | `break` in `try`, `finally` runs, `catch` does not catch signals |
| Lambda boundary | `tests/test_loops.py` | `break` inside a lambda is rejected |
| Slicing | `tests/test_slicing.py` | copy, open ends, negative indices, empty, out of bounds, arrays, tuples |
| Annotations | `tests/test_annotations.py` | `obj`, `task`, `file`, `handle`, `error` |
| Frames | `tests/test_errors.py` | nested calls, method calls, task errors |
| Spawn methods | `tests/test_tasks.py` | module method, user type method, state isolation |
| LSP | `powang-lsp/tests/test_lsp_language.py` | diagnostics, label completion, semantic legend |

## 5. Verification commands

From `C:\Users\zarap\Dev\Python\powang`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -O -m unittest discover -s tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_loops.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_slicing.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_annotations.py" -v
uv build --wheel
```

From `C:\Users\zarap\Dev\Python\powang-lsp`:

```powershell
python -m unittest discover -s tests
node --test tests/protocol.test.js
python lsp_smoke.py
python scripts/check_versions.py
python scripts/check_vendored_src.py --reference ..\powang\src
npx vsce package --no-dependencies
python scripts/check_vsix.py powang-lsp-*.vsix
```

## 6. Risks and dependencies

| Risk | Mitigation |
|---|---|
| Control signals are caught by `catch` | Re-raise them in the runtime catch path and test `try/finally` |
| Labels cross function boundaries | Checker starts a fresh label stack per function and lambda |
| Simplifier changes scoping | Keep block nodes and preserve spans |
| Slicing conflicts with `>>` in map literals and ranges | Parse `>>` inside brackets only in index context |
| `obj` weakens type safety | Restrict member access on `obj` to casts and traits |
| Frames cost too much | Build strings lazily and only attach on error |
| Spawn method resolution uses the parent state | Resolve the owner and method in the cloned task state |
| LSP label completion is noisy | Only suggest labels whose loop range contains the cursor |

Dependency order: A0, A1, A2, A3, A4, A5, A6, A7, A8, A9, A10. A5 through A8 can run in parallel after A2.

## 7. Acceptance criteria

- All existing tests pass.
- The `-O` suite passes.
- `if false` branches are absent from `--ast`.
- `PW210` to `PW214` appear as warnings and are suppressed by `--no-warnings`.
- Labeled loops work across all for forms and `loop`.
- `break` and `continue` in `try/finally` preserve `finally` behavior.
- Slicing produces the documented results for strings, arrays, and tuples.
- `obj`, `task`, `file`, `handle`, and `error` annotations check and run.
- Caught errors expose non-empty `frames`.
- `spawn` method calls run with isolated task state.
- The LSP highlights the new syntax, completes active labels, and publishes the new warnings.
