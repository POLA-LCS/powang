# Phase 1 patch plan

**Scope:** correctness and guardrails only. No architecture refactor, no new language features, no language server rewrite. Every commit is independently revertible.

**Mandatory baseline:** both working trees are dirty. Create a checkpoint commit or branch first, for example `chore: phase-1 baseline snapshot`, in both repositories. Without it, per-defect reverts are not reliable.

**Two decisions to confirm before starting:**

1. **Copy semantics:** recommended path is recursive value copies for implicit assignments and task snapshots. Explicit `&` references remain aliases. This matches the README claim that instances copy by value and fixes task isolation.
2. **LSP safety:** formatting, range formatting, organize imports, and `source.fixAll` are removed in Phase 1, not rewritten. They return in a later phase only with token-aware tests.

## 1. Commit sequence

| Commit | Objective | Main files | Tests | Done when |
|---|---|---|---|---|
| P0 | Baseline snapshot | all dirty files in both repos | none | `git status --short` is clean |
| P1 | Repair constructor checking and checker error handling | `src/typecheck.py` | existing six failures plus new checker tests | full suite passes, `lsp_smoke.py` passes |
| P2a | Add `require` and remove assertions from parser and simple builtins | `src/error.py`, `src/parser.py`, `src/builtins/cast.py`, `file.py`, `input.py`, `iterable.py`, `output.py`, `system.py` | new optimized-mode tests | parser and builtin asserts no longer disappear under `-O` |
| P2b | Remove assertions from runtime and value classes | `src/runtime.py`, `src/powang_types.py` | optimized-mode suite | whole suite passes under `-O` |
| P3 | Fix short-circuit evaluation | `src/runtime.py` binary branch | new short-circuit tests | skipped branches do not evaluate the right operand |
| P4 | Enforce private ownership and clean method stacks | `src/state.py`, `src/scopestack.py`, `src/runtime.py` | new access-control tests | cross-type private access is rejected, stack is clean after errors |
| P5 | Make implicit copies recursive and task references snapshots | `src/powang_types.py`, `src/state.py` | new copy-semantics tests | `b := a` does not alias, task cannot mutate parent through `&x` |
| P6 | Isolate module closures in task clones | `src/state.py`, `src/runtime.py` module closure path | new task closure test | parent and task module counters are independent |
| P7 | Fix equality and comparison errors | `src/powang_types.py`, `src/runtime.py` `performOperation` | new language tests | user types compare by type, map ordering is a Powang error |
| P8 | Preserve and render error positions | `src/error.py`, `src/typecheck.py`, `src/runtime.py` | new error-position tests | `--check` renders `ln: N`, `with_line` is idempotent |
| P9 | Align runtime named-argument messages | `src/runtime.py` named-argument helpers | new `--no-check` tests | precise messages appear with and without checking |
| P10 | Add `modules.host` packaging coverage | `pyproject.toml`, new packaging test | new packaging test | built wheel contains `modules/host/use.po` |
| P11 | Add powang CI guardrails | `.github/workflows/ci.yml` | CI only | `-O` job and clean-install smoke pass |
| L1 | Disable destructive LSP features | `server/powang_lsp.py`, `extension.js`, `README.md` | new server capability tests | no format, organize-imports, fix-all, or execute-command capability is advertised |
| L2 | Harden LSP transport and shutdown | `server/powang_lsp.py` | new protocol tests | malformed frames, broken pipes, and post-shutdown requests are handled safely |
| L3 | Fix initialize handshake and client capabilities | `extension.js`, `protocol.js` | new Node protocol test plus manual smoke | `initialized` is sent after the initialize response, legend is advertised |
| L4 | Sync vendored source and add drift check | `powang-lsp/src/`, new scripts and pin file | drift script | vendored `src/` matches the pinned powang tree exactly |
| L5 | Add LSP CI and release guardrails | both workflows, scripts, CHANGELOG, `.vscodeignore` | CI only | tests, smoke, drift, version, and vsix inspection all pass |

