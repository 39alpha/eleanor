"""Off-thread committing for output sinks that must write serially.

A sink whose :meth:`~eleanor.output.interface.AbstractOutputSink.commit_batch`
runs in the parent process sits directly on the dispatch loop: while it writes,
the loop is neither collecting finished chunks nor handing out new ones, so the
worker pool can only work through whatever it was already given.
:class:`BackgroundWriter` moves those commits onto a dedicated thread, which
turns the parent's per-point cost from ``unpickle + commit`` into
``max(unpickle, commit)`` and lets the dispatch loop keep the pool fed
meanwhile.

The thread is deliberately singular. Every serial sink in the tree keeps state
that assumes one writer -- a monotonic point counter, an open file handle, a
single database transaction -- so the win being sought here is overlap with
the workers, not write concurrency. A single FIFO consumer also means commits
happen in exactly the order the dispatch loop produced them, which keeps
``outcomes[i]`` lined up with the chunk that produced it.
"""

import queue
import threading
from collections.abc import Sequence
from types import TracebackType
from typing import Self

from eleanor.output.interface import AbstractOutputSink, WriteOutcome
from eleanor.progress import ProgressHandle

_ABORT_JOIN_TIMEOUT_S = 5.0
"""How long :meth:`BackgroundWriter.abort` waits for an in-flight commit.

Long enough for a commit already in progress to finish and release its
resources, short enough that a wedged sink cannot hang an interrupt.
"""


class BackgroundWriter:
    """Runs a sink's ``commit_batch`` calls on a dedicated thread.

    Owns the sink exclusively for the lifetime of one run: the sink is only
    ever touched from the writer thread between :meth:`start` and
    :meth:`join`, so it never sees concurrent commits and never needs its own
    locking. Callers must not commit through the sink directly while a writer
    is active, and must :meth:`join` (or :meth:`abort`) before any
    ``finalize_run`` / ``finalize`` call -- both because outcomes are
    incomplete until then, and because a sink is entitled to tear down state
    that an in-flight commit is still using.

    Use as a context manager to get that ordering for free::

        with BackgroundWriter(sink, order_id, depth=8) as writer:
            writer.submit(prepared)
        outcomes = writer.outcomes

    :param sink: The sink to commit through. Not touched by this object on the
        calling thread.
    :param order_id: Forwarded to every ``commit_batch`` call.
    :param depth: Maximum number of prepared payloads to hold. Reached only
        when the sink cannot keep up, at which point :meth:`submit` blocks --
        which is the intended backpressure: without it the parent would buffer
        prepared payloads without bound.
    :param progress: Forwarded to every ``commit_batch`` call. Safe to hand to
        another thread: a progress handle is a stateless wrapper over a
        manager-backed queue.
    """

    _sink: AbstractOutputSink
    _order_id: int
    _progress: ProgressHandle | None
    _queue: queue.Queue[Sequence[object] | None]
    _thread: threading.Thread | None
    _outcomes: list[WriteOutcome]
    _error: BaseException | None

    def __init__(
        self,
        sink: AbstractOutputSink,
        order_id: int,
        *,
        depth: int,
        progress: ProgressHandle | None = None,
    ) -> None:
        self._sink = sink
        self._order_id = order_id
        self._progress = progress
        self._queue = queue.Queue(maxsize=max(1, depth))
        self._thread = None
        self._outcomes = []
        self._error = None

    @property
    def outcomes(self) -> list[WriteOutcome]:
        """Outcomes committed so far, in commit order.

        Only meaningful once :meth:`join` has returned; reading it earlier
        races with the writer thread.
        """
        return self._outcomes

    def start(self) -> None:
        """Start the writer thread. Idempotent."""
        if self._thread is not None:
            return

        # Not a daemon: a half-written batch is worse than a slow exit, and
        # both exit paths join explicitly anyway.
        self._thread = threading.Thread(target=self._run, name="eleanor-writer")
        self._thread.start()

    def submit(self, prepared: Sequence[object]) -> None:
        """Queue one prepared payload for commit.

        Blocks while the queue is full. Re-raises a commit failure from the
        writer thread so it surfaces in the dispatch loop, matching what an
        inline ``commit_batch`` would have done.
        """
        if self._thread is None:
            msg = "background writer is not running -- call start() before submit()"
            raise RuntimeError(msg)

        error = self._error
        if error is not None:
            raise error

        self._queue.put(prepared)

    def join(self) -> list[WriteOutcome]:
        """Drain the queue, stop the thread, and return every outcome.

        Re-raises a stashed commit failure after the thread has stopped, so a
        failure is never silently dropped even if it happened after the last
        :meth:`submit`.
        """
        if self._thread is None:
            if self._error is not None:
                raise self._error
            return self._outcomes

        # A plain blocking put, deliberately: the writer thread is still
        # consuming, so room appears on its own. Making room by discarding --
        # as ``abort`` does -- would silently drop committed-but-not-yet-
        # written payloads whenever the queue happened to be full here.
        self._queue.put(None)
        self._thread.join()
        self._thread = None

        if self._error is not None:
            raise self._error
        return self._outcomes

    def abort(self) -> None:
        """Stop the thread without waiting for queued work, and without raising.

        For teardown paths that already have an exception in flight -- an
        interrupt, or a failure elsewhere in the dispatch loop. Queued payloads
        are discarded rather than committed, and a stashed commit error is left
        on the instance instead of being raised, so it cannot mask whatever is
        already propagating.
        """
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
        """Join on a clean exit, abort otherwise.

        Aborting on the exception path keeps ``join``'s re-raise from
        displacing the exception already on its way out.
        """
        if exc_type is None:
            _ = self.join()
        else:
            self.abort()

    def _run(self) -> None:
        """Writer-thread body: commit each payload until the sentinel arrives.

        After a failure the loop keeps consuming but stops committing. It must
        not return early: a producer blocked on a full queue would then never
        be released.
        """
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
        """Deliver the stop sentinel, discarding queued work to make room.

        Only for :meth:`abort`. A producer may be blocked on a full queue and
        refilling it as fast as the thread drains, so getting the sentinel in
        can require dropping payloads -- acceptable when tearing down, and
        never acceptable on the :meth:`join` path.
        """
        while True:
            try:
                self._queue.put(None, timeout=0.05)
                return
            except queue.Full:
                self._discard_queued()


__all__ = ["BackgroundWriter"]
