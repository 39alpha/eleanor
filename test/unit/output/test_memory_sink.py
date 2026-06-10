from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output import ComputeResult, ErrorInfo, WriteOutcome
from eleanor.output.memory import MemorySink, MemorySinkSettings
from eleanor.variable_space import Point


def _order(*, order_id: int | None = None, eleanor_version: str | None = None) -> Order:
    return cast(
        Order,
        cast(
            object,
            SimpleNamespace(
                id=order_id,
                eleanor_version=eleanor_version,
                vs_points=[],
            ),
        ),
    )


def _point(*, exit_code: int = 0, order_id: int | None = None) -> Point:
    return cast(
        Point, cast(object, SimpleNamespace(exit_code=exit_code, order_id=order_id))
    )


class TestMemorySink(TestCase):
    def test_supports_worker_writes_defaults_to_false(self) -> None:
        """Ensure MemorySink defaults to no worker-side writes when config is omitted."""
        self.assertFalse(MemorySink().supports_worker_writes())

    def test_supports_worker_writes_respects_config_true(self) -> None:
        """Ensure MemorySink reports worker-write support when config enables it."""
        config = MemorySinkSettings(support_worker_writes=True)
        self.assertTrue(MemorySink(config).supports_worker_writes())

    def test_supports_worker_writes_respects_config_false(self) -> None:
        """Ensure MemorySink denies worker-write support when config disables it."""
        config = MemorySinkSettings(support_worker_writes=False)
        self.assertFalse(MemorySink(config).supports_worker_writes())

    def test_memory_config_rejects_non_bool(self) -> None:
        """Ensure MemorySinkSettings raises on non-boolean support_worker_writes."""
        with self.assertRaisesRegex(
            EleanorError, "support_worker_writes must be a boolean"
        ):
            _ = MemorySinkSettings(support_worker_writes="yes")  # pyright: ignore[reportArgumentType]

    def test_memory_config_from_dict_defaults(self) -> None:
        """Ensure MemorySinkSettings.from_dict defaults support_worker_writes to False."""
        config = MemorySinkSettings.from_dict({})
        self.assertFalse(config.support_worker_writes)

    def test_supports_progress_returns_true(self) -> None:
        """Ensure MemorySink opts in to sink-side output progress ticks."""
        self.assertTrue(MemorySink().supports_progress())

    def test_begin_run_assigns_sequential_ids_when_order_id_is_none(self) -> None:
        """Ensure begin_run allocates sequential ids for caller-unspecified orders."""
        sink = MemorySink()
        first = _order()
        second = _order()

        first_id = sink.begin_run(first)
        second_id = sink.begin_run(second)

        self.assertEqual(first_id, 0)
        self.assertEqual(second_id, 1)
        self.assertEqual(first.id, 0)
        self.assertEqual(second.id, 1)

    def test_begin_run_respects_caller_supplied_order_id(self) -> None:
        """Ensure begin_run uses a caller-supplied order id and resumes implicit ids from max+1."""
        sink = MemorySink()
        explicit = _order(order_id=42)
        explicit_id = sink.begin_run(explicit)
        self.assertEqual(explicit_id, 42)
        self.assertEqual(explicit.id, 42)

        implicit = _order()
        implicit_id = sink.begin_run(implicit)
        self.assertEqual(implicit_id, 43)

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

    def test_begin_run_allows_version_mismatch_for_existing_order_id(self) -> None:
        """Ensure begin_run permits caller version changes when reusing an order id."""
        sink = MemorySink()
        first = _order(order_id=7, eleanor_version="v1")
        _ = sink.begin_run(first)
        mismatch = _order(order_id=7, eleanor_version="v2")

        order_id = sink.begin_run(mismatch)
        self.assertEqual(order_id, 7)
        self.assertEqual(mismatch.eleanor_version, "v2")

    def test_write_batch_appends_points_to_order(self) -> None:
        """Ensure write_batch appends successful points to the registered order in input order."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        first = _point(exit_code=0)
        second = _point(exit_code=1)

        _ = sink.write_batch(
            order_id,
            [ComputeResult(point=first), ComputeResult(point=second)],
        )

        self.assertEqual(order.vs_points, [first, second])

    def test_write_batch_stamps_order_id_on_each_point(self) -> None:
        """Ensure write_batch overwrites each point's order_id with the batch order id."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        point = _point(exit_code=0, order_id=None)

        _ = sink.write_batch(order_id, [ComputeResult(point=point)])

        self.assertEqual(point.order_id, order_id)

    def test_write_batch_returns_committed_outcomes(self) -> None:
        """Ensure successful writes return committed outcomes with source exit codes."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        first = _point(exit_code=0)
        second = _point(exit_code=3)

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

    def test_write_batch_treats_error_results_as_committed_points(self) -> None:
        """Ensure write_batch treats ComputeResult.error entries as committed point writes."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)
        point = _point(exit_code=7)
        error = ErrorInfo(
            type_name="RuntimeError", message="boom", traceback_text="trace"
        )

        outcomes = sink.write_batch(
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
            _ = sink.write_batch(1, [ComputeResult(point=point)])

    def test_write_batch_empty_results_is_noop(self) -> None:
        """Ensure writing an empty batch returns no outcomes and does not mutate order points."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)

        outcomes = sink.write_batch(order_id, [])

        self.assertEqual(outcomes, [])
        self.assertEqual(order.vs_points, [])

    def test_write_batch_outcomes_are_independent_per_order(self) -> None:
        """Ensure writes for different orders produce committed outcomes in both orders."""
        sink = MemorySink()
        first_order = _order()
        second_order = _order()
        first_order_id = sink.begin_run(first_order)
        second_order_id = sink.begin_run(second_order)

        first_outcome = sink.write_batch(
            first_order_id, [ComputeResult(point=_point())]
        )
        second_outcome = sink.write_batch(
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

        _ = sink.write_batch(
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