## 2. Implementation notes for the risky commits

### P1: constructor checking

In `src/typecheck.py` `_infer_instantiation_inner`, the early return at line 1469 already handles `Project`. Expand it to validate named arguments and delete the unreachable block at lines 1471 to 1481:

```python
if normalized == f'{OBJECT}:Project':
    for named_node in named_nodes:
        field_name = named_node.get('name')
        if isinstance(field_name, str) and field_name not in {
            "modules", "paths", "logLevel", "allowSystem"
        }:
            self._error(
                f"Project has no field named '{field_name}'",
                ["fields: modules, paths, logLevel, allowSystem"],
                where='project construction',
            )
    return f'{OBJECT}:Project'
```

Replace the broad `except Exception` in `_infer` with:

```python
try:
    return self._infer_inner(node)
except PowangError as error:
    self.errors.append(error)
    return ANY
except (AttributeError, KeyError, IndexError, TypeError, ValueError):
    return ANY
```

Do not catch `NameError` or `UnboundLocalError`. A checker internal bug must surface, not silently become `any`.

Fix `_infer_method_call` line 1205 by defining `has_named` from `argument_nodes` instead of referencing the undefined `named_nodes`. Split `map.has` and `map.popget` return types in `_infer_native_method`. `has` returns `bool`, `popget` returns the value type.

### P2: assertion removal

There are 98 `assert` statements across `src/`. 93 are directly paired with a `powang_error_*` call on the same line. Audit the remaining 5 as internal invariants.

Add to `src/error.py`:

```python
def require(condition, error):
    if not condition:
        if isinstance(error, BaseException):
            raise error
        raise PowangError(message=str(error), text=str(error))
    return condition
```

Replace `assert COND, ERR` with `require(COND, ERR)`. In `src/builtins/cast.py` lines 92 and 108 the asserted value is the error object itself, so use an explicit `raise powang_error_format(...)` instead. Keep `src/runtime.py` line 2588 as an explicit internal `AssertionError` if it is a true invariant.

Modify `tests/helpers.py` so `run_command`, `run_file`, and `run_source` accept `optimize: bool = False` and prepend `-O` to the Python command. Add `tests/test_optimized_mode.py` for `print(nope);` and `export 1;`.

### P4: private access

`ScopeState` already has `method_call_stack`. Add `static_method_stack: list[str]` to `ScopeState.__init__`, reset it in `clone_for_task`, and expose it through `_ScopeStackMeta` in `src/scopestack.py`.

Add a helper in `src/runtime.py`:

```python
def _private_access_allowed(target) -> bool:
    if ScopeStack.method_call_stack:
        owner = ScopeStack.method_call_stack[-1]
        if owner.type_name == target.type_name:
            return True
    if ScopeStack.static_method_stack:
        return ScopeStack.static_method_stack[-1] == target.type_name
    return False
```

Use it at the four `getProperty` and `getMethods` call sites. Wrap `callMethod` in `try/finally` so the stack always pops. Push and pop `user_type.type_name` around static calls and pass the ownership check into `getStaticMethods`.

### P5: copy semantics

Add a `_memo: dict[int, PowangAny] | None = None` parameter to `PowangCopyConstruct` and `PowangCopyConstructObjectType`. Register container shells in the memo before recursing. Recursively copy array items, map keys and values, set members, tuple items, and object property bags. Preserve functions, modules, tasks, file streams, error values, and explicit references as references.

Remove the unreachable duplicate `PowangErrorValue` branch at lines 902 to 906 while editing the function.

In `copy_for_task`, handle `PowangReference` first:

```python
if value.type == PowangReference.type:
    return copy_for_task(value.get(), memo)
```

The memo also prevents infinite recursion on self-referential objects.

### P6: module closure isolation

