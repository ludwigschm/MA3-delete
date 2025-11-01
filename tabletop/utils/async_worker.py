"""Lightweight background worker for non-blocking I/O tasks."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Optional, Tuple

from kivy.clock import Clock

log = logging.getLogger(__name__)

_Task = Tuple[Callable[[], Any], Optional[Callable[[Any, Optional[BaseException]], None]]]

_IO_QUEUE: "queue.Queue[_Task]" = queue.Queue(maxsize=1000)
_SENTINEL: object = object()


def _worker_loop() -> None:
    while True:
        try:
            task, callback = _IO_QUEUE.get()
        except Exception:  # pragma: no cover - defensive guard
            continue
        if task is _SENTINEL:  # pragma: no cover - shutdown not used
            _IO_QUEUE.task_done()
            break
        result: Any = None
        error: Optional[BaseException] = None
        try:
            result = task()
        except Exception as exc:  # pragma: no cover - defensive
            error = exc
            log.exception("Async task failed")
        finally:
            _IO_QUEUE.task_done()
        if callback is not None:
            def _dispatch(_dt: float) -> None:
                try:
                    callback(result, error)
                except Exception:  # pragma: no cover - defensive
                    log.exception("Async callback failed")
            Clock.schedule_once(_dispatch, 0.0)


_THREAD = threading.Thread(
    target=_worker_loop,
    name="TabletopAsyncIO",
    daemon=True,
)
_THREAD.start()


def enqueue_io_task(
    task: Callable[[], Any],
    *,
    on_complete: Optional[Callable[[Any, Optional[BaseException]], None]] = None,
) -> bool:
    """Attempt to enqueue ``task`` for background execution."""

    try:
        _IO_QUEUE.put_nowait((task, on_complete))
    except queue.Full:
        log.warning("Async IO queue saturated – executing task inline")
        return False
    return True


def io_queue_load() -> float:
    """Return the current queue saturation ratio in the range [0, 1]."""

    maxsize = _IO_QUEUE.maxsize
    if not maxsize:
        return 0.0
    return _IO_QUEUE.qsize() / float(maxsize)
