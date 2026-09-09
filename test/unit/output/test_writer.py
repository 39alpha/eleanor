import threading
import time
from collections.abc import Sequence
from typing import override
from unittest import TestCase

from eleanor.output.interface import AbstractOutputSink, ComputeResult, WriteOutcome
from eleanor.output.writer import BackgroundWriter


class _RecordingSink(AbstractOutputSink):
    """Sink that records the thread and payload of every commit."""

    def __init__(self, *, delay: float = 0.0, fail_on: object = None) -> None:
        self.delay = delay
        self.fail_on = fail_on
        self.commits: list[Sequence[object]] = []
        self.threads: list[str] = []

    @override
    def begin_run(self, order: object) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        _ = order
        return 0

    @override
    def prepare_batch(self, order_id: int, results: Sequence[ComputeResult]) -> Sequence[object]:
        _ = order_id
        return list(results)

    @override
    def commit_batch(
        self,
        order_id: int,
        prepared: Sequence[object],
        progress: object = None,
    ) -> list[WriteOutcome]:
        _ = (order_id, progress)
        if self.delay:
            time.sleep(self.delay)
        self.threads.append(threading.current_thread().name)
        if self.fail_on is not None and self.fail_on in prepared:
            msg = f"refusing to commit {self.fail_on!r}"
            raise RuntimeError(msg)
        self.commits.append(prepared)
        return [WriteOutcome(exit_code=0, committed=True) for _ in prepared]

    @override
    def finalize_run(self) -> None:
        return None


class TestBackgroundWriterCommits(TestCase):
    """The writer must commit everything, in order, off the calling thread."""

    def test_commits_run_on_the_writer_thread_not_the_caller(self) -> None:
        sink = _RecordingSink()
        caller = threading.current_thread().name

        with BackgroundWriter(sink, 7, depth=4) as writer:
            writer.submit(["a"])

        self.assertEqual(sink.commits, [["a"]])
        self.assertEqual(len(sink.threads), 1)
        self.assertNotEqual(sink.threads[0], caller)

    def test_payloads_commit_in_submission_order(self) -> None:
        """FIFO order is what keeps outcomes lined up with their chunks."""
        sink = _RecordingSink()

        with BackgroundWriter(sink, 7, depth=2) as writer:
            for index in range(20):
                writer.submit([index])

        self.assertEqual(sink.commits, [[index] for index in range(20)])

    def test_join_returns_every_outcome(self) -> None:
        sink = _RecordingSink()
        writer = BackgroundWriter(sink, 7, depth=4)
        writer.start()
        writer.submit(["a", "b"])
        writer.submit(["c"])

        outcomes = writer.join()

        self.assertEqual(len(outcomes), 3)
        self.assertTrue(all(o.committed for o in outcomes))

    def test_join_is_idempotent(self) -> None:
        sink = _RecordingSink()
        writer = BackgroundWriter(sink, 7, depth=2)
        writer.start()
        writer.submit(["a"])

        first = writer.join()
        second = writer.join()

        self.assertEqual(len(first), 1)
        self.assertIs(first, second)

    def test_submit_before_start_is_rejected(self) -> None:
        writer = BackgroundWriter(_RecordingSink(), 7, depth=2)

        with self.assertRaises(RuntimeError):
            writer.submit(["a"])

    def test_start_is_idempotent(self) -> None:
        sink = _RecordingSink()
        writer = BackgroundWriter(sink, 7, depth=2)
        writer.start()
        writer.start()
        writer.submit(["a"])

        _ = writer.join()

        self.assertEqual(sink.commits, [["a"]])


class TestBackgroundWriterBackpressure(TestCase):
    """A full queue must block the producer rather than buffer without bound."""

    def test_submit_blocks_once_the_queue_is_full(self) -> None:
        # A slow sink and a depth of one: the second submit cannot be accepted
        # until the first commit finishes.
        sink = _RecordingSink(delay=0.05)
        writer = BackgroundWriter(sink, 7, depth=1)
        writer.start()

        start = time.perf_counter()
        for index in range(4):
            writer.submit([index])
        elapsed = time.perf_counter() - start
        _ = writer.join()

        self.assertEqual(len(sink.commits), 4)
        # Four commits at 50ms cannot all have been absorbed instantly; if
        # submit were non-blocking this would be ~0.
        self.assertGreater(elapsed, 0.05)


