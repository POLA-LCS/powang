"""Thread-based tasks (ADR-0001 W25/W26/W27).

``spawn`` is a language form, not a plain builtin: the parser turns
``spawn call(...)`` into a ``SPAWN_EXPRESSION`` and the runtime evaluates the
arguments in the parent before handing the call to this module. ``wait``,
``cancel`` and ``task_status`` are ordinary builtins exposed through
``BUILTINS``.

The pool is deliberately small and pure standard library:

* ``concurrent.futures.ThreadPoolExecutor`` with a bounded worker count
  (default 4, overridable with ``POWANG_TASK_WORKERS``).
* A bounded in-flight queue (``MAX_PENDING_TASKS``) so a spawn storm raises a
  catchable task error instead of growing without limit.
* Every task runs in a fresh ``contextvars.Context``. The worker installs the
  task's cloned interpreter state there, so ``ScopeStack`` resolves to the
  task's own scopes and the parent's context is untouched.

Cancellation is cooperative. The evaluator calls :func:`check_cancellation` at
statement boundaries; the flag itself is only a request, so a task blocked in
an external Python call still runs to completion.
"""

from __future__ import annotations

import contextvars
import os
import sys
import time
from concurrent.futures import (
    CancelledError as FutureCancelledError,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from contextvars import ContextVar
from itertools import count
from threading import Lock
from typing import Callable, Optional

from ..powang_types import *
from ..error import *
from ..state import get_state, set_state, reset_state, copy_for_task

DEFAULT_TASK_WORKERS: int = 4
MAX_PENDING_TASKS: int = 64
SHUTDOWN_TIMEOUT_SECONDS: float = 1.0
## If a task ignores the first join deadline, request cooperative cancellation
## and give it a short grace period so a normal program exit cannot hang.
SHUTDOWN_CANCEL_GRACE_SECONDS: float = 1.0

## The task currently running in this execution context. Plain programs have
## no task, so the default is ``None`` and cancellation checks are cheap.
CURRENT_TASK: ContextVar[Optional['PowangTask']] = ContextVar(
    'powang_current_task', default=None
)


def _configured_workers() -> int:
    raw = os.environ.get('POWANG_TASK_WORKERS')
    if raw is None:
        return DEFAULT_TASK_WORKERS
    try:
        workers = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_TASK_WORKERS
    return workers if workers > 0 else DEFAULT_TASK_WORKERS


def check_cancellation() -> None:
    """Raise the cooperative cancellation error when the current task asks.

    Called at statement boundaries by the evaluator. Outside a task this is a
    no-op, so interpreter overhead in normal programs is one context lookup.
    """
    task = CURRENT_TASK.get()
    if task is None or not task.cancel_requested:
        return
    error = powang_error_format('TASK', None, 'canceled', [
        f"task {task.task_id} cancellation was requested",
    ])
    setattr(error, '_task_cancel', True)
    raise error


def _require_task(where: str, value: PowangAny) -> PowangTask:
    if value.type == PowangAnyType.type:
        value = PowangUnwrapAny(value)
    if value.type != PowangTask.type:
        raise powang_throw(powang_error_format(
            'TYPE',
            f'builtin: {where}',
            'expected a task value',
            [f"but {value.type} was encountered"],
        ))
    return value


class TaskPool:
    """Bounded worker pool shared by one run and all of its task clones."""

    def __init__(self, max_workers: int | None = None, max_pending: int | None = None):
        self.max_workers: int = max_workers if max_workers is not None else _configured_workers()
        self.max_pending: int = max_pending if max_pending is not None else MAX_PENDING_TASKS
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix='powang-task',
        )
        self._lock = Lock()
        self._pending: int = 0
        self._ids = count(1)
        self.tasks: list[PowangTask] = []
        self.closed: bool = False

    def next_id(self) -> int:
        return next(self._ids)

    def submit(self, task: PowangTask, work: Callable[[], PowangAny], cloned_state) -> None:
        with self._lock:
            if self.closed:
                raise powang_throw(powang_error_format(
                    'TASK', 'spawn', 'the task pool is shut down', []
                ))
            if self._pending >= self.max_pending:
                raise powang_throw(powang_error_format(
                    'TASK',
                    'spawn',
                    'task queue is full',
                    [
                        f"pending tasks: {self._pending}",
                        f"limit: {self.max_pending}",
                        "wait for running tasks before spawning more",
                    ],
                ))
            self._pending += 1

        ## An empty Context gives every task an isolated set of ContextVars.
        ## The worker installs the cloned state into it immediately.
        context = contextvars.Context()
        try:
            future = self._executor.submit(
                context.run, self._run, task, work, cloned_state
            )
        except BaseException:
            with self._lock:
                self._pending -= 1
            raise

        task.future = future
        ## A queued future can be canceled before a worker starts it. In that
        ## case ``_run`` never executes, so the callback owns the pending
        ## counter decrement.
        future.add_done_callback(self._release_if_cancelled)
        with self._lock:
            self.tasks.append(task)

    def _release_if_cancelled(self, future) -> None:
        if future.cancelled():
            with self._lock:
                self._pending -= 1

    def _run(self, task: PowangTask, work: Callable[[], PowangAny], cloned_state) -> None:
        task_token = CURRENT_TASK.set(task)
        state_token = set_state(cloned_state)
        try:
            with task.lock:
                if task.cancel_requested:
                    task.status = 'canceled'
                    return
                task.status = 'running'

            try:
                result = work()
            except BaseException as raw_error:
                converted = powang_error_from_exception(raw_error)
                with task.lock:
                    canceled = bool(getattr(raw_error, '_task_cancel', False)) \
                        or task.cancel_requested
                    task.status = 'canceled' if canceled else 'failed'
                    if converted is not None:
                        task.error = converted
                    else:
                        task.error = powang_error_format(
                            'TASK', 'task', 'task raised an unexpected error', [
                                f"{type(raw_error).__name__}: {raw_error}",
                            ]
                        )
            else:
                with task.lock:
                    task.result = result
                    task.status = 'done'
        finally:
            CURRENT_TASK.reset(task_token)
            reset_state(state_token)
            try:
                cloned_state.close()
            except Exception:
                pass
            with self._lock:
                self._pending -= 1

    def shutdown(self) -> None:
        """Join tasks with a short deadline and report unobserved failures."""
        with self._lock:
            tasks = list(self.tasks)
            self.closed = True

        deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SECONDS
        for task in tasks:
            future = task.future
            if future is None or future.done():
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                future.result(timeout=remaining)
            except Exception:
                ## The runner stores task errors instead of leaking them.
                pass

        ## Anything still running is asked to stop cooperatively. The grace
        ## period lets loop-heavy tasks reach their next statement boundary.
        lingering = [
            task for task in tasks
            if task.future is not None and not task.future.done()
        ]
        for task in lingering:
            with task.lock:
                if task.status in {'pending', 'running'}:
                    task.cancel_requested = True
        cancel_deadline = time.monotonic() + SHUTDOWN_CANCEL_GRACE_SECONDS
        for task in lingering:
            remaining = cancel_deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                task.future.result(timeout=remaining)
            except Exception:
                pass

        unhandled: list[tuple[int, BaseException | None]] = []
        for task in tasks:
            with task.lock:
                if task.status == 'failed' and not task.handled:
                    unhandled.append((task.task_id, task.error))

        for task_id, error in unhandled:
            print(
                f"[TASK WARNING] task {task_id} failed and was never "
                f"awaited: {error}",
                file=sys.stderr,
            )

        self._executor.shutdown(wait=False)


