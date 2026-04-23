from collections.abc import Sequence
from types import SimpleNamespace
from unittest import mock

from eleanor.config import DatabaseConfig
from eleanor.exceptions import EleanorConfigurationException, EleanorException
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
            WriteOutcome(point_id=None, exit_code=0, committed=False, error_message='x'),
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
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)
        self.assertTrue(sink.supports_worker_writes())

    def test_postgres_sink_supports_progress(self):
        """
        Ensure PostgresSink opts in to per-row output progress reporting.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)
        self.assertTrue(sink.supports_progress())

    def test_postgres_sink_rejects_non_postgres_dialect(self):
        """
        Ensure sink-specific dialect validation rejects non-postgresql configs.
        """
        cfg = DatabaseConfig(dialect='sqlite', database='db', username='u', password='p')
        with self.assertRaises(EleanorConfigurationException):
            _ = PostgresSink(cfg)

    def test_postgres_begin_run_returns_existing_order_id(self):
        """
        Ensure begin_run returns existing order.id and copies stored eleanor_version when unset.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=17, eleanor_version=None)
        existing = SimpleNamespace(id=17, eleanor_version='v1')

        with (
            mock.patch('eleanor.output.postgres.sink.repositories.setup_schema') as setup_schema,
            mock.patch('eleanor.output.postgres.sink.repositories.get_order', return_value=existing) as get_order,
            mock.patch('eleanor.output.postgres.sink.repositories.insert_order') as insert_order,
        ):
            order_id = sink.begin_run(order)  # type: ignore[arg-type]

        self.assertEqual(order_id, 17)
        self.assertEqual(order.eleanor_version, 'v1')
        setup_schema.assert_called_once_with(cfg, verbose=False)
        get_order.assert_called_once_with(cfg, 17, verbose=False)
        insert_order.assert_not_called()

    def test_postgres_begin_run_writes_order_with_preassigned_id(self):
        """
        Ensure begin_run inserts a caller-preassigned id when no matching row exists.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=99, eleanor_version=None)

        with (
            mock.patch('eleanor.output.postgres.sink.repositories.setup_schema'),
            mock.patch('eleanor.output.postgres.sink.repositories.get_order', return_value=None),
            mock.patch(
                'eleanor.output.postgres.sink.repositories.insert_order',
                return_value=SimpleNamespace(id=99),
            ) as insert_order,
        ):
            order_id = sink.begin_run(order)  # type: ignore[arg-type]

        self.assertEqual(order_id, 99)
        self.assertEqual(order.id, 99)
        self.assertIsNotNone(order.eleanor_version)
        insert_order.assert_called_once_with(cfg, order, verbose=False)

    def test_postgres_begin_run_raises_on_version_mismatch(self):
        """
        Ensure begin_run rejects extending an order from a different Eleanor version.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=17, eleanor_version='v2')
        existing = SimpleNamespace(id=17, eleanor_version='v1')

        with (
            mock.patch('eleanor.output.postgres.sink.repositories.setup_schema'),
            mock.patch('eleanor.output.postgres.sink.repositories.get_order', return_value=existing),
            self.assertRaisesRegex(EleanorException, 'different version of Eleanor'),
        ):
            sink.begin_run(order)  # type: ignore[arg-type]

    def test_postgres_begin_run_writes_new_order_and_returns_id(self):
        """
        Ensure begin_run writes a new order and returns its generated id.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=None, eleanor_version=None)
        with (
            mock.patch('eleanor.output.postgres.sink.repositories.setup_schema'),
            mock.patch(
                'eleanor.output.postgres.sink.repositories.insert_order',
                return_value=SimpleNamespace(id=42),
            ) as insert_order,
        ):
            order_id = sink.begin_run(order)  # type: ignore[arg-type]

        self.assertEqual(order_id, 42)
        self.assertEqual(order.id, 42)
        self.assertIsNotNone(order.eleanor_version)
        insert_order.assert_called_once_with(cfg, order, verbose=False)

    def test_postgres_begin_run_raises_when_id_missing_after_write(self):
        """
        Ensure begin_run raises if persistence does not return an order id.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)
        order = SimpleNamespace(id=None, eleanor_version=None)

        with (
            mock.patch('eleanor.output.postgres.sink.repositories.setup_schema'),
            mock.patch(
                'eleanor.output.postgres.sink.repositories.insert_order',
                return_value=SimpleNamespace(id=None),
            ),
            self.assertRaises(EleanorException),
        ):
            sink.begin_run(order)  # type: ignore[arg-type]

    def test_error_info_fields(self):
        """
        Ensure ErrorInfo stores serializable error metadata fields.
        """
        error = ErrorInfo(type_name='RuntimeError', message='boom', traceback_text='traceback')
        self.assertEqual(error.type_name, 'RuntimeError')
        self.assertEqual(error.message, 'boom')
        self.assertEqual(error.traceback_text, 'traceback')

    def test_write_batch_recovers_per_point_on_write_failure(self):
        """
        Ensure write_batch catches per-point failures and keeps processing the batch.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        good_point = SimpleNamespace(exit_code=0, order_id=None)
        bad_point = SimpleNamespace(exit_code=0, order_id=None)
        results = [ComputeResult(point=good_point), ComputeResult(point=bad_point)]

        fake_session = mock.MagicMock()
        fake_session.__enter__.return_value = fake_session
        fake_session.__exit__.return_value = None

        def insert_point(_session, _order_id, point):
            if point is bad_point:
                raise RuntimeError('write failed')
            return SimpleNamespace(id=42)

        with (
            mock.patch('eleanor.output.postgres.sink.PostgresSession', return_value=fake_session),
            mock.patch(
                'eleanor.output.postgres.sink.repositories.insert_point',
                side_effect=insert_point,
            ),
        ):
            outcomes = sink.write_batch(order_id=7, results=results)

        fake_session.rollback.assert_called_once()
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].committed)
        self.assertEqual(outcomes[0].point_id, 42)
        self.assertFalse(outcomes[1].committed)
        self.assertIsNone(outcomes[1].point_id)
        self.assertIsNotNone(outcomes[1].error_message)
        self.assertIn('write failed', outcomes[1].error_message)  # type: ignore[arg-type]

    def test_write_batch_recovers_when_point_id_missing_after_write(self):
        """
        Ensure write_batch treats a missing persisted id after write as a recoverable error.
        """
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        point = SimpleNamespace(exit_code=0, order_id=None)
        results = [ComputeResult(point=point)]

        fake_session = mock.MagicMock()
        fake_session.__enter__.return_value = fake_session
        fake_session.__exit__.return_value = None

        with (
            mock.patch('eleanor.output.postgres.sink.PostgresSession', return_value=fake_session),
            mock.patch(
                'eleanor.output.postgres.sink.repositories.insert_point',
                return_value=SimpleNamespace(id=None),
            ),
        ):
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
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        good_a = SimpleNamespace(exit_code=0, order_id=None, id=10)
        bad = SimpleNamespace(exit_code=0, order_id=None, id=None)
        good_b = SimpleNamespace(exit_code=0, order_id=None, id=11)
        results = [
            ComputeResult(point=good_a),
            ComputeResult(point=bad),
            ComputeResult(point=good_b),
        ]

        fake_session = mock.MagicMock()
        fake_session.__enter__.return_value = fake_session
        fake_session.__exit__.return_value = None

        def insert_point(_session, _order_id, point):
            if point is bad:
                raise RuntimeError('write failed')
            return SimpleNamespace(id=point.id)

        progress = mock.Mock()
        with (
            mock.patch('eleanor.output.postgres.sink.PostgresSession', return_value=fake_session),
            mock.patch(
                'eleanor.output.postgres.sink.repositories.insert_point',
                side_effect=insert_point,
            ),
        ):
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
        cfg = DatabaseConfig(database='db', username='u', password='p')
        sink = PostgresSink(cfg)

        point = SimpleNamespace(exit_code=0, order_id=None, id=5)
        results = [ComputeResult(point=point)]

        fake_session = mock.MagicMock()
        fake_session.__enter__.return_value = fake_session
        fake_session.__exit__.return_value = None

        with (
            mock.patch('eleanor.output.postgres.sink.PostgresSession', return_value=fake_session),
            mock.patch(
                'eleanor.output.postgres.sink.repositories.insert_point',
                return_value=SimpleNamespace(id=point.id),
            ),
        ):
            outcomes = sink.write_batch(order_id=7, results=results)

        # Smoke test: if the call didn't raise, the default-None path is fine.
        self.assertEqual(len(outcomes), 1)
