from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output import ComputeResult, WriteOutcome
from eleanor.output.null import NullSink, NullSinkSettings
from eleanor.variable_space import Point


def _order(*, order_id: int | None = None, eleanor_version: str | None = None) -> Order:
    return cast(
        Order,
        cast(object, SimpleNamespace(id=order_id, eleanor_version=eleanor_version)),
    )


def _point(*, exit_code: int = 0, order_id: int | None = None) -> Point:
    return cast(
        Point, cast(object, SimpleNamespace(exit_code=exit_code, order_id=order_id))
    )


class TestNullSink(TestCase):
    def test_supports_worker_writes_reflects_config(self) -> None:
        """Ensure NullSink worker-write capability mirrors the config flag."""
        self.assertFalse(
            NullSink(
                NullSinkSettings(support_worker_writes=False)
            ).supports_worker_writes()
        )
        self.assertTrue(
            NullSink(
                NullSinkSettings(support_worker_writes=True)
            ).supports_worker_writes()
        )

    def test_supports_progress_returns_true(self) -> None:
        """Ensure NullSink opts in to sink-side output progress ticks."""
        self.assertTrue(
            NullSink(NullSinkSettings(support_worker_writes=False)).supports_progress()
        )

    def test_null_config_rejects_non_boolean_worker_write_flag(self) -> None:
        """Ensure NullSinkSettings validates support_worker_writes as a strict boolean."""
        with self.assertRaisesRegex(
            EleanorError, "support_worker_writes must be a boolean"
        ):
            _ = NullSinkSettings(support_worker_writes="yes")  # pyright: ignore[reportArgumentType]

    def test_null_config_from_dict_defaults_and_reads_flag(self) -> None:
        """Ensure NullSinkSettings.from_dict defaults to false and accepts an explicit bool."""
        self.assertFalse(NullSinkSettings.from_dict({}).support_worker_writes)
        self.assertTrue(
            NullSinkSettings.from_dict(
                {"support_worker_writes": True}
            ).support_worker_writes
        )

    def test_begin_run_assigns_sequential_ids_for_implicit_orders(self) -> None:
        """Ensure begin_run allocates sequential ids when orders have no id."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))
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
        sink = NullSink(NullSinkSettings(support_worker_writes=False))

        order = _order(eleanor_version="custom-v1")
        _ = sink.begin_run(order)  # type: ignore[arg-type]
        self.assertEqual(order.eleanor_version, "custom-v1")

    def test_begin_run_respects_explicit_ids_and_does_not_rewind_allocator(
        self,
    ) -> None:
        """Ensure explicit ids are accepted and lower explicit ids do not lower the implicit counter."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))

        high = _order(order_id=42)
        self.assertEqual(sink.begin_run(high), 42)  # type: ignore[arg-type]

        low = _order(order_id=3)
        self.assertEqual(sink.begin_run(low), 3)  # type: ignore[arg-type]

        implicit = _order()
        self.assertEqual(sink.begin_run(implicit), 43)  # type: ignore[arg-type]

    def test_write_batch_raises_before_begin_run(self) -> None:
        """Ensure write_batch requires begin_run before accepting writes."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))
        result = ComputeResult(point=_point())

        with self.assertRaisesRegex(EleanorError, "called before begin_run"):
            _ = sink.write_batch(1, [result])  # type: ignore[arg-type]

    def test_write_batch_raises_for_non_active_order_id(self) -> None:
        """Ensure write_batch rejects writes for an order id different from the active run."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))
        active_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        wrong_order_id = active_order_id + 1

        with self.assertRaisesRegex(EleanorError, "called before begin_run"):
            _ = sink.write_batch(wrong_order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]

    def test_write_batch_returns_committed_outcomes_and_stamps_points(self) -> None:
        """Ensure write_batch marks outcomes committed and overwrites each point's order_id."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        first = _point(exit_code=0, order_id=None)
        second = _point(exit_code=3, order_id=999)

        outcomes = sink.write_batch(
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
        self.assertEqual(first.order_id, order_id)
        self.assertEqual(second.order_id, order_id)

    def test_write_batch_commits_results_across_orders(self) -> None:
        """Ensure NullSink reports committed outcomes across multiple runs."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))

        first_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        first_outcomes = sink.write_batch(
            first_order_id, [ComputeResult(point=_point())]
        )

        sink.finalize_run()

        second_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        second_outcomes = sink.write_batch(
            second_order_id, [ComputeResult(point=_point())]
        )
        self.assertTrue(first_outcomes[0].committed)
        self.assertTrue(second_outcomes[0].committed)

    def test_write_batch_ticks_progress_for_each_result(self) -> None:
        """Ensure write_batch emits one progress tick per committed result."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        progress = mock.Mock()

        _ = sink.write_batch(
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
        sink = NullSink(NullSinkSettings(support_worker_writes=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        progress = mock.Mock()

        outcomes = sink.write_batch(order_id, [], progress=progress)

        self.assertEqual(outcomes, [])
        progress.tick.assert_not_called()

    def test_finalize_run_requires_new_begin_run_before_next_write(self) -> None:
        """Ensure finalize_run clears active-run state so writes require a subsequent begin_run."""
        sink = NullSink(NullSinkSettings(support_worker_writes=False))
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        sink.finalize_run()

        with self.assertRaisesRegex(EleanorError, "called before begin_run"):
            _ = sink.write_batch(order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]

        self.assertEqual(sink.begin_run(order), order_id)  # type: ignore[arg-type]
        outcomes = sink.write_batch(
            order_id, [ComputeResult(point=_point(exit_code=1))]
        )
        self.assertTrue(outcomes[0].committed)

    def test_import_from_submodule(self) -> None:
        """Ensure eleanor.output.null.NullSink is importable directly."""
        from eleanor.output.null import NullSink as _NullSink

        self.assertIs(_NullSink, NullSink)
