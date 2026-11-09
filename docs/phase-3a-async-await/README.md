# Phase 3A: async and await

## 1. Scope

This phase adds asynchronous function declarations and await expressions.

In scope:

- Parse `async fun` declarations at top level, in type bodies and in trait bodies.
- Parse `async` lambdas.
- Parse `await expression` as a prefix expression.
- Return a lazy task from an async call.
- Run a lazy task when it is awaited.
- Await a task created by `spawn`.
- Support async free functions, instance methods, static methods, trait default methods, async lambdas and exported module functions.
- Support top-level await.
- Report await outside an async function as a checker error.
- Report await on a non-task value as a checker error.
- Preserve the awaited result type through the checker.
- Propagate async task errors through await and try/catch.
- Support `wait`, `cancel` and `task_status` on lazy tasks.
- Bound pending lazy tasks.
- Add LSP keyword highlighting, completion, hover and diagnostics for async and await.

Out of scope:

- Preemptive scheduling.
- Suspending an async body at an arbitrary expression boundary.
- Parallel await of several tasks at once.
- Async extern functions.
- Preserving the async marker when an async function crosses a function-typed parameter.
- Package registry.
- Formatter and linter.

## 2. Syntax

An async function uses `async` before `fun`:

```po
async fun fetch(): int {
    return 42;
}
```

An async expression body uses the existing `>>` form:

```po
async fun double(value: int): int >> value * 2;
```

Async methods use the same modifier:

```po
type Worker[+] {
    | value: int;

    async fun this.double(): int >> this.value * 2;
    async fun make(value: int): Worker >> Worker.[value];
}
```

Async lambdas use `async fun` in expression position:

```po
triple := async fun(value: int): int >> value * 3;
```

Await is a prefix expression:

```po
result := await fetch();
```

Top-level await is allowed. This gives a program a direct entry point for lazy async tasks.

## 3. Task model

`spawn` remains the parallel task primitive. It starts a worker task immediately.

An async call creates a lazy `task` value. The body does not start until the task is awaited or waited on. This avoids pool starvation when async functions await other async functions.

The task states are:

```text
pending -> running -> done
pending -> canceled
running -> failed
running -> canceled
```

`await` on a pending lazy task runs the body on the current thread with the task's cloned interpreter state. `await` on a worker task waits for the worker.

`wait` on a lazy task runs it with the same rules as `await` and returns its result. `cancel` on a pending lazy task marks it canceled and releases its cloned state. `task_status` reports the same states for both task kinds.

Calling an async function and never awaiting it leaves the task pending until program shutdown. Pending lazy tasks are bounded by the same pending limit as the task pool. The default limit is 64.

An async function in a `spawn` call runs its body on the worker and returns the body result, not another task. This makes `await spawn async_function()` return the body result.

## 4. Type checking

`_Signature` gains an `is_async` flag.

An async function keeps its declared return type in its signature. A call to an async function has static type `task`. The call node records the declared return type in `async_result_type`.

`await` checks its operand:

- The operand type must be `task` or `any`.
- Inside a function, the enclosing function must be async.
- At top level, await is allowed.
- The result type is the recorded `async_result_type`, or `any` when the task value does not carry a result type.

Examples:

```po
async fun number(): int >> 1;

value: int = await number();
text: str = await number();
```

The second line reports a type mismatch between `str` and `int`.

An async function call without await has type `task`:

```po
task := number();
print(typeof(task));
```

The output is `task`.

Async lambdas assigned to a local variable are tracked so a direct call through that variable returns `task` and await sees the declared result type.

## 5. Runtime support

`PowangFunction` gains an `is_async` flag. Task copies preserve the flag along with the other function metadata.

Async free function calls use `_createLazyCallTask`. The helper resolves the callable in the parent state, copies the evaluated arguments, clones the parent state for the task and registers a lazy task. Resolving in the parent keeps local variables, parameters and method receivers available.

Async instance and static method calls use the same helper with method preparation. Async module functions resolve the exported member and call the body synchronously inside the lazy task, so the task does not wrap another task.

`PowangTask` gains lazy fields:

```text
lazy_work
lazy_state
lazy_pool
lazy_counted
```

`run_lazy_task` installs the cloned state, sets the current task for cancellation checks, runs the body, stores the result or error and closes the cloned state. It raises a catchable `[TASK ERROR]` for failed and canceled tasks.

The task pool tracks pending lazy tasks separately from worker tasks. A full pending queue raises a catchable task error instead of growing without limit. Shutdown closes any state held by an unawaited lazy task.

## 6. Diagnostics

Await outside an async function:

```text
ln: 3 | [TYPE ERROR] (in await expression) 'await' is only valid inside an async function:
      | mark the enclosing function as async
```

Await on a non-task value:

```text
ln: 2 | [TYPE ERROR] (in await expression) 'await' expects a task value:
      | but int was encountered
```

A failed async body propagates through await:

```po
async fun boom(): int {
    error("boom");
    return 1;
}

try {
    print(await boom());
} catch caught {
    print("caught");
}
```

The catch runs and the program continues.

## 7. LSP support

The LSP adds:

- `async` and `await` to keyword completion.
- Keyword hover for both words with a syntax-highlighted `powang` code block and plain prose.
- Keyword semantic tokens.
- Grammar highlighting for `async` before `fun` and for `await`.
- Document indexing for `async fun` declarations.
- Diagnostics from the vendored powang checker.

## 8. Limitations

- Async tasks are lazy. A call does not start work until await, wait or cancellation.
- An async function passed through a parameter typed as `fun[...]` loses its async marker in the checker. Direct calls by name keep the marker.
- An async function called through an `any` function value returns a lazy task at runtime but the checker can only see `any`.
- Async extern functions are not supported.
- A task cannot await itself. Re-entering a running lazy task reports a task error.

## 9. Tests

Powang tests cover:

- Async free functions and nested awaits.
- Async instance methods and static methods.
- Async lambdas.
- Exported async module functions.
- Async trait default methods.
- Top-level await.
- Await on a spawned task.
- Wait, cancel and task status on lazy tasks.
- Error propagation through await.
- Await outside an async function.
- Await on a non-task value.
- Await result type mismatch.
- Pending lazy task limit and release after await.
- The async example.

LSP tests cover:

- Keyword semantic tokens.
- Async declaration indexing.
- Keyword completion.
- Await hover prose.
- Await diagnostics.
- Grammar entries.

## 10. Acceptance criteria

- `async fun` works at top level, in type bodies and in trait bodies.
- `await` works on lazy async tasks and spawned tasks.
- Async methods, statics, trait defaults, lambdas and exported module functions work.
- Await outside an async function is a checker error.
- Await on a non-task value is a checker error.
- Await preserves the declared result type.
- Failed async bodies propagate through await.
- Pending lazy tasks are bounded and released.
- The full powang test suite passes in normal mode and under `python -O`.
- The LSP test suite, smoke test, version check and vendored source check pass.