_POOL_LOCK = Lock()


def get_task_pool(state) -> TaskPool:
    """Return the state's pool, creating it on first use."""
    pool = getattr(state, 'task_pool', None)
    if isinstance(pool, TaskPool):
        return pool
    with _POOL_LOCK:
        pool = getattr(state, 'task_pool', None)
        if not isinstance(pool, TaskPool):
            pool = TaskPool()
            state.task_pool = pool
    return pool


def spawn_task(cloned_state, work: Callable[[], PowangAny], pool: TaskPool) -> PowangTask:
    """Register and submit already-prepared work, returning its handle."""
    task = PowangTask(pool.next_id())
    pool.submit(task, work, cloned_state)
    return task


def shutdown_state_tasks(state) -> None:
    pool = getattr(state, 'task_pool', None)
    if isinstance(pool, TaskPool):
        pool.shutdown()


# --------------------------------------------------------------------- builtins
def builtin_wait(task: PowangAny, timeout: PowangAny | None = None) -> PowangAny:
    """Block until the task settles and return a copy of its result.

    With a timeout (milliseconds) the call returns ``nova`` when the deadline
    passes. The task is *not* canceled and keeps running; a later ``wait`` can
    still observe its result. A failed task raises a catchable ``[TASK ERROR]``
    whose details include the original error text.
    """
    task = _require_task('wait', task)

    timeout_seconds: Optional[float] = None
    if timeout is not None:
        if timeout.type not in {PowangInteger.type, PowangNumber.type}:
            raise powang_throw(powang_error_format(
                'TYPE',
                'builtin: wait',
                'timeout must be a number of milliseconds',
                [f"but {timeout.type} was encountered"],
            ))
        timeout_seconds = max(0.0, float(timeout.data) / 1000.0)

    future = task.future
    if future is None:
        return PowangNova()
    try:
        future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        return PowangNova()
    except TimeoutError:
        return PowangNova()
    except FutureCancelledError:
        ## The queued future was canceled before a worker started it.
        pass

    with task.lock:
        task.handled = True
        status = task.status
        result = task.result
        error = task.error

    if status == 'failed':
        original = str(error) if error is not None else 'task failed'
        raise powang_throw(powang_error_format(
            'TASK', 'wait', 'task failed', [original]
        ))
    if status == 'canceled':
        original = str(error) if error is not None else 'cancellation requested'
        raise powang_throw(powang_error_format(
            'TASK', 'wait', 'task canceled', [original]
        ))
    if status == 'done':
        return copy_for_task(result) if result is not None else PowangNova()
    return PowangNova()


def builtin_cancel(task: PowangAny) -> PowangNova:
    """Request cooperative cancellation of a task.

    A task still waiting in the queue is canceled immediately, so ``wait`` on
    it never has to wait for a worker slot. A task already running observes
    the flag at its next statement boundary.
    """
    task = _require_task('cancel', task)
    with task.lock:
        if task.status in {'pending', 'running'}:
            task.cancel_requested = True

    future = task.future
    if future is not None and future.cancel():
        ## Not started yet: transition now instead of waiting for a worker.
        with task.lock:
            task.status = 'canceled'
    return PowangNova()


def builtin_task_status(task: PowangAny) -> PowangString:
    """Return ``pending``, ``running``, ``done``, ``failed`` or ``canceled``."""
    task = _require_task('task_status', task)
    with task.lock:
        return PowangString(task.status)
