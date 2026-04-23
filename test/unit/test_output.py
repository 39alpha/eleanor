from collections.abc import Sequence
from types import SimpleNamespace
from unittest import mock

from eleanor.config import DatabaseConfig
from eleanor.exceptions import EleanorException
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
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            def write_batch(self, order_id: int, results: Sequence[ComputeResult], progress=None) -> list[WriteOutcome]:
                _ = progress
                return []

            def finalize(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_worker_writes())

    def test_output_sink_defaults_to_no_progress(self):
        """
        Ensure OutputSink subclasses that do not override supports_progress
        opt out of the output bar by default -- protecting third-party sinks
        from silent breakage when the progress protocol evolves.
        """
        class MinimalSink(OutputSink):
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            def write_batch(self, order_id: int, results: Sequence[ComputeResult], progress=None) -> list[WriteOutcome]:
                _ = progress
                return []

            def finalize(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_progress())

    def test_postgres_sink_supports_worker_writes(self):
        """
        Ensure PostgresSink opts in to worker-side writes.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)
        self.assertTrue(sink.supports_worker_writes())

    def test_postgres_sink_supports_progress(self):
        """
        Ensure PostgresSink opts in to per-row output progress reporting.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)
        self.assertTrue(sink.supports_progress())

    def test_postgres_begin_run_returns_existing_order_id(self):
        """
        Ensure PostgresSink.begin_run returns the existing order.id without
        writing when the order is already persisted, and copies the stored
        eleanor_version onto the in-memory order when it is unset.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=17, eleanor_version=None)
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def setup(self): pass
            def get(self, _entity, _ident): return existing
            def write(self, _point, **_kwargs):
                raise AssertionError("write should not be called when the order is already persisted")

        with mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman):
            order_id = sink.begin_run(order)  # type: ignore[arg-type]

        self.assertEqual(order_id, 17)
        self.assertEqual(order.eleanor_version, "v1")

    def test_postgres_begin_run_writes_order_with_preassigned_id(self):
        """
        Ensure PostgresSink.begin_run inserts an order when order.id is
        supplied but no matching row exists, preserving the caller-chosen id
        and stamping the current Eleanor version.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=99, eleanor_version=None)
        write_calls: list[tuple[object, dict[str, object]]] = []

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def setup(self): pass
            def get(self, _entity, _ident): return None  # no matching row
            def write(self, entity, **kwargs):
                write_calls.append((entity, kwargs))

        with mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman):
            order_id = sink.begin_run(order)  # type: ignore[arg-type]

        self.assertEqual(order_id, 99)
        self.assertEqual(len(write_calls), 1)
        entity, kwargs = write_calls[0]
        self.assertIs(entity, order)
        self.assertEqual(entity.id, 99)  # caller-chosen id preserved
        self.assertTrue(kwargs.get("refresh"))
        self.assertIsNotNone(order.eleanor_version)

    def test_postgres_begin_run_raises_on_version_mismatch(self):
        """
        Ensure PostgresSink.begin_run rejects extending an order whose stored
        eleanor_version does not match the in-memory order's version.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=17, eleanor_version="v2")
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def setup(self): pass
            def get(self, _entity, _ident): return existing
            def write(self, _point, **_kwargs):
                raise AssertionError("write should not be called on version mismatch")

        with (
            mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman),
            self.assertRaisesRegex(EleanorException, "different version of Eleanor"),
        ):
            sink.begin_run(order)  # type: ignore[arg-type]

    def test_postgres_begin_run_writes_new_order_and_returns_id(self):
        """
        Ensure PostgresSink.begin_run writes an unpersisted order and returns
        the id assigned by the refresh.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=None, eleanor_version=None)
        write_calls: list[tuple[object, dict[str, object]]] = []

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def setup(self): pass
            def write(self, entity, **kwargs):
                write_calls.append((entity, kwargs))
                entity.id = 42  # simulate refresh assigning a primary key

        with mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman):
            order_id = sink.begin_run(order)  # type: ignore[arg-type]

        self.assertEqual(order_id, 42)
        self.assertEqual(len(write_calls), 1)
        entity, kwargs = write_calls[0]
        self.assertIs(entity, order)
        self.assertTrue(kwargs.get("refresh"))
        # begin_run should stamp the current Eleanor version onto the new order.
        self.assertIsNotNone(order.eleanor_version)

    def test_postgres_begin_run_raises_when_id_missing_after_write(self):
        """
        Ensure PostgresSink.begin_run raises if the refresh does not assign an
        order id after writing.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=None, eleanor_version=None)

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def setup(self): pass
            def write(self, _entity, **_kwargs): pass  # does not set id

        with (
            mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman),
            self.assertRaises(EleanorException),
        ):
            sink.begin_run(order)  # type: ignore[arg-type]

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

    def test_write_batch_ticks_progress_only_for_committed_rows(self):
        """
        Ensure PostgresSink.write_batch emits one progress tick per durably-
        written row and no tick for a row that failed to write.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        good_a = SimpleNamespace(exit_code=0, order_id=None, id=10)
        bad = SimpleNamespace(exit_code=0, order_id=None, id=None)
        good_b = SimpleNamespace(exit_code=0, order_id=None, id=11)
        results = [
            ComputeResult(point=good_a),
            ComputeResult(point=bad),
            ComputeResult(point=good_b),
        ]

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def write(self, point, **_kwargs):
                if point is bad:
                    raise RuntimeError("write failed")

        progress = mock.Mock()
        with mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman):
            outcomes = sink.write_batch(order_id=7, results=results, progress=progress)

        self.assertEqual(len(outcomes), 3)
        # Two successful writes => two ticks.
        self.assertEqual(progress.tick.call_count, 2)
        self.assertTrue(outcomes[0].committed)
        self.assertFalse(outcomes[1].committed)
        self.assertTrue(outcomes[2].committed)

    def test_write_batch_without_progress_handle_is_silent(self):
        """
        Ensure PostgresSink.write_batch tolerates progress=None (the default).
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        point = SimpleNamespace(exit_code=0, order_id=None, id=5)
        results = [ComputeResult(point=point)]

        class FakeYeoman:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def write(self, _point, **_kwargs): pass

        with mock.patch("eleanor.output.postgres.Yeoman", FakeYeoman):
            outcomes = sink.write_batch(order_id=7, results=results)

        # Smoke test: if the call didn't raise, the default-None path is fine.
        self.assertEqual(len(outcomes), 1)
