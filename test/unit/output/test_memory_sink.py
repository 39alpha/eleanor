from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output import ComputeResult, ErrorInfo, WriteOutcome
from eleanor.output.memory import MemorySink, MemorySinkSettings
from eleanor.variable_space import Point



def _write_batch(sink, order_id, results, progress=None):
    """Drive both halves of the split write protocol, as Eleanor does.

    ``prepare_batch`` runs in a worker and ``commit_batch`` in the parent, but
    for a test the pair is one logical "write this batch", so most cases are
    clearer expressed through this helper than by threading the prepared
    payload by hand.
    """
    prepared = sink.prepare_batch(order_id, results)
    return sink.commit_batch(order_id, prepared, progress=progress)

def _order(*, eleanor_version: str | None = None) -> Order:
    return cast(
        Order,
        cast(
            object,
            SimpleNamespace(eleanor_version=eleanor_version, vs_points=[]),
        ),
    )


def _point(*, exit_code: int = 0) -> Point:
    return cast(Point, cast(object, SimpleNamespace(exit_code=exit_code)))


class TestMemorySink(TestCase):
    def test_supports_worker_commit_defaults_to_false(self) -> None:
        """Ensure MemorySink defaults to no worker-side writes when config is omitted."""
        self.assertFalse(MemorySink().supports_worker_commit())

    def test_supports_worker_commit_respects_config_true(self) -> None:
        """Ensure MemorySink reports worker-write support when config enables it."""
        config = MemorySinkSettings(support_worker_commit=True)
        self.assertTrue(MemorySink(config).supports_worker_commit())

    def test_supports_worker_commit_respects_config_false(self) -> None:
        """Ensure MemorySink denies worker-write support when config disables it."""
        config = MemorySinkSettings(support_worker_commit=False)
        self.assertFalse(MemorySink(config).supports_worker_commit())

    def test_memory_config_rejects_non_bool(self) -> None:
        """Ensure MemorySinkSettings raises on non-boolean support_worker_commit."""
        with self.assertRaisesRegex(
            EleanorError, "support_worker_commit must be a boolean"
        ):
            _ = MemorySinkSettings(support_worker_commit="yes")  # pyright: ignore[reportArgumentType]

    def test_memory_config_from_dict_defaults(self) -> None:
        """Ensure MemorySinkSettings.from_dict defaults support_worker_commit to False."""
        config = MemorySinkSettings.from_dict({})
        self.assertFalse(config.support_worker_commit)

    def test_supports_progress_returns_true(self) -> None:
        """Ensure MemorySink opts in to sink-side output progress ticks."""
        self.assertTrue(MemorySink().supports_progress())

    def test_begin_run_assigns_sequential_ids(self) -> None:
        """Ensure begin_run allocates sequential ids for successive orders."""
        sink = MemorySink()
        first_id = sink.begin_run(_order())
        second_id = sink.begin_run(_order())

        self.assertEqual(first_id, 0)
        self.assertEqual(second_id, 1)

    def test_begin_run_resumes_a_requested_id_it_holds(self) -> None:
        """Ensure a requested_id for a registered order resumes that order."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)

        resumed = sink.begin_run(_order(), requested_id=str(order_id))

        self.assertEqual(resumed, order_id)
        # The resumed run keeps the order object it was registered with, so
        # committed points still land on the retained graph.
        self.assertIs(sink._orders[order_id], order)

    def test_begin_run_rejects_a_requested_id_it_does_not_hold(self) -> None:
        """Ensure an unknown id is an error: a fresh sink has nothing to extend.

        The retained graph lives only in this instance, so there is no store
        to look a previous run up in.
        """
        sink = MemorySink()

        with self.assertRaisesRegex(EleanorError, "no order 42 to extend"):
            _ = sink.begin_run(_order(), requested_id="42")

        with self.assertRaisesRegex(EleanorError, "must be an integer"):
            _ = sink.begin_run(_order(), requested_id="not-an-int")

    def test_begin_run_is_idempotent(self) -> None:
        """Ensure begin_run returns the same id and keeps sink state stable for the same object."""
        sink = MemorySink()
        order = _order()

        first_id = sink.begin_run(order)
        orders_after_first = dict(sink._orders)
        second_id = sink.begin_run(order)

        self.assertEqual(first_id, second_id)
        self.assertEqual(sink._orders, orders_after_first)

    def test_begin_run_preserves_caller_supplied_eleanor_version(self) -> None:
        """Ensure begin_run keeps caller-supplied eleanor_version values unchanged."""
        sink = MemorySink()
        order = _order(eleanor_version="custom-v1")

        _ = sink.begin_run(order)
        self.assertEqual(order.eleanor_version, "custom-v1")

    def test_begin_run_allows_version_mismatch_when_resuming(self) -> None:
        """Ensure this sink does not gate resumption on the Eleanor version.

        Unlike the durable sinks, nothing here outlives the process, so there
        is no old-format data for a version change to invalidate.
        """
        sink = MemorySink()
        order_id = sink.begin_run(_order(eleanor_version="v1"))
        mismatch = _order(eleanor_version="v2")

        resumed = sink.begin_run(mismatch, requested_id=str(order_id))

        self.assertEqual(resumed, order_id)
        self.assertEqual(mismatch.eleanor_version, "v2")

    def test_write_batch_appends_points_to_order(self) -> None:
        """Ensure write_batch appends successful points to the registered order in input order."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        first = _point(exit_code=0)
        second = _point(exit_code=1)

        _ = _write_batch(sink,
            order_id,
            [ComputeResult(point=first), ComputeResult(point=second)],
        )

        self.assertEqual(order.vs_points, [first, second])

    def test_write_batch_returns_committed_outcomes(self) -> None:
        """Ensure successful writes return committed outcomes with source exit codes."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        first = _point(exit_code=0)
        second = _point(exit_code=3)

        outcomes = _write_batch(sink,
            order_id,
            [ComputeResult(point=first), ComputeResult(point=second)],
        )

        self.assertEqual(
            outcomes,
            [
                WriteOutcome(exit_code=0, committed=True),
                WriteOutcome(exit_code=3, committed=True),
            ],
        )

    def test_write_batch_treats_error_results_as_committed_points(self) -> None:
        """Ensure write_batch treats ComputeResult.error entries as committed point writes."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        point = _point(exit_code=7)
        error = ErrorInfo(
            type_name="RuntimeError", message="boom", traceback_text="trace"
        )

        outcomes = _write_batch(sink,
            order_id,
            [ComputeResult(point=point, error=error)],
        )

        self.assertEqual(
            outcomes,
            [
                WriteOutcome(
                    exit_code=7,
                    committed=True,
                )
            ],
        )
        self.assertEqual(order.vs_points, [point])

    def test_write_batch_raises_before_begin_run(self) -> None:
        """Ensure write_batch requires begin_run registration before writing any points."""
        sink = MemorySink()
        point = _point(exit_code=0)

        with self.assertRaisesRegex(EleanorError, "called before begin_run"):
            _ = _write_batch(sink, 1, [ComputeResult(point=point)])

    def test_write_batch_empty_results_is_noop(self) -> None:
        """Ensure writing an empty batch returns no outcomes and does not mutate order points."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)

        outcomes = _write_batch(sink, order_id, [])

        self.assertEqual(outcomes, [])
        self.assertEqual(order.vs_points, [])

    def test_write_batch_outcomes_are_independent_per_order(self) -> None:
        """Ensure writes for different orders produce committed outcomes in both orders."""
        sink = MemorySink()
        first_order = _order()
        second_order = _order()
        first_order_id = sink.begin_run(first_order)
        second_order_id = sink.begin_run(second_order)

        first_outcome = _write_batch(sink,
            first_order_id, [ComputeResult(point=_point())]
        )
        second_outcome = _write_batch(sink,
            second_order_id, [ComputeResult(point=_point())]
        )
        self.assertTrue(first_outcome[0].committed)
        self.assertTrue(second_outcome[0].committed)

    def test_write_batch_ticks_progress_for_each_point(self) -> None:
        """Ensure write_batch emits one progress tick for each committed point."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        progress = mock.Mock()

        _ = _write_batch(sink,
            order_id,
            [
                ComputeResult(point=_point(exit_code=0)),
                ComputeResult(point=_point(exit_code=1)),
            ],
            progress=progress,
        )
        self.assertEqual(progress.tick.call_count, 2)

    def test_finalize_run_is_noop(self) -> None:
        """Ensure finalize_run is a no-op for in-memory output state."""
        MemorySink().finalize_run()

    def test_import_from_submodule(self) -> None:
        """Ensure eleanor.output.memory.MemorySink is importable directly."""
        from eleanor.output.memory import MemorySink as _MemorySink

        self.assertIs(_MemorySink, MemorySink)
