from types import SimpleNamespace
from typing import cast
from unittest import mock

from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.order import Order
from eleanor.output import ComputeResult, ErrorInfo, MemorySink, WriteOutcome
from eleanor.output.memory import MemoryConfig
from eleanor.variable_space import Point

from .common import TestCase


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
    return cast(Point, cast(object, SimpleNamespace(exit_code=exit_code, order_id=order_id)))


class TestMemorySink(TestCase):
    def test_supports_worker_writes_defaults_to_false(self):
        """Ensure MemorySink defaults to no worker-side writes when config is omitted."""
        self.assertFalse(MemorySink().supports_worker_writes())

    def test_supports_worker_writes_respects_config_true(self):
        """Ensure MemorySink reports worker-write support when config enables it."""
        config = MemoryConfig(support_worker_writes=True)
        self.assertTrue(MemorySink(config).supports_worker_writes())

    def test_supports_worker_writes_respects_config_false(self):
        """Ensure MemorySink denies worker-write support when config disables it."""
        config = MemoryConfig(support_worker_writes=False)
        self.assertFalse(MemorySink(config).supports_worker_writes())

    def test_memory_config_rejects_non_bool(self):
        """Ensure MemoryConfig raises on non-boolean support_worker_writes."""
        with self.assertRaises(EleanorConfigurationException):
            MemoryConfig(support_worker_writes="yes")

    def test_memory_config_from_raw_defaults(self):
        """Ensure MemoryConfig.from_raw defaults support_worker_writes to False."""
        config = MemoryConfig.from_raw({})
        self.assertFalse(config.support_worker_writes)

    def test_supports_progress_returns_true(self):
        """Ensure MemorySink opts in to sink-side output progress ticks."""
        self.assertTrue(MemorySink().supports_progress())

    def test_begin_run_assigns_sequential_ids_when_order_id_is_none(self):
        """Ensure begin_run allocates sequential ids for caller-unspecified orders."""
        sink = MemorySink()
        first = _order()
        second = _order()

        first_id = sink.begin_run(first)  # type: ignore[arg-type]
        second_id = sink.begin_run(second)  # type: ignore[arg-type]

        self.assertEqual(first_id, 0)
        self.assertEqual(second_id, 1)
        self.assertEqual(first.id, 0)
        self.assertEqual(second.id, 1)

    def test_begin_run_respects_caller_supplied_order_id(self):
        """Ensure begin_run uses a caller-supplied order id and resumes implicit ids from max+1."""
        sink = MemorySink()
        explicit = _order(order_id=42)
        explicit_id = sink.begin_run(explicit)  # type: ignore[arg-type]
        self.assertEqual(explicit_id, 42)
        self.assertEqual(explicit.id, 42)

        implicit = _order()
        implicit_id = sink.begin_run(implicit)  # type: ignore[arg-type]
        self.assertEqual(implicit_id, 43)

    def test_begin_run_is_idempotent(self):
        """Ensure begin_run returns the same id and keeps sink state stable for the same object."""
        sink = MemorySink()
        order = _order()

        first_id = sink.begin_run(order)  # type: ignore[arg-type]
        orders_after_first = dict(sink._orders)
        second_id = sink.begin_run(order)  # type: ignore[arg-type]

        self.assertEqual(first_id, second_id)
        self.assertEqual(sink._orders, orders_after_first)

    def test_begin_run_preserves_caller_supplied_eleanor_version(self):
        """Ensure begin_run keeps caller-supplied eleanor_version values unchanged."""
        sink = MemorySink()
        order = _order(eleanor_version="custom-v1")

        _ = sink.begin_run(order)  # type: ignore[arg-type]
        self.assertEqual(order.eleanor_version, "custom-v1")

    def test_begin_run_allows_version_mismatch_for_existing_order_id(self):
        """Ensure begin_run permits caller version changes when reusing an order id."""
        sink = MemorySink()
        first = _order(order_id=7, eleanor_version="v1")
        _ = sink.begin_run(first)  # type: ignore[arg-type]
        mismatch = _order(order_id=7, eleanor_version="v2")

        order_id = sink.begin_run(mismatch)  # type: ignore[arg-type]
        self.assertEqual(order_id, 7)
        self.assertEqual(mismatch.eleanor_version, "v2")

    def test_write_batch_appends_points_to_order(self):
        """Ensure write_batch appends successful points to the registered order in input order."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        first = _point(exit_code=0)
        second = _point(exit_code=1)

        _ = sink.write_batch(
            order_id,
            [ComputeResult(point=first), ComputeResult(point=second)],  # type: ignore[arg-type]
        )

        self.assertEqual(order.vs_points, [first, second])

    def test_write_batch_stamps_order_id_on_each_point(self):
        """Ensure write_batch overwrites each point's order_id with the batch order id."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        point = _point(exit_code=0, order_id=None)

        _ = sink.write_batch(order_id, [ComputeResult(point=point)])  # type: ignore[arg-type]

        self.assertEqual(point.order_id, order_id)

    def test_write_batch_returns_committed_outcomes(self):
        """Ensure successful writes return committed outcomes with source exit codes."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        first = _point(exit_code=0)
        second = _point(exit_code=3)

        outcomes = sink.write_batch(
            order_id,
            [ComputeResult(point=first), ComputeResult(point=second)],  # type: ignore[arg-type]
        )

        self.assertEqual(
            outcomes,
            [
                WriteOutcome(exit_code=0, committed=True),
                WriteOutcome(exit_code=3, committed=True),
            ],
        )

    def test_write_batch_treats_error_results_as_committed_points(self):
        """Ensure write_batch treats ComputeResult.error entries as committed point writes."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        point = _point(exit_code=7)
        error = ErrorInfo(type_name="RuntimeError", message="boom", traceback_text="trace")

        outcomes = sink.write_batch(
            order_id,
            [ComputeResult(point=point, error=error)],  # type: ignore[arg-type]
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

    def test_write_batch_raises_before_begin_run(self):
        """Ensure write_batch requires begin_run registration before writing any points."""
        sink = MemorySink()
        point = _point(exit_code=0)

        with self.assertRaisesRegex(EleanorException, "called before begin_run"):
            sink.write_batch(1, [ComputeResult(point=point)])  # type: ignore[arg-type]

    def test_write_batch_empty_results_is_noop(self):
        """Ensure writing an empty batch returns no outcomes and does not mutate order points."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]

        outcomes = sink.write_batch(order_id, [])

        self.assertEqual(outcomes, [])
        self.assertEqual(order.vs_points, [])

    def test_write_batch_outcomes_are_independent_per_order(self):
        """Ensure writes for different orders produce committed outcomes in both orders."""
        sink = MemorySink()
        first_order = _order()
        second_order = _order()
        first_order_id = sink.begin_run(first_order)  # type: ignore[arg-type]
        second_order_id = sink.begin_run(second_order)  # type: ignore[arg-type]

        first_outcome = sink.write_batch(first_order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]
        second_outcome = sink.write_batch(second_order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]
        self.assertTrue(first_outcome[0].committed)
        self.assertTrue(second_outcome[0].committed)

    def test_write_batch_ticks_progress_for_each_point(self):
        """Ensure write_batch emits one progress tick for each committed point."""
        sink = MemorySink()
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        progress = mock.Mock()

        _ = sink.write_batch(
            order_id,
            [
                ComputeResult(point=_point(exit_code=0)),  # type: ignore[arg-type]
                ComputeResult(point=_point(exit_code=1)),  # type: ignore[arg-type]
            ],
            progress=progress,
        )
        self.assertEqual(progress.tick.call_count, 2)

    def test_finalize_run_is_noop(self):
        """Ensure finalize_run is a no-op for in-memory output state."""
        MemorySink().finalize_run()

    def test_lazy_import_from_package(self):
        """Ensure eleanor.output lazy re-export resolves to eleanor.output.memory.MemorySink."""
        from eleanor.output import MemorySink

        self.assertIs(
            MemorySink,
            __import__("eleanor.output.memory", fromlist=["MemorySink"]).MemorySink,
        )