`clone_for_task` currently shallow-copies the global function overload sets, so function closures are shared. Add a `_copy_function_for_task` helper with a memo. Clone each `PowangFunction`, rebuild its `closure` dictionary, copy closure variables with `copy_for_task`, and clone closure functions recursively. Preserve function identity within one clone.

### P8: error positions

`PowangError.with_line` always prefixes, so calling it twice double-prefixes. Store `_base_text` at construction. Add `render_text()` that returns the base text when `line` is `None`, otherwise `ln: {line} | {base}`. Make `with_line` return `self` when `line is None` or `self.line is not None`. In `typecheck._error` and `_assign_error`, assign line and column first, then set `error.text = error.render_text()`. In `runtime.interpret_program`, call `with_line` only when the error has no line.

Keep column data for the LSP. Do not add a column to CLI text in Phase 1, to preserve existing output.

### P9: named-argument messages

Align runtime wording with the checker. Use `has no parameter named '{name}'` and `received '{name}' more than once`. In `_ordered_named_constructor`, keep the first precise `PowangError` from failed candidates and re-raise it when no candidate resolves, instead of replacing it with `Invalid named constructor call`.

### P10: packaging

Add `"modules.host" = ["*.po"]` to `pyproject.toml`. Add `tests/test_packaging.py` that parses `pyproject.toml` with `tomllib` and asserts every directory under `modules/` has a matching package-data key and every `.po` file is covered.

The real acceptance is the built wheel. After building, inspect it with `python -m zipfile -l dist/*.whl` and confirm `modules/host/use.po` is present. Do not rely on `import modules.host`, because `modules` is a namespace package.

### L1: disable destructive features

Remove `documentFormattingProvider`, `documentRangeFormattingProvider`, and `executeCommandProvider` from `handle_initialize`. Set `codeActionKinds` to `["quickfix"]`. Remove the "Organize imports", "Fix all auto-fixable problems", and "Format document" actions from `handle_code_action`. Delete or leave unused the unsafe helpers only if they are unreachable. Remove the formatting provider and `source` kind mappings from `extension.js`. Update `README.md` and add a CHANGELOG entry that states the removal.

Add `tests/test_lsp_server.py` that initializes the server and asserts these capabilities and actions are absent.

### L2: transport safety

Refactor `read_message(stream=None)` and `send(message, stream=None)` to accept binary streams, defaulting to `sys.stdin.buffer` and `sys.stdout.buffer`. This makes them unit-testable.

Add `MAX_MESSAGE_BYTES = 16 * 1024 * 1024` and `LSPProtocolError`. `read_message` returns `None` on EOF. It raises on missing or invalid `Content-Length`, oversized frames, short bodies, and invalid JSON. `send` catches `BrokenPipeError` and `OSError` and returns `False`. Add `SHUTDOWN_REQUESTED`. `shutdown` sets it. `dispatch` rejects every method except `exit` after shutdown with error `-32600`. `main` catches `LSPProtocolError`, logs through `window/logMessage` when possible, and exits 1.

### L3: initialize handshake

Move the semantic token legend to a module constant in `extension.js`. Build the initialize capabilities with `tokenTypes: SEMANTIC_TOKEN_TYPES` and `tokenModifiers: []`. Replace the fixed 100 ms `setTimeout` with an awaited `protocol.request('initialize', ...)`, then send `initialized` and the initial `didOpen` messages. Guard every continuation with `serverProcess === proc` so a restart cannot send stale messages.

Give `initialize` a 10 second timeout. Keep the 2 second default for interactive requests. Clear pending requests in `stopServer`.

Add `protocol.respond(id, result)` and `protocol.respondError(id, code, message)` to `protocol.js`. In `handleMessage`, answer server requests: `workspace/configuration` returns `[]`, `workspace/applyEdit` returns `{applied: false}`, and unknown requests return `-32601`. Handle `window/logMessage` as a notification.

### L4: vendored source

