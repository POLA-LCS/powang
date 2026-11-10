# V8: Async and Tasks

Purpose: deliver async declarations and lambdas, lazy tasks, spawn and await, task waits, cancellation, status, task errors and cleanup, top level await and worker pool limits on the bytecode VM.

## Objective

At the end of V8 the VM executes the language async model. An async function call returns a lazy task. The body does not start until the task is awaited or waited on. `spawn` creates a worker task that starts on the shared task pool. `await` runs a lazy task on the current thread or waits for a worker task. `wait`, `cancel` and `task_status` read and change the same task handle that the tree walker uses.

Task errors propagate through `await`, `wait` and `try` and `catch`. Cancellation is checked at call boundaries and loop back edges. Task cleanup closes cloned state, releases lazy counters and shuts down workers under repeated starts and stops.

The VM does not suspend a task at an arbitrary expression boundary. It preserves the current lazy and worker model. A future coroutine model would need a new bytecode version and a new task state machine.

Semantic reference: `docs/phase-4b-bytecode-vm/01-architecture-and-execution.md` section 7.8, `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` section 13.9, and `docs/phase-4b-bytecode-vm/06-tooling-testing-and-performance.md` section 18.5.

## Prerequisites

- V7 is `gate green`. Errors, finally, propagate and references work.
- The V7 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v7 --fail-fast
```

- The baseline suite is green.

Contract surfaces this phase depends on:

- `src/vm/image.py`: `CodeObject.flags` async bit, `CallSite` dispatch values `async`, `async_method` and `spawn`, `CallSite.is_async`.
- `src/vm/tasks.py`: `create_lazy_task`, `create_worker_task`, `await_task`, `cancel_task`, `task_status`, `close_task_state`.
- `src/builtins/tasks.py`: `TaskPool`, `spawn_task`, `run_lazy_task`, `builtin_wait`, `builtin_cancel`, `builtin_task_status`, `get_task_pool`, `check_cancellation`.
- `src/powang_types.py`: `PowangTask` status fields `pending`, `running`, `done`, `failed`, `canceled`.
- `src/runtime.py`: `copy_for_task`, `_createLazyCallTask`, `_createLazyFunctionValueTask`, `_prepareTaskCall`, `_prepareTaskMethodCall`.
- `src/state.py`: `InterpreterState.clone_for_task`, `InterpreterState.close`.

## Deliverables

### By file

| File | Work in V8 |
|---|---|
| `src/vm/tasks.py` | `create_lazy_task`, `create_worker_task`, `await_task`, `cancel_task`, `task_status`, `close_task_state`, `clone_state_for_task` |
| `src/vm/compiler.py` | Async flags, async lambdas, `CALL_ASYNC`, `CALL_ASYNC_METHOD`, `SPAWN`, `AWAIT`, `CHECK_CANCEL` at call boundaries and loop back edges, top level await |
| `src/vm/dispatch.py` | Async call binding, async method binding, spawn binding, copy semantics for task arguments |
| `src/vm/interpreter.py` | Handlers for `CALL_ASYNC`, `CALL_ASYNC_METHOD`, `SPAWN`, `AWAIT`, `CHECK_CANCEL`, async frame entry and task reference propagation |
| `src/vm/host.py` | `wait`, `cancel` and `task_status` builtins and the task pool boundary |
| `src/vm/tests/test_async.py` | Async declaration, async lambda, async method, async static method, async module function |
| `src/vm/tests/test_lazy_tasks.py` | Lazy start, pending count, repeated await |
| `src/vm/tests/test_spawn.py` | Worker start, module isolation, method and static method spawn |
| `src/vm/tests/test_task_status.py` | `wait`, `cancel`, `task_status` and timeouts |
| `src/vm/tests/test_task_errors.py` | Task failure, await error text, try and catch |
| `src/vm/tests/test_task_cleanup.py` | Repeated starts, shutdown, lazy counter release |
| `src/vm/tests/test_pool_limits.py` | Pending worker and lazy task limits |
| `src/vm/tests/golden/` | V8 golden disassembly snapshots |
| `src/vm/tests/corpus/v8/` | V8 differential corpus |
| `tests/test_vm_async.py` | End to end VM engine test for async and tasks |

### By language feature

| Feature | Required behavior |
|---|---|
| `async fun` declaration | Code object with `FLAG_ASYNC` |
| Async expression body | `>> expression` inside an async code object |
| Async lambda | `async fun(...)` value with `is_async=True` |
| Async method | `async fun this.method(...)`, dispatched with `CALL_ASYNC_METHOD` |
| Async static method | `async fun method(...)`, dispatched with `CALL_ASYNC` |
| Async module function | Exported async function called through `CALL_MODULE`, which returns a lazy task |
| Lazy task | Call returns a `PowangTask` in `pending` state, body not started |
| `await` | Runs a lazy task on the current thread or waits for a worker task |
| `spawn` | Creates a worker task and starts it on the pool |
| `wait` | Waits for a task with an optional timeout |
| `cancel` | Requests cancellation and settles the task |
| `task_status` | Returns the existing status string |
| Top level await | Module init can execute `AWAIT` |
| Task error | Failed task raises a catchable `TASK` error with the original text |
| Task cancellation | Cancellation at call boundaries and loop back edges |
| Cleanup | Task state closes on success, failure, cancellation and shutdown |
| Worker pool limit | Pending worker and lazy limits raise the same `TASK` errors |

## Task checklist

- [ ] Add the async flag and async code object metadata.
- [ ] Lower async declarations and async lambdas.
- [ ] Add `CALL_ASYNC` and lazy task creation.
- [ ] Add `CALL_ASYNC_METHOD` for async methods.
- [ ] Add `SPAWN` and worker task creation.
- [ ] Add `AWAIT` for lazy and worker tasks.
- [ ] Add `wait`, `cancel` and `task_status` builtins.
- [ ] Add task error propagation through await and try and catch.
- [ ] Add cancellation checks at call boundaries and loop back edges.
- [ ] Add top level await.
- [ ] Add worker pool limits and pending lazy limits.
- [ ] Add task cleanup and repeated start and shutdown tests.
- [ ] Add V8 unit tests, corpus, golden snapshots and the async engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `async fun double(value: int): int >> value * 2;` | code object with `FLAG_ASYNC`, `LOAD_LOCAL 0`, `LOAD_INT 2`, `MUL`, `RETURN`. Module init `DECLARE_FUNCTION`, `STORE_GLOBAL` |
| `async fun f(...) { ... }` | code object with `FLAG_ASYNC`, body, `RETURN` |
| `async fun(value: int): int >> value * 2` | lambda code object with `FLAG_ASYNC`, `DECLARE_FUNCTION` |
| `double(3)` where `double` is async | evaluate args, `CALL_ASYNC call_site` |
| `worker.double()` where the method is async | evaluate receiver, evaluate args, `CALL_ASYNC_METHOD call_site` |
| `Type.make(3)` where the static method is async | evaluate args, `CALL_ASYNC call_site` |
| `module.double(3)` where the module function is async | evaluate args, `CALL_MODULE call_site`. `callModuleMember` sees the async flag and returns a lazy task |
| `spawn f(args)` | evaluate args, `SPAWN call_site` |
| `spawn worker.get()` | evaluate receiver, evaluate args, `SPAWN call_site` |
| `spawn Type.make()` | evaluate args, `SPAWN call_site` |
| `await task` | evaluate `task`, `AWAIT` |
| `wait(task, timeout)` | evaluate args, `CALL_BUILTIN wait` |
| `cancel(task)` | evaluate `task`, `CALL_BUILTIN cancel` |
| `task_status(task)` | evaluate `task`, `CALL_BUILTIN task_status` |
| async function entry | `CHECK_CANCEL` at the prologue |
| async loop back edge | `CHECK_CANCEL` before the backward `JUMP` |
| async call boundary | `CHECK_CANCEL` before `CALL_ASYNC`, `CALL_ASYNC_METHOD`, `SPAWN` and ordinary calls |

## Runtime semantics notes

### Async flags and code objects

- `CodeObject.is_async` is true when `flags` has `FLAG_ASYNC` bit 6.
- `FunctionInfo.flags["is_async"]` mirrors the parser flag. `DECLARE_FUNCTION` sets `PowangFunction.is_async`.
- An async code object has the same parameter, local and capture layout as a sync code object. It does not need a suspension table because the VM never suspends at an arbitrary expression boundary.
- An async function body runs to completion when the task is awaited or waited on. It does not yield.

### Lazy task creation

`CALL_ASYNC call_site` performs:

1. Resolve the callee with the same overload selection as `CALL`.
2. Evaluate and bind arguments in the caller frame. Binding uses `copy_for_task` for every argument.
3. Clone the caller state with `state.clone_for_task()`. The clone owns its own scopes, module loader view and task pool reference.
4. Build a `work` closure that creates a `VM` with the cloned state and the same `ProgramImage`, then calls `VM.call_function` with the bound function and copied arguments.
5. Create a `PowangTask` with `pool.next_id()`, `status="pending"`, `lazy_work=work`.
6. Register the task with `pool.register_lazy(task, cloned_state)`.
7. Push the task.

If any step before registration fails, close the cloned state and re-raise. This matches the `try` and `except` shape in `_createLazyCallTask`.

`CALL_ASYNC_METHOD` is the same flow with `receiver` bound and `is_method=True`. The receiver is copied with `copy_for_task`.

The task body is a VM call, not an AST evaluation. The cloned state has `engine == "vm"`, so the nested VM call runs the VM code object.

### Worker tasks

`SPAWN call_site` performs:

1. Resolve the callee and bind arguments.
2. Copy every argument with `copy_for_task`. A reference or a mutable capture raises the existing task copy error before any worker starts.
3. Clone the caller state.
4. Build a `work` closure that runs the VM function in the cloned state.
5. Call `src.builtins.tasks.spawn_task(cloned_state, work, pool)`.
6. Push the task handle.

`spawn_task` assigns the task ID and submits the work. The worker installs the cloned state in its own context. Module closures are isolated because the cloned state has its own module loader cache and scope stack.

### Await

`AWAIT` performs:

1. Unwrap a `PowangAny`.
2. Require a `PowangTask`, otherwise raise the same `TYPE` error as the tree walker with `where` `await`.
3. If `task.lazy_pool is not None`, call `src.builtins.tasks.run_lazy_task(task)`.
4. Else call `src.builtins.tasks.builtin_wait(task)`.
5. Push the returned value.

`run_lazy_task` moves a pending task to `running`, installs the cloned state, runs the work, stores `result` or `error`, sets `status` to `done`, `failed` or `canceled`, and releases the lazy counter. `builtin_wait` blocks on the future and maps the final status to a result, a `TASK` error or `nova` on timeout.

The error text and `where` values come from the existing helpers. Do not wrap them again.

### Task status and cancellation

- `task_status(task)` calls `src.builtins.tasks.builtin_task_status(task)`. The returned strings are the existing status values: `pending`, `running`, `done`, `failed`, `canceled`.
- `cancel(task)` calls `builtin_cancel`. It sets `cancel_requested` and cancels the future when the task has not started. A running task observes the flag at the next `CHECK_CANCEL`.
- `wait(task, timeout)` calls `builtin_wait`. A timeout returns `nova` and leaves the task running.
- Cancellation checks raise a `TASK` error with the same text as the tree walker. `CHECK_CANCEL` calls `src.builtins.tasks.check_cancellation()`.
- The compiler emits `CHECK_CANCEL` at the async function prologue, before every call in an async function and before every backward jump in an async function. This covers loops that do not call anything.

### Task errors

- A failed task stores a converted `PowangError` in `task.error` and sets `status="failed"`.
- `await` and `wait` raise a `TASK` error with `where` `await` or `wait` and the original error text as the detail. The original error is preserved as the cause when the language supports it.
- A `try` and `catch` around `await` catches the `TASK` error. `problem.frames` contains the awaiting frame chain, not the task's internal frame chain.
- A canceled task raises a `TASK` error with `where` `await` or `wait` and the message `task canceled` exactly as the existing helper produces.

### Top level await

- The module init code object can execute `AWAIT`.
- The module init frame has no task reference. `AWAIT` still works because the task itself carries its cloned state.
- A top level `await` on a lazy task runs it on the current module init thread.
- A top level `await` on a worker task blocks the module init thread until the worker settles.
- A failed top level await fails module initialization and enters the loader error path.

### Cleanup

- `run_lazy_task` closes the cloned state in a `finally` block and releases the lazy counter once.
- `TaskPool._run` closes the cloned state in a `finally` block.
- `shutdown_state_tasks(state)` closes the pool and waits for running tasks. The VM calls it from `run_program` in a `finally` block.
- A task that is never awaited and never waited on is still tracked by the pool. Shutdown cancels pending work and closes state.
- `task.handled` is set when a result or error is observed. Unhandled failed tasks do not raise at shutdown. This matches the tree walker.

### Worker pool limits

- `TaskPool.max_workers` comes from `_configured_workers()`.
- `TaskPool.max_pending` comes from `MAX_PENDING_TASKS`.
- A worker spawn over the limit raises `TASK` error `task queue is full` with the pending count, the limit and the advice text.
- A lazy task over the limit raises `TASK` error `too many pending async tasks` with the pending count, the limit and the advice text.
- The VM does not implement a second pool. `get_task_pool(state)` returns the state pool.

### Frame and task interaction

- A frame that belongs to a task holds `frame.task = task`.
- `CHECK_CANCEL` reads `CURRENT_TASK` from `src.builtins.tasks` or `frame.task`. The existing `check_cancellation` uses the context variable, which is set by `run_lazy_task` and by the pool worker.
- `state.call_frames` is per cloned state, so task error frames do not mix with the parent frames.

## Acceptance criteria

1. Every V8 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. An async call returns a `pending` task and does not run the body before `await`.
3. `await` on a lazy task returns the same value as the tree walker.
4. `spawn` starts a worker and `wait` returns the same value as the tree walker.
5. Async methods, async static methods, async lambdas and async module functions work.
6. `task_status` returns the same status string before, during and after a task.
7. `cancel` on a pending lazy task prevents the body from running.
8. `cancel` on a running worker is observed at the next check.
9. A task failure raises the exact `TASK` error text through `await` and `wait`.
10. A `try` and `catch` around `await` catches the task error.
11. Top level await works in a module init code object.
12. A reference passed to `spawn` raises the same task copy error as the tree walker.
13. The worker pool limit and the lazy task limit raise the exact `TASK` error text.
14. Repeated task starts and shutdowns do not leak state, threads or lazy counters.
15. The V8 corpus reports zero mismatches.
16. `test_async.py` and `test_tasks.py` pass with `POWANG_ENGINE=vm`.
17. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_async -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_lazy_tasks -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_spawn -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_task_status -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_task_errors -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_task_cleanup -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_pool_limits -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v8 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_async.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_tasks.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_async.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v8\async_basic.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v8\async_basic.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v8/`.

