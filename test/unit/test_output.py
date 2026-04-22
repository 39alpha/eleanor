from collections.abc import Sequence
from types import SimpleNamespace
from unittest import mock

from eleanor.config import DatabaseConfig
from eleanor.order import Order
from eleanor.output import ComputeResult, ErrorInfo, OutputSink, PostgresSink, RunStats, WriteOutcome

from .common import TestCase


class TestOutput(TestCase):
    """
    Tests of the eleanor.output module.
    """

    def test_run_stats_updates_from_write_outcomes(self):
        """
        Ensure RunStats accumulates attempted/succeeded/failed from WriteOutcome lists.
        """
        stats = RunStats()
        outcomes = [
            WriteOutcome(point_id=10, exit_code=0, committed=True),
            WriteOutcome(point_id=11, exit_code=1, committed=True),
            WriteOutcome(point_id=None, exit_code=0, committed=False, error_message="x"),
        ]
        stats.update(outcomes)
        self.assertEqual(stats.attempted, 3)
        self.assertEqual(stats.succeeded, 1)
        self.assertEqual(stats.failed, 2)

    def test_output_sink_is_abstract(self):
        """
        Ensure OutputSink cannot be instantiated directly.
        """
        with self.assertRaises(TypeError):
            OutputSink()  # type: ignore[abstract]

    def test_output_sink_defaults_to_no_worker_writes(self):
        """
        Ensure OutputSink subclasses that do not override supports_worker_writes
        opt out of worker-side writes by default.
        """
        class MinimalSink(OutputSink):
            def begin_run(self, order: Order) -> None:
                pass

            def write_batch(self, order_id: int, results: Sequence[ComputeResult]) -> list[WriteOutcome]:
                return []

            def finalize(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_worker_writes())

    def test_postgres_sink_supports_worker_writes(self):
        """
        Ensure PostgresSink opts in to worker-side writes.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)
        self.assertTrue(sink.supports_worker_writes())

    def test_error_info_fields(self):
        """
        Ensure ErrorInfo stores serializable error metadata fields.
        """
        error = ErrorInfo(type_name="RuntimeError", message="boom", traceback_text="traceback")
        self.assertEqual(error.type_name, "RuntimeError")
        self.assertEqual(error.message, "boom")
        self.assertEqual(error.traceback_text, "traceback")

    def test_write_batch_recovers_per_point_on_write_failure(self):
        """
        Ensure write_batch catches per-point write failures and returns a committed=False
        outcome without aborting the rest of the batch.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        good_point = SimpleNamespace(exit_code=0, order_id=None, id=42)
        bad_point = SimpleNamespace(exit_code=0, order_id=None, id=None)

        results = [
            ComputeResult(point=good_point),
            ComputeResult(point=bad_point),
        ]

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def write(self, point, **_kwargs):
                if point is bad_point:
                    raise RuntimeError("write failed")

        with mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman):
            outcomes = sink.write_batch(order_id=7, results=results)

        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].committed)
        self.assertEqual(outcomes[0].point_id, 42)
        self.assertFalse(outcomes[1].committed)
        self.assertIsNone(outcomes[1].point_id)
        self.assertIsNotNone(outcomes[1].error_message)
        self.assertIn("write failed", outcomes[1].error_message)  # type: ignore[arg-type]

    def test_write_batch_recovers_when_point_id_missing_after_write(self):
        """
        Ensure write_batch treats a missing point.id after write as a recoverable error.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        point = SimpleNamespace(exit_code=0, order_id=None, id=None)
        results = [ComputeResult(point=point)]

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def write(self, _point, **_kwargs): pass  # does not set point.id

        with mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman):
            outcomes = sink.write_batch(order_id=7, results=results)

        self.assertEqual(len(outcomes), 1)
        self.assertFalse(outcomes[0].committed)
        self.assertIsNone(outcomes[0].point_id)
        self.assertIsNotNone(outcomes[0].error_message)