After P1 to P9 are merged, copy the fixed `powang/src` tree into `powang-lsp/src`. Then delete the 11 stale files:

`src/stdlib_crypto.py`, `src/stdlib_env.py`, `src/stdlib_http.py`, `src/stdlib_http_router.py`, `src/stdlib_http_server.py`, `src/stdlib_json.py`, `src/stdlib_log.py`, `src/stdlib_strings.py`, `src/stdlib_time.py`, `src/stdlib_url.py`, and `src/builtins/native_methods.py`.

Add `scripts/check_vendored_src.py` and `.github/powang-src-pin.txt`. The script compares relative `.py` file sets and SHA-256 hashes against a reference tree, ignoring `__pycache__`. CI clones powang at the pinned SHA and runs the script.

## 3. Regression test matrix

| Defect | Test file | Cases |
|---|---|---|
| Checker undefined names | `tests/test_type_construction.py`, new `tests/test_typecheck_internal.py` | invalid instantiation, missing argument, NameError propagates |
| Checker silent failure | `tests/test_typecheck_internal.py` | malformed shape returns `ANY`, NameError does not |
| `-O` checks | new `tests/test_optimized_mode.py` | `print(nope)`, `export 1` under `-O` |
| Short-circuit | new `tests/test_short_circuit.py` | `&&`, `||`, `??` skip and evaluate cases |
| Private access | new `tests/test_access_control.py` | same type allowed, other type denied, static access, stack cleanup after error |
| Copy semantics | new `tests/test_copy_semantics.py` | array assignment, nested object property, cycle guard, task reference snapshot |
| Module closures | `tests/test_tasks.py` | parent and task module counters independent |
| Equality and comparison | `tests/test_language.py` | user types compare by type, map ordering returns a language error |
| Error positions | `tests/test_errors.py` | `--check` renders `ln: N`, `with_line` idempotent |
| Named arguments | `tests/test_type_construction.py` | unknown and duplicate names with `--no-check` |
| Packaging | new `tests/test_packaging.py` | every module directory covered, wheel contains `modules/host/use.po` |
| LSP capabilities | new `powang-lsp/tests/test_lsp_server.py` | no formatting, no source actions, no execute commands |
| LSP transport | new `powang-lsp/tests/test_lsp_protocol.py` | valid frame, missing length, malformed header, oversized, short body, invalid JSON, broken pipe, post-shutdown |
| Client protocol | new `powang-lsp/tests/protocol.test.js` | fragmented header and body, pending request cleanup |

The powang tests directory has no `__init__.py`. Run one file with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_packaging.py" -v
```

## 4. CI edits

### powang

Add to the existing matrix job:

```yaml
      - name: Run tests without assertions
        if: matrix.python-version == '3.12'
        run: python -O -m unittest discover -s tests