`async_basic.po`:

```po
async fun double(value: int): int >> value * 2;

async fun total(): int {
    a := await double(3);
    b := await double(4);
    return a + b;
}

println(await total());
```

`lazy_start.po`:

```po
async fun work(): int {
    println("started");
    return 1;
}

task := work();
println(task_status(task));
println(await task);
println(task_status(task));
```

`spawn.po`:

```po
fun work(value: int): int >> value * 2;

task := spawn work(5);
println(wait(task));
println(task_status(task));
```

`async_methods.po`:

```po
type Worker[+] {
    | value: int;

    async fun this.double(): int >> this.value * 2;
    async fun make(value: int): Worker >> Worker.[value];
}

worker := Worker.[5];
println(await worker.double());
made := await Worker.make(3);
println(made.value);
```

`async_lambda.po`:

```po
double := async fun(value: int): int >> value * 2;
println(await double(3));
```

`task_errors.po`:

```po
async fun fail_now(): int {
    error("task boom");
}

try {
    await fail_now();
} catch problem {
    println(problem.kind);
    println(problem.message);
}
```

`wait_error.po`:

```po
fun fail_now(): int {
    error("worker boom");
}

task := spawn fail_now();
try {
    wait(task);
} catch problem {
    println(problem.kind);
    println(problem.message);
}
```

