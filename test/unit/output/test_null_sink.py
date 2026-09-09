from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output import ComputeResult, WriteOutcome
from eleanor.output.null import NullSink, NullSinkSettings
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

def _order(*, order_id: int | None = None, eleanor_version: str | None = None) -> Order:
    return cast(
        Order,
        cast(object, SimpleNamespace(id=order_id, eleanor_version=eleanor_version)),
    )


def _point(*, exit_code: int = 0) -> Point:
    return cast(Point, cast(object, SimpleNamespace(exit_code=exit_code)))


class TestNullSink(TestCase):
    def test_supports_worker_commit_reflects_config(self) -> None:
        """Ensure NullSink worker-write capability mirrors the config flag."""
        self.assertFalse(
            NullSink(
                NullSinkSettings(support_worker_commit=False)
            ).supports_worker_commit()
        )
        self.assertTrue(
            NullSink(
                NullSinkSettings(support_worker_commit=True)
            ).supports_worker_commit()
        )

    def test_supports_progress_returns_true(self) -> None:
        """Ensure NullSink opts in to sink-side output progress ticks."""
        self.assertTrue(
            NullSink(NullSinkSettings(support_worker_commit=False)).supports_progress()
        )

    def test_null_config_rejects_non_boolean_worker_write_flag(self) -> None:
        """Ensure NullSinkSettings validates support_worker_commit as a strict boolean."""
        with self.assertRaisesRegex(
            EleanorError, "support_worker_commit must be a boolean"
        ):
            _ = NullSinkSettings(support_worker_commit="yes")  # pyright: ignore[reportArgumentType]

    def test_null_config_from_dict_defaults_and_reads_flag(self) -> None:
        """Ensure NullSinkSettings.from_dict defaults to false and accepts an explicit bool."""
        self.assertFalse(NullSinkSettings.from_dict({}).support_worker_commit)
        self.assertTrue(
            NullSinkSettings.from_dict(
                {"support_worker_commit": True}
            ).support_worker_commit
        )

    def test_begin_run_assigns_sequential_ids_for_implicit_orders(self) -> None:
        """Ensure begin_run allocates sequential ids when orders have no id."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        first = _order()
        second = _order()

        first_id = sink.begin_run(first)  # type: ignore[arg-type]
        second_id = sink.begin_run(second)  # type: ignore[arg-type]

        self.assertEqual(first_id, 0)
        self.assertEqual(second_id, 1)
        self.assertEqual(first.id, 0)
        self.assertEqual(second.id, 1)

    def test_begin_run_stamps_preserves_supplied_version(self) -> None:
        """Ensure begin_run stamps missing versions and preserves caller-provided values."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))

        order = _order(eleanor_version="custom-v1")
        _ = sink.begin_run(order)  # type: ignore[arg-type]
        self.assertEqual(order.eleanor_version, "custom-v1")

    def test_begin_run_respects_explicit_ids_and_does_not_rewind_allocator(
        self,
    ) -> None:
        """Ensure explicit ids are accepted and lower explicit ids do not lower the implicit counter."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))

        high = _order(order_id=42)
        self.assertEqual(sink.begin_run(high), 42)  # type: ignore[arg-type]

        low = _order(order_id=3)
        self.assertEqual(sink.begin_run(low), 3)  # type: ignore[arg-type]

        implicit = _order()
        self.assertEqual(sink.begin_run(implicit), 43)  # type: ignore[arg-type]

    def test_write_batch_raises_before_begin_run(self) -> None:
        """Ensure write_batch requires begin_run before accepting writes."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        result = ComputeResult(point=_point())

        with self.assertRaisesRegex(EleanorError, "called before begin_run"):
            _ = _write_batch(sink, 1, [result])  # type: ignore[arg-type]

    def test_write_batch_raises_for_non_active_order_id(self) -> None:
        """Ensure write_batch rejects writes for an order id different from the active run."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        active_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        wrong_order_id = active_order_id + 1

        with self.assertRaisesRegex(EleanorError, "called before begin_run"):
            _ = _write_batch(sink, wrong_order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]

    def test_write_batch_returns_committed_outcomes(self) -> None:
        """Ensure write_batch marks every outcome committed with its source exit code."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
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

    def test_write_batch_commits_results_across_orders(self) -> None:
        """Ensure NullSink reports committed outcomes across multiple runs."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))

        first_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        first_outcomes = _write_batch(sink,
            first_order_id, [ComputeResult(point=_point())]
        )

        sink.finalize_run()

        second_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        second_outcomes = _write_batch(sink,
            second_order_id, [ComputeResult(point=_point())]
        )
        self.assertTrue(first_outcomes[0].committed)
        self.assertTrue(second_outcomes[0].committed)

    def test_write_batch_ticks_progress_for_each_result(self) -> None:
        """Ensure write_batch emits one progress tick per committed result."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        progress = mock.Mock()

        _ = _write_batch(sink,
            order_id,
            [
                ComputeResult(point=_point(exit_code=0)),
                ComputeResult(point=_point(exit_code=5)),
            ],
            progress=progress,
        )

        self.assertEqual(progress.tick.call_count, 2)

    def test_write_batch_empty_results_is_noop(self) -> None:
        """Ensure writing an empty batch returns no outcomes and emits no ticks."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        progress = mock.Mock()

        outcomes = _write_batch(sink, order_id, [], progress=progress)

        self.assertEqual(outcomes, [])
        progress.tick.assert_not_called()

    def test_finalize_run_requires_new_begin_run_before_next_write(self) -> None:
        """Ensure finalize_run clears active-run state so writes require a subsequent begin_run."""
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        sink.finalize_run()

        with self.assertRaisesRegex(EleanorError, "called before begin_run"):
            _ = _write_batch(sink, order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]

        self.assertEqual(sink.begin_run(order), order_id)  # type: ignore[arg-type]
        outcomes = _write_batch(sink,
            order_id, [ComputeResult(point=_point(exit_code=1))]
        )
        self.assertTrue(outcomes[0].committed)

    def test_import_from_submodule(self) -> None:
        """Ensure eleanor.output.null.NullSink is importable directly."""
        from eleanor.output.null import NullSink as _NullSink

        self.assertIs(_NullSink, NullSink)