```

Add a package job:

```yaml
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install --upgrade pip build
      - run: python -m build --wheel
      - run: python -m venv .smoke-venv
      - run: .smoke-venv/bin/python -m pip install dist/*.whl
      - name: Installed CLI smoke
        run: |
          printf 'print("ok");\n' > smoke.po
          test "$(.smoke-venv/bin/powang smoke.po)" = "ok"
      - name: Packaged host module
        run: python -m zipfile -l dist/*.whl | grep 'modules/host/use.po'
```

### powang-lsp

Add `workflow_call:` under `on`. Add these steps to the check job:

```yaml
      - name: Protocol and server tests
        run: |
          python -m unittest discover -s tests
          node --test tests/protocol.test.js
      - name: LSP smoke
        run: python lsp_smoke.py
      - name: Vendored source drift
        run: |
          git clone https://github.com/POLA-LCS/powang.git /tmp/powang-src
          git -C /tmp/powang-src checkout "$(cat .github/powang-src-pin.txt)"
          python scripts/check_vendored_src.py --reference /tmp/powang-src/src
      - name: Version consistency
        run: python scripts/check_versions.py
      - name: Package
        run: npx vsce package --no-dependencies
      - name: Inspect VSIX
        run: python scripts/check_vsix.py powang-lsp-*.vsix
```

Make `publish.yml` call the CI workflow with `needs: test`. Add `tests/**` and `scripts/**` to `.vscodeignore`.

## 5. Phase 1 exit checklist

From `C:\Users\zarap\Dev\Python\powang`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -O -m unittest discover -s tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_packaging.py" -v
uv build --wheel
python -m zipfile -l dist\*.whl
```

Expected: zero failures, wheel contains `modules/host/use.po`, and `print(nope);` exits 1 under `-O`.

From `C:\Users\zarap\Dev\Python\powang-lsp`:

```powershell
python -m unittest discover -s tests
node --test tests/protocol.test.js
python lsp_smoke.py
node --check extension.js
node --check protocol.js
python -m py_compile server/powang_lsp.py
python scripts/check_versions.py
python scripts/check_vendored_src.py --reference ..\powang\src
npx vsce package --no-dependencies
python scripts/check_vsix.py powang-lsp-*.vsix
```

Expected: `lsp smoke: ok`, `versions: ok`, `vendored src: ok`, `vsix: ok`, and no stale files in the package.

Manual check: launch the extension, open a `.po` file, confirm diagnostics appear after the initialize response, and confirm no format, organize-imports, or fix-all command is offered.

## 6. Risks and dependencies

| Risk | Mitigation |
|---|---|
| P1 exposes latent checker errors | Run the full suite and all examples. Fix real diagnostics, not symptoms. |
| P2 mechanical edits change messages | Preserve error objects exactly. Run normal and `-O` suites. Grep for remaining user-facing asserts. |
| P5 deep copies change performance or semantics | Use a memo, add cycle tests, benchmark the example corpus, and document the decision. |
| P4 private policy breaks legitimate same-type access | Test same-type, cross-type, static, and nested cases. |
| L4 sync pulls in unfinished powang work | Pin the exact powang commit after P1 to P9. Add a drift check. |
| L1 removes user-visible features | Document the removal in CHANGELOG and README. Keep the code path for a later safe rewrite. |

Dependency order: P0, then P1, P2a, P2b, P3, P4, P5, P6, P7, P8, P9, P10, P11. L1 to L3 can run in parallel with the interpreter work. L4 must wait for P1 to P9. L5 must wait for L1 to L4.

## 7. Out of scope for Phase 1

- The shared analysis package and AST rewrite.
- TypeSpec unification and runtime dispatch registry.
- Rewriting the language server or replacing the regex index.
- A new token-aware formatter.
- New language features or grammar changes.
- Packaging layout migration beyond `modules.host`.
- Restart backoff, full workspace indexing, incremental sync, and UTF-16 conversion.
- Duplicate `PowangReference` cleanup and other broad dead-code removal.

## 8. Implementation outcome

Phase 1 was implemented with the following deviations from the plan:

- The assert pass found 101 asserts, not 98. All of them carried a language error and were replaced.
- `require` takes an error factory rather than an already evaluated error. This preserves the lazy evaluation of the original `assert condition, error` form and avoids evaluating expensive or failing messages when the condition is true.
- Task references are rejected at the task boundary instead of being snapshotted. This matches the documented rule that a reference lives for one call and cannot be sent to a task.
- Static method calls with named arguments were also fixed. The plan only covered the checker side, but the runtime path was already broken.
- The vendored source pin is the powang commit containing the Phase 1 source fixes.

Verification at the end of Phase 1:

- powang: 223 tests pass in normal mode and under `python -O`.
- powang: the built wheel contains `modules/host/use.po`.
- powang-lsp: 12 Python tests and 3 Node protocol tests pass.
- powang-lsp: `lsp_smoke.py` passes.
- powang-lsp: version, vendored source drift and VSIX inspection checks pass.