`top_level_await.po`:

```po
async fun value(): int >> 42;
println(await value());
```

`cancel.po`:

```po
async fun work(): int {
    println("started");
    return 1;
}

task := work();
cancel(task);
try {
    println(await task);
} catch problem {
    println(problem.kind);
}
```

The worker pool and lazy task limits are covered by `src/vm/tests/test_pool_limits.py` with a small explicit `TaskPool`. A source level corpus cannot set the pool limit, so a corpus file would be timing dependent and is not used.

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v8_async_basic` | `src/vm/tests/corpus/v8/async_basic.po` | `FLAG_ASYNC` on both code objects, `CALL_ASYNC`, `AWAIT` |
| `v8_async_methods` | `src/vm/tests/corpus/v8/async_methods.po` | `CALL_ASYNC_METHOD`, receiver first, async static call uses `CALL_ASYNC` |
| `v8_async_lambda` | `src/vm/tests/corpus/v8/async_lambda.po` | Lambda code object with async flag, `CALL_ASYNC` through `CALL_VALUE` compatibility |
| `v8_spawn` | `src/vm/tests/corpus/v8/spawn.po` | `SPAWN`, `CALL_BUILTIN wait`, task argument copy |
| `v8_top_level_await` | `src/vm/tests/corpus/v8/top_level_await.po` | `AWAIT` in the module init code object |
| `v8_cancel` | `src/vm/tests/corpus/v8/cancel.po` | `CALL_BUILTIN cancel`, `AWAIT`, `CHECK_CANCEL` at the prologue |

## Atomic commit plan

1. `vm(v8): add async flags and async code metadata`
2. `vm(v8): lower async declarations and async lambdas`
3. `vm(v8): add call async and lazy task creation`
4. `vm(v8): add call async method`
5. `vm(v8): add spawn and worker task creation`
6. `vm(v8): add await for lazy and worker tasks`
7. `vm(v8): add wait cancel and task status builtins`
8. `vm(v8): add task error propagation`
9. `vm(v8): add cancellation checks at boundaries`
10. `vm(v8): add top level await`
11. `vm(v8): add worker pool and lazy task limits`
12. `vm(v8): add task cleanup and repeated start tests`
13. `vm(v8): add v8 corpus golden snapshots and async engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Task body starts before await | Lazy task holds only `lazy_work` and `pending` status until `run_lazy_task` | Revert the lazy task commit |
| Worker state leaks into the parent | `clone_for_task` for every task and close in a `finally` block | Revert the task creation commit |
| Await error text differs | Call `run_lazy_task` or `builtin_wait` and compare full stderr | Revert the await commit |
| Cancellation is ignored in loops | `CHECK_CANCEL` at every async back edge and call boundary | Revert the cancellation commit |
| Task cleanup misses a path | Success, failure, cancellation and shutdown all close the cloned state | Revert the cleanup commit |
| Pool limits differ | Use `TaskPool` unchanged | Revert the pool commit |
| Top level await starts a second event loop | It uses the same `AWAIT` handler and blocks the current thread | Revert the top level await commit |
| References cross task boundaries | `copy_for_task` rejects references and mutable captures before the task is created | Revert the task copy commit |

## Exit gate

V8 is closed when all of these are true:

- [ ] Every V8 opcode has a handler, a verifier rule and a unit test.
- [ ] The V8 corpus reports zero mismatches.
- [ ] Lazy tasks, spawn, await, wait, cancel and status match the tree walker.
- [ ] Task errors and cancellation errors match the tree walker.
- [ ] Task cleanup passes under repeated starts and shutdowns.
- [ ] Worker pool and lazy task limits match the tree walker.
- [ ] `test_async.py` and `test_tasks.py` pass with `POWANG_ENGINE=vm`.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
