"""Wall-clock accounting for the :meth:`Eleanor.process` dispatch loop.

The dispatch loop interleaves four activities in the parent process: pulling
points out of the navigator, submitting chunks to the executor, blocking until
a chunk completes, and (for serial sinks) writing the resulting payload.
:class:`DispatchTimings` accumulates the time spent in each so a run can be
attributed rather than guessed at.

Alongside that split, :attr:`DispatchTimings.starved_s` reports parent-side
time during which fewer chunks were outstanding than there are workers. The
outstanding count is an upper bound on how many chunks the pool could possibly
be working on, so whenever it falls below the worker count at least one worker
provably has nothing to do. It is charged across both the blocking wait and
the serial-sink write, because a parent stalled in ``write_batch`` starves the
pool just as effectively as one that has run out of points to hand out.

``starved_s`` is a strict *lower* bound on worker idleness, not an estimate of
it. It cannot see the case that matters most for a slow serial sink -- plenty
of chunks outstanding, all of them already finished, the parent too busy
writing to collect them. Two things stand in the way of detecting that from
the parent:

* ``len(futures)`` counts submitted-and-not-yet-collected work, which says
  nothing about how much of it is still executing.
* Polling ``Future.done()`` to find out does not help. A
  :class:`~concurrent.futures.ProcessPoolExecutor` result is only marked done
  once its result-handler *thread* has unpickled it, and that thread needs the
  GIL that a CPU-bound ``write_batch`` is holding -- so the probe reads "not
  done" exactly when the parent is busiest. Worse, the same contention means a
  slow parent-side write actively delays result collection.

Measure total worker idleness by differencing wall clock against a
compute-only baseline run (a worker-write sink with no write cost) at the same
size and worker count, rather than from inside the dispatch loop.

.. note::
    ``generate`` and ``submit`` time is not classified against the pool state,
    so ``starved_s`` under-reports by however long those take. Pre-pipelining,
    the per-batch drain barrier means the pool is provably empty for the whole
    ``generate`` region at a batch boundary.

.. note::
    Because a result is unpickled before its future is marked done, IPC cost
    is folded into :attr:`wait_s` and is not separately attributable here;
    measure payload sizes directly if the numbers point that way.
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(slots=True)
class DispatchTimings:
    """Accumulated wall-clock totals for one :meth:`Eleanor.process` call.

    All context managers are no-ops when :attr:`enabled` is ``False``, so the
    instrumentation can stay in the hot loop unconditionally.

    :param enabled: When ``False`` no clock is read and every counter stays at
        zero.
    """

    enabled: bool = False

    generate_s: float = 0.0
    """Time spent pulling batches out of the navigator."""

    submit_s: float = 0.0
    """Time spent in :meth:`AbstractExecutor.submit`."""

    wait_s: float = 0.0
    """Time spent blocked in :meth:`AbstractExecutor.pop_completed_future`."""

    write_s: float = 0.0
    """Time spent in :meth:`AbstractOutputSink.write_batch` in the parent."""

    starved_s: float = 0.0
    """Parent-side time with fewer chunks outstanding than there are workers.

    Charged across both :attr:`wait_s` and :attr:`write_s`. A strict lower
    bound on worker idleness -- see the module docstring for what it cannot
    see and how to measure the rest.
    """

    chunks: int = 0
    """Number of chunks submitted to the executor."""

    points: int = 0
    """Number of VS points submitted to the executor."""

    elapsed_s: float = 0.0
    """Wall clock for the whole measured region."""

    @contextmanager
    def measure(self) -> Generator[None]:
        """Record :attr:`elapsed_s` for the enclosed region."""
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            self.elapsed_s += time.perf_counter() - start

    @contextmanager
    def generating(self) -> Generator[None]:
        """Accumulate into :attr:`generate_s`."""
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            self.generate_s += time.perf_counter() - start

    @contextmanager
    def submitting(self) -> Generator[None]:
        """Accumulate into :attr:`submit_s`."""
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            self.submit_s += time.perf_counter() - start

    @contextmanager
    def waiting(self, *, in_flight: int, num_workers: int) -> Generator[None]:
        """Accumulate into :attr:`wait_s`, and :attr:`starved_s` when starved.

        :param in_flight: Chunks outstanding at the moment the wait begins,
            counted *before* the completed one is popped.
        :param num_workers: Worker count the executor reports.
        """
        if not self.enabled:
            yield
            return

        starved = in_flight < num_workers
        start = time.perf_counter()
        try:
            yield
        finally:
            delta = time.perf_counter() - start
            self.wait_s += delta
            if starved:
                self.starved_s += delta

    @contextmanager
    def writing(self, *, in_flight: int, num_workers: int) -> Generator[None]:
        """Accumulate into :attr:`write_s`, and :attr:`starved_s` when starved.

        Taking ``in_flight`` here is the point: a serial sink's write runs on
        the dispatch thread, so worker idleness during it is caused by the
        write and belongs in :attr:`starved_s` rather than going unrecorded.

        :param in_flight: Chunks still outstanding while the write runs.
        :param num_workers: Worker count the executor reports.
        """
        if not self.enabled:
            yield
            return

        starved = in_flight < num_workers
        start = time.perf_counter()
        try:
            yield
        finally:
            delta = time.perf_counter() - start
            self.write_s += delta
            if starved:
                self.starved_s += delta

    def count_chunk(self, points: int) -> None:
        """Record that a chunk of ``points`` points was submitted."""
        if not self.enabled:
            return

        self.chunks += 1
        self.points += points

    @property
    def accounted_s(self) -> float:
        """Sum of the four disjoint activity categories.

        :attr:`starved_s` is deliberately excluded: it classifies time already
        counted elsewhere rather than adding a category.
        """
        return self.generate_s + self.submit_s + self.wait_s + self.write_s

    @property
    def unaccounted_s(self) -> float:
        """Measured region time not charged to any category, floored at zero."""
        return max(0.0, self.elapsed_s - self.accounted_s)

    def summary(self) -> str:
        """Render a human-readable attribution table.

        Percentages are of :attr:`elapsed_s`. The activity rows sum to
        :attr:`accounted_s`; ``starved`` is printed separately below a rule
        because it re-classifies that same time.
        """

        def line(label: str, seconds: float, *, indent: int = 2) -> str:
            share = f"{100.0 * seconds / self.elapsed_s:5.1f}%" if self.elapsed_s > 0.0 else "    --"
            # Widen/narrow the label field by the indent so the numeric columns
            # stay aligned across differently-indented rows.
            return f"{'':<{indent}}{label:<{20 - indent}}{seconds:9.2f}s {share}"

        return "\n".join(
            [
                f"dispatch timings: {self.points} point(s) in {self.chunks} chunk(s), {self.elapsed_s:.2f}s wall clock",
                line("generate", self.generate_s),
                line("submit", self.submit_s),
                line("wait", self.wait_s),
                line("write", self.write_s),
                line("unaccounted", self.unaccounted_s),
                "  -- of the above, with fewer chunks outstanding than workers --",
                line("starved", self.starved_s),
            ],
        )


__all__ = ["DispatchTimings"]