class TestBackgroundWriterFailures(TestCase):
    """A commit failure must surface, and must not wedge the producer."""

    def test_a_commit_failure_surfaces_from_join(self) -> None:
        sink = _RecordingSink(fail_on="bad")
        writer = BackgroundWriter(sink, 7, depth=4)
        writer.start()
        writer.submit(["bad"])

        with self.assertRaisesRegex(RuntimeError, "refusing to commit"):
            _ = writer.join()

    def test_a_commit_failure_surfaces_from_a_later_submit(self) -> None:
        """The dispatch loop should learn about it without waiting for join."""
        sink = _RecordingSink(fail_on="bad")
        writer = BackgroundWriter(sink, 7, depth=4)
        writer.start()
        writer.submit(["bad"])

        # The failure is asynchronous, so retry until submit reports it.
        deadline = time.perf_counter() + 2.0
        error: RuntimeError | None = None
        while error is None and time.perf_counter() < deadline:
            try:
                writer.submit(["next"])
            except RuntimeError as caught:
                error = caught
            else:
                time.sleep(0.005)

        writer.abort()
        self.assertIsNotNone(error, "submit never surfaced the commit failure")
        self.assertIn("refusing to commit", str(error))

    def test_a_failed_writer_keeps_draining_so_submit_cannot_deadlock(self) -> None:
        """After a failure the thread must consume without committing.

        If it stopped consuming, a producer blocked on a full queue would
        never be released and the run would hang instead of failing.
        """
        sink = _RecordingSink(fail_on="bad")
        writer = BackgroundWriter(sink, 7, depth=1)
        writer.start()
        writer.submit(["bad"])

        # Far more submits than the queue can hold. These must not block
        # forever; a raise from submit is a fine outcome, a hang is not.
        def flood() -> None:
            try:
                for index in range(50):
                    writer.submit([index])
            except RuntimeError:
                pass

        flooder = threading.Thread(target=flood)
        flooder.start()
        flooder.join(timeout=5.0)

        self.assertFalse(flooder.is_alive(), "submit deadlocked after a commit failure")
        writer.abort()

    def test_abort_does_not_raise_a_stashed_failure(self) -> None:
        """Teardown paths already have an exception in flight."""
        sink = _RecordingSink(fail_on="bad")
        writer = BackgroundWriter(sink, 7, depth=4)
        writer.start()
        writer.submit(["bad"])

        writer.abort()  # must not raise

    def test_context_manager_aborts_on_an_exception_and_does_not_mask_it(self) -> None:
        sink = _RecordingSink(fail_on="bad")

        with self.assertRaisesRegex(ValueError, "original"):
            with BackgroundWriter(sink, 7, depth=4) as writer:
                writer.submit(["bad"])
                msg = "original"
                raise ValueError(msg)


class TestBackgroundWriterAbort(TestCase):
    """Abort must stop promptly, even with a full queue."""

    def test_abort_discards_queued_payloads(self) -> None:
        sink = _RecordingSink(delay=0.05)
        writer = BackgroundWriter(sink, 7, depth=8)
        writer.start()
        for index in range(8):
            writer.submit([index])

        writer.abort()

        # Whatever was in flight may land; the rest must be dropped rather
        # than committed on the way out.
        self.assertLess(len(sink.commits), 8)

    def test_abort_is_idempotent_and_safe_before_start(self) -> None:
        writer = BackgroundWriter(_RecordingSink(), 7, depth=2)
        writer.abort()
        writer.start()
        writer.abort()
        writer.abort()


class TestBackgroundWriterJoinDoesNotDropWork(TestCase):
    """A clean join must commit everything queued, however backed up.

    Regression test. ``join`` originally shared its sentinel delivery with
    ``abort``, which discards queued payloads to guarantee the sentinel gets
    through. On the join path that silently dropped uncommitted work whenever
    the queue happened to be full -- which is exactly when the sink is slow,
    i.e. the case the writer exists to serve.
    """

    def test_a_full_queue_at_join_still_commits_every_payload(self) -> None:
        # Depth of one guarantees the queue is occupied at join. The delay has
        # to exceed the abort path's sentinel timeout (50ms) or the old code
        # made room in time and dropped nothing -- a sink this slow is the
        # normal case here, not a contrivance.
        sink = _RecordingSink(delay=0.2)
        writer = BackgroundWriter(sink, 7, depth=1)
        writer.start()
        for index in range(4):
            writer.submit([index])

        outcomes = writer.join()

        self.assertEqual(sink.commits, [[index] for index in range(4)])
        self.assertEqual(len(outcomes), 4)

    def test_context_manager_exit_also_commits_everything(self) -> None:
        sink = _RecordingSink(delay=0.2)

        with BackgroundWriter(sink, 7, depth=1) as writer:
            for index in range(4):
                writer.submit([index])

        self.assertEqual(len(sink.commits), 4)
