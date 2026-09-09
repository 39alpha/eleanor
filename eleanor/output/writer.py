"""Off-thread committing for output sinks that must write serially."""

import queue
import threading
from collections.abc import Sequence
from types import TracebackType
from typing import Self

from eleanor.output.interface import AbstractOutputSink, WriteOutcome
from eleanor.progress import ProgressHandle

_ABORT_JOIN_TIMEOUT_S = 5.0


class BackgroundWriter[IdT]:
    """Runs a sink's ``commit_batch`` calls on a dedicated thread."""

    _sink: AbstractOutputSink[IdT]
    _order_id: IdT
    _name: str
    _progress: ProgressHandle | None
    _queue: queue.Queue[Sequence[object] | None]
    _thread: threading.Thread | None
    _outcomes: list[WriteOutcome]
    _error: BaseException | None

    def __init__(
        self,
        sink: AbstractOutputSink[IdT],
        order_id: IdT,
        *,
        depth: int,
        progress: ProgressHandle | None = None,
        name: str | None = None,
    ) -> None:
        self._sink = sink
        self._order_id = order_id
        self._name = name or type(sink).__name__
        self._progress = progress
        self._queue = queue.Queue(maxsize=max(1, depth))
        self._thread = None
        self._outcomes = []
        self._error = None

    @property
    def outcomes(self) -> list[WriteOutcome]:
        """Outcomes committed so far, in commit order."""
        return self._outcomes

    def start(self) -> None:
        """Start the writer thread. Idempotent."""
        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._run,
            name=f"eleanor-writer[{self._name}]",
            daemon=True,
        )
        self._thread.start()

    def submit(self, prepared: Sequence[object]) -> None:
        """Queue one prepared payload for commit."""
        if self._thread is None:
            msg = "background writer is not running -- call start() before submit()"
            raise RuntimeError(msg)

        error = self._error
        if error is not None:
            raise error

        self._queue.put(prepared)

    def join(self) -> list[WriteOutcome]:
        """Drain the queue, stop the thread, and return every outcome."""
        if self._thread is None:
            if self._error is not None:
                raise self._error
            return self._outcomes

        self._queue.put(None)
        self._thread.join()
        self._thread = None

        if self._error is not None:
            raise self._error
        return self._outcomes

    def abort(self) -> None:
        """Stop the thread without waiting for queued work, and without raising."""
        if self._thread is None:
            return

        self._discard_queued()
        self._force_sentinel()
        self._thread.join(timeout=_ABORT_JOIN_TIMEOUT_S)
        self._thread = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Join on a clean exit, abort otherwise."""
        if exc_type is None:
            _ = self.join()
        else:
            self.abort()

    def _run(self) -> None:
        """Writer-thread body: commit each payload until the sentinel arrives."""
        while True:
            item = self._queue.get()
            if item is None:
                return
            if self._error is not None:
                continue
            try:
                self._outcomes.extend(
                    self._sink.commit_batch(self._order_id, item, progress=self._progress),
                )
            except BaseException as error:
                self._error = error

    def _discard_queued(self) -> None:
        """Drop everything currently queued, ignoring races with the thread."""
        while True:
            try:
                _ = self._queue.get_nowait()
            except queue.Empty:
                return

    def _force_sentinel(self) -> None:
        """Deliver the stop sentinel, discarding queued work to make room."""
        while True:
            try:
                self._queue.put(None, timeout=0.05)
                return
            except queue.Full:
                self._discard_queued()


__all__ = ["BackgroundWriter"]
