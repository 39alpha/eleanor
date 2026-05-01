import warnings
from types import SimpleNamespace
from unittest import mock

from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.output import ComputeResult, NullSink, WriteOutcome, _build_null
from eleanor.output.null import NullConfig

from .common import TestCase


def _order(*, order_id: int | None = None, eleanor_version: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=order_id,
        eleanor_version=eleanor_version,
    )


def _point(*, exit_code: int = 0, order_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        exit_code=exit_code,
        order_id=order_id,
    )


class TestNullSink(TestCase):
    def test_supports_worker_writes_reflects_config(self):
        """Ensure NullSink worker-write capability mirrors the config flag."""
        self.assertFalse(NullSink(NullConfig(support_worker_writes=False)).supports_worker_writes())
        self.assertTrue(NullSink(NullConfig(support_worker_writes=True)).supports_worker_writes())

    def test_supports_progress_returns_true(self):
        """Ensure NullSink opts in to sink-side output progress ticks."""
        self.assertTrue(NullSink(NullConfig(support_worker_writes=False)).supports_progress())

    def test_null_config_rejects_non_boolean_worker_write_flag(self):
        """Ensure NullConfig validates support_worker_writes as a strict boolean."""
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.support_worker_writes must be a boolean for output type "null"',
        ):
            NullConfig(support_worker_writes="yes")  # type: ignore[arg-type]

    def test_null_config_from_raw_defaults_and_reads_flag(self):
        """Ensure NullConfig.from_raw defaults to false and accepts an explicit bool."""
        self.assertFalse(NullConfig.from_raw({}).support_worker_writes)
        self.assertTrue(NullConfig.from_raw({"support_worker_writes": True}).support_worker_writes)

    def test_build_null_returns_sink_and_warns_on_unknown_kwargs(self):
        """Ensure _build_null warns once for unknown kwargs and still constructs a sink."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sink = _build_null(
                object(),
                support_worker_writes=True,
                verbose=True,
                ignored_b=True,
                ignored_a=True,
            )

        self.assertIsInstance(sink, NullSink)
        self.assertTrue(sink.supports_worker_writes())
        runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        self.assertEqual(len(runtime_warnings), 1)
        message = str(runtime_warnings[0].message)
        self.assertIn("['ignored_a', 'ignored_b']", message)
        self.assertNotIn("support_worker_writes", message)
        self.assertNotIn("verbose", message)

    def test_build_null_does_not_warn_for_known_kwargs(self):
        """Ensure _build_null emits no RuntimeWarning for known kwargs only."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sink = _build_null(
                object(),
                support_worker_writes=False,
                verbose=False,
            )
        self.assertIsInstance(sink, NullSink)
        runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        self.assertEqual(runtime_warnings, [])

    def test_build_null_rejects_non_boolean_worker_write_flag(self):
        """Ensure _build_null forwards NullConfig validation errors."""
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.support_worker_writes must be a boolean for output type "null"',
        ):
            _build_null(object(), support_worker_writes="yes")  # type: ignore[arg-type]

    def test_begin_run_assigns_sequential_ids_for_implicit_orders(self):
        """Ensure begin_run allocates sequential ids when orders have no id."""
        sink = NullSink(NullConfig(support_worker_writes=False))
        first = _order()
        second = _order()

        first_id = sink.begin_run(first)  # type: ignore[arg-type]
        second_id = sink.begin_run(second)  # type: ignore[arg-type]

        self.assertEqual(first_id, 0)
        self.assertEqual(second_id, 1)
        self.assertEqual(first.id, 0)
        self.assertEqual(second.id, 1)

    def test_begin_run_stamps_missing_version_and_preserves_supplied_version(self):
        """Ensure begin_run stamps missing versions and preserves caller-provided values."""
        sink = NullSink(NullConfig(support_worker_writes=False))

        unstamped = _order()
        _ = sink.begin_run(unstamped)  # type: ignore[arg-type]
        self.assertIsNotNone(unstamped.eleanor_version)

        supplied = _order(eleanor_version="custom-v1")
        _ = sink.begin_run(supplied)  # type: ignore[arg-type]
        self.assertEqual(supplied.eleanor_version, "custom-v1")

    def test_begin_run_respects_explicit_ids_and_does_not_rewind_allocator(self):
        """Ensure explicit ids are accepted and lower explicit ids do not lower the implicit counter."""
        sink = NullSink(NullConfig(support_worker_writes=False))

        high = _order(order_id=42)
        self.assertEqual(sink.begin_run(high), 42)  # type: ignore[arg-type]

        low = _order(order_id=3)
        self.assertEqual(sink.begin_run(low), 3)  # type: ignore[arg-type]

        implicit = _order()
        self.assertEqual(sink.begin_run(implicit), 43)  # type: ignore[arg-type]

    def test_write_batch_raises_before_begin_run(self):
        """Ensure write_batch requires begin_run before accepting writes."""
        sink = NullSink(NullConfig(support_worker_writes=False))
        result = ComputeResult(point=_point())

        with self.assertRaisesRegex(EleanorException, "called before begin_run"):
            sink.write_batch(1, [result])  # type: ignore[arg-type]

    def test_write_batch_raises_for_non_active_order_id(self):
        """Ensure write_batch rejects writes for an order id different from the active run."""
        sink = NullSink(NullConfig(support_worker_writes=False))
        active_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        wrong_order_id = active_order_id + 1

        with self.assertRaisesRegex(EleanorException, "called before begin_run"):
            sink.write_batch(wrong_order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]

    def test_write_batch_returns_committed_outcomes_and_stamps_points(self):
        """Ensure write_batch marks outcomes committed and overwrites each point's order_id."""
        sink = NullSink(NullConfig(support_worker_writes=False))
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
                WriteOutcome(point_id=0, exit_code=0, committed=True),
                WriteOutcome(point_id=1, exit_code=3, committed=True),
            ],
        )
        self.assertEqual(first.order_id, order_id)
        self.assertEqual(second.order_id, order_id)

    def test_write_batch_point_ids_are_global_across_orders(self):
        """Ensure NullSink point ids increment globally across all runs, not per order."""
        sink = NullSink(NullConfig(support_worker_writes=False))

        first_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        first_outcomes = sink.write_batch(first_order_id, [ComputeResult(point=_point())])

        sink.finalize_run()

        second_order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        second_outcomes = sink.write_batch(second_order_id, [ComputeResult(point=_point())])

        self.assertEqual(first_outcomes[0].point_id, 0)
        self.assertEqual(second_outcomes[0].point_id, 1)

    def test_write_batch_ticks_progress_for_each_result(self):
        """Ensure write_batch emits one progress tick per committed result."""
        sink = NullSink(NullConfig(support_worker_writes=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        progress = mock.Mock()

        _ = sink.write_batch(
            order_id,
            [ComputeResult(point=_point(exit_code=0)), ComputeResult(point=_point(exit_code=5))],
            progress=progress,
        )

        self.assertEqual(progress.tick.call_count, 2)

    def test_write_batch_empty_results_is_noop(self):
        """Ensure writing an empty batch returns no outcomes and emits no ticks."""
        sink = NullSink(NullConfig(support_worker_writes=False))
        order_id = sink.begin_run(_order())  # type: ignore[arg-type]
        progress = mock.Mock()

        outcomes = sink.write_batch(order_id, [], progress=progress)

        self.assertEqual(outcomes, [])
        progress.tick.assert_not_called()

    def test_finalize_run_requires_new_begin_run_before_next_write(self):
        """Ensure finalize_run clears active-run state so writes require a subsequent begin_run."""
        sink = NullSink(NullConfig(support_worker_writes=False))
        order = _order()
        order_id = sink.begin_run(order)  # type: ignore[arg-type]
        sink.finalize_run()

        with self.assertRaisesRegex(EleanorException, "called before begin_run"):
            sink.write_batch(order_id, [ComputeResult(point=_point())])  # type: ignore[arg-type]

        self.assertEqual(sink.begin_run(order), order_id)  # type: ignore[arg-type]
        outcomes = sink.write_batch(order_id, [ComputeResult(point=_point(exit_code=1))])
        self.assertTrue(outcomes[0].committed)

    def test_lazy_import_from_package(self):
        """Ensure eleanor.output lazy re-export resolves to eleanor.output.null.NullSink."""
        from eleanor.output import NullSink

        self.assertIs(
            NullSink,
            __import__("eleanor.output.null", fromlist=["NullSink"]).NullSink,
        )
