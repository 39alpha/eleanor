from pathlib import Path
import pickle
import tempfile
from eleanor.output.csv import CsvSink, CsvSinkSettings
from eleanor.output.memory import MemorySink, MemorySinkSettings
from eleanor.output.null import NullSink, NullSinkSettings
import io
import logging
from collections.abc import Sequence
from contextlib import nullcontext
from types import SimpleNamespace
from typing import cast, override
from unittest import TestCase, mock

import eleanor.variable_space as vs
from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output import (
    AbstractOutputSink,
    ComputeResult,
    ErrorInfo,
    RunStats,
    WriteOutcome,
)
from eleanor.output.postgres.settings import (
    PostgresDatabaseSettings,
    PostgresSinkSettings,
)
from eleanor.output.interface import ChunkResult, SinkBinding, SinkChunkResult
from eleanor.output.postgres.persistence import connection
from eleanor.output.postgres.sink import PostgresSink
from eleanor.progress import ProgressHandle



def _write_batch(sink, order_id, results, progress=None):
    """Drive both halves of the split write protocol, as Eleanor does."""
    prepared = sink.prepare_batch(order_id, results)
    return sink.commit_batch(order_id, prepared, progress=progress)

def _as_order(order: SimpleNamespace) -> Order:
    return cast(Order, cast(object, order))


def _as_point(point: SimpleNamespace) -> vs.Point:
    return cast(vs.Point, cast(object, point))


class TestOutput(TestCase):
    """
    Tests of the eleanor.output module.
    """

    def test_run_stats_updates_from_write_outcomes(self) -> None:
        """
        Ensure RunStats accumulates attempted/succeeded/failed from WriteOutcome lists.
        """
        stats = RunStats()
        outcomes = [
            WriteOutcome(exit_code=0, committed=True),
            WriteOutcome(exit_code=1, committed=True),
            WriteOutcome(exit_code=0, committed=False, error_message="x"),
        ]
        stats.update(outcomes)
        self.assertEqual(stats.attempted, 3)
        self.assertEqual(stats.succeeded, 1)
        self.assertEqual(stats.failed, 2)

    def test_output_sink_is_abstract(self) -> None:
        """
        Ensure AbstractOutputSink cannot be instantiated directly.
        """
        with self.assertRaises(TypeError):
            _ = AbstractOutputSink()  # pyright: ignore[reportAbstractUsage]

    def test_output_sink_defaults_to_no_worker_writes(self) -> None:
        """
        Ensure AbstractOutputSink subclasses that do not override supports_worker_commit
        opt out of worker-side writes by default.
        """

        class MinimalSink(AbstractOutputSink[int]):
            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def prepare_batch(
                self, order_id: int, results: Sequence[ComputeResult]
            ) -> Sequence[object]:
                return list(results)

            @override
            def commit_batch(
                self, order_id: int, prepared: Sequence[object], progress=None
            ) -> list[WriteOutcome]:
                _ = progress
                return []

            @override
            def finalize_run(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_worker_commit())

    def test_output_sink_defaults_to_no_progress(self) -> None:
        """
        Ensure AbstractOutputSink subclasses that do not override supports_progress
        opt out of the output bar by default -- protecting third-party sinks
        from silent breakage when the progress protocol evolves.
        """

        class MinimalSink(AbstractOutputSink[int]):
            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def prepare_batch(
                self, order_id: int, results: Sequence[ComputeResult]
            ) -> Sequence[object]:
                return list(results)

            @override
            def commit_batch(
                self, order_id: int, prepared: Sequence[object], progress=None
            ) -> list[WriteOutcome]:
                _ = progress
                return []

            @override
            def finalize_run(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_progress())

    def test_output_sink_context_manager_calls_initialize_and_finalize(self) -> None:
        """
        Ensure AbstractOutputSink.__enter__ calls initialize and returns the sink,
        and __exit__ calls finalize, matching the AbstractExecutor pattern.
        """

        calls: list[str] = []

        class RecordingSink(AbstractOutputSink[int]):
            @override
            def initialize(self) -> None:
                calls.append("initialize")

            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def prepare_batch(
                self, order_id: int, results: Sequence[ComputeResult]
            ) -> Sequence[object]:
                return list(results)

            @override
            def commit_batch(
                self,
                order_id: int,
                prepared: Sequence[object],
                progress: ProgressHandle | None = None,
            ) -> list[WriteOutcome]:
                _ = progress
                return []

            @override
            def finalize_run(self) -> None:
                pass

            @override
            def finalize(self) -> None:
                calls.append("finalize")

        sink = RecordingSink()
        with sink as entered:
            self.assertIs(entered, sink)
            self.assertEqual(calls, ["initialize"])
        self.assertEqual(calls, ["initialize", "finalize"])

    def test_postgres_sink_supports_worker_commit(self) -> None:
        """
        Ensure PostgresSink opts in to worker-side writes.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        self.assertTrue(sink.supports_worker_commit())

    def test_postgres_sink_supports_progress(self) -> None:
        """
        Ensure PostgresSink opts in to per-row output progress reporting.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        self.assertTrue(sink.supports_progress())

    def test_postgres_initialize_runs_apply_pending_migrations(self) -> None:
        """
        Ensure PostgresSink.initialize calls repositories.apply_pending_migrations
        once with the active config, and -- with bulk_load_optimization off --
        does NOT call drop_bulk_load_objects.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.apply_pending_migrations"
            ) as apply_mig,
            mock.patch(
                "eleanor.output.postgres.sink.repositories.drop_bulk_load_objects"
            ) as drop_bulk_load_objects,
        ):
            sink.initialize()
        apply_mig.assert_called_once_with(settings.database)
        drop_bulk_load_objects.assert_not_called()

    def test_postgres_initialize_drops_indexes_when_bulk_load_optimization_is_on(
        self,
    ) -> None:
        """
        Ensure PostgresSink.initialize calls
        :func:`repositories.drop_bulk_load_objects` *after* ``apply_pending_migrations``
        when the sink was constructed with ``bulk_load_optimization=True``.
        The order matters: tables must exist before we try to alter
        them on a fresh database.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
            bulk_load_optimization=True,
        )
        sink = PostgresSink(settings)
        manager = mock.MagicMock()
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.apply_pending_migrations",
                manager.apply_pending_migrations,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.drop_bulk_load_objects",
                manager.drop_bulk_load_objects,
            ),
        ):
            sink.initialize()
        manager.apply_pending_migrations.assert_called_once_with(settings.database)
        manager.drop_bulk_load_objects.assert_called_once_with(settings.database)
        # mock.Mock records every child-attr call on the parent in order;
        # we use that ordering to pin the migrate-then-drop sequence.
        self.assertEqual(
            [c[0] for c in manager.method_calls],
            ["apply_pending_migrations", "drop_bulk_load_objects"],
        )

    def test_postgres_finalize_closes_connection(self) -> None:
        """
        Ensure PostgresSink.finalize releases the persistent connection
        through ``connection_module.release``, and -- with
        bulk_load_optimization off -- does NOT call recreate_bulk_load_objects.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.release"
            ) as close,
            mock.patch(
                "eleanor.output.postgres.sink.repositories.recreate_bulk_load_objects"
            ) as recreate,
        ):
            sink.finalize()
        close.assert_called_once_with(settings.database)
        recreate.assert_not_called()

    def test_postgres_finalize_recreates_indexes_when_bulk_load_optimization_is_on(
        self,
    ) -> None:
        """
        Ensure PostgresSink.finalize calls
        :func:`repositories.recreate_bulk_load_objects` *before* the connection
        is released when the sink was constructed with
        ``bulk_load_optimization=True``. Order matters: the recreate
        uses the same connection cache, so it must run before
        ``release`` evicts the cached entry.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
            bulk_load_optimization=True,
        )
        sink = PostgresSink(settings)
        manager = mock.MagicMock()
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.recreate_bulk_load_objects",
                manager.recreate_bulk_load_objects,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.release",
                manager.release,
            ),
        ):
            sink.finalize()
        manager.recreate_bulk_load_objects.assert_called_once_with(settings.database)
        manager.release.assert_called_once_with(settings.database)
        self.assertEqual(
            [c[0] for c in manager.method_calls],
            ["recreate_bulk_load_objects", "release"],
        )

    def test_postgres_finalize_still_closes_connection_when_recreate_raises(
        self,
    ) -> None:
        """
        Ensure PostgresSink.finalize releases the persistent connection
        even when :func:`recreate_bulk_load_objects` raises -- typically because
        the bulk-loaded data violates a constraint. The recreate
        exception must propagate to the caller (so the failure isn't
        silently swallowed) but the libpq socket must not leak.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
            bulk_load_optimization=True,
        )
        sink = PostgresSink(settings)
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.recreate_bulk_load_objects",
                side_effect=RuntimeError("check constraint violated"),
            ),
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.release",
            ) as close,
        ):
            with self.assertRaisesRegex(RuntimeError, "check constraint violated"):
                sink.finalize()
        close.assert_called_once_with(settings.database)

    def test_postgres_verbose_initialize_finalize_restores_psycopg_log_level(
        self,
    ) -> None:
        """
        Ensure a verbose sink snapshots the psycopg logger's level
        during :meth:`initialize` and restores it during
        :meth:`finalize`.  A redundant second ``initialize`` must
        not clobber the original snapshot.
        """
        settings = PostgresSinkSettings(
            verbose=True,
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        logger = logging.getLogger("psycopg")
        original_level = logging.WARNING
        logger.setLevel(original_level)
        try:
            with mock.patch(
                "eleanor.output.postgres.sink.repositories.apply_pending_migrations"
            ):
                sink.initialize()
            self.assertEqual(logger.level, logging.DEBUG)
            # Second initialize must NOT overwrite the snapshot.
            with mock.patch(
                "eleanor.output.postgres.sink.repositories.apply_pending_migrations"
            ):
                sink.initialize()
            self.assertEqual(logger.level, logging.DEBUG)
            with mock.patch(
                "eleanor.output.postgres.sink.connection_module.release",
            ):
                sink.finalize()
            self.assertEqual(logger.level, original_level)
        finally:
            # Belt-and-suspenders: leave the logger clean for other tests.
            logger.setLevel(logging.WARNING)

    def test_postgres_finalize_run_is_noop(self) -> None:
        """
        Ensure PostgresSink.finalize_run is a no-op today (reserved for
        the bulk-load follow-up).
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        # Just verify it returns without raising / reaching the connection layer.
        sink.finalize_run()

    def test_postgres_begin_run_resumes_the_requested_id(self) -> None:
        """
        Ensure a requested_id naming an existing row resumes it without inserting.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(eleanor_version="v1")
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.get_order",
                return_value=existing,
            ) as get_order,
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_order"
            ) as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order), requested_id="17")

        self.assertEqual(order_id, 17)
        get_order.assert_called_once_with(settings.database, 17)
        insert_order.assert_not_called()

    def test_postgres_begin_run_rejects_a_requested_id_with_no_row(self) -> None:
        """
        Ensure a requested_id naming no row is an error rather than a new order.

        This previously inserted a fresh order under a different,
        sequence-assigned id, so the caller's request to extend a specific run
        was silently discarded.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(eleanor_version="v1")

        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.get_order", return_value=None
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_order"
            ) as insert_order,
            self.assertRaisesRegex(EleanorError, "no order 99 to extend"),
        ):
            _ = sink.begin_run(_as_order(order), requested_id="99")

        insert_order.assert_not_called()

    def test_postgres_begin_run_rejects_a_non_integer_requested_id(self) -> None:
        """
        Ensure a token outside this sink's id space is rejected by name.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(eleanor_version="v1")

        with self.assertRaisesRegex(EleanorError, "must be an integer"):
            _ = sink.begin_run(_as_order(order), requested_id="not-an-int")

    def test_postgres_begin_run_raises_on_version_mismatch(self) -> None:
        """
        Ensure begin_run rejects extending an order from a different Eleanor version.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(eleanor_version="v2")
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.get_order",
                return_value=existing,
            ),
            self.assertRaisesRegex(EleanorError, "different version of Eleanor"),
        ):
            _ = sink.begin_run(_as_order(order), requested_id="17")

    def test_postgres_begin_run_writes_new_order_and_returns_id(self) -> None:
        """
        Ensure begin_run writes a new order and returns the sequence-generated id.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(eleanor_version="v1")
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_order",
                return_value=SimpleNamespace(id=42),
            ) as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 42)
        insert_order.assert_called_once_with(settings.database, order)

    def test_error_info_fields(self) -> None:
        """
        Ensure ErrorInfo stores serializable error metadata fields.
        """
        error = ErrorInfo(
            type_name="RuntimeError", message="boom", traceback_text="traceback"
        )
        self.assertEqual(error.type_name, "RuntimeError")
        self.assertEqual(error.message, "boom")
        self.assertEqual(error.traceback_text, "traceback")

    def test_write_batch_recovers_per_point_on_write_failure(self) -> None:
        """
        Ensure write_batch catches per-point failures via savepoints and
        keeps processing the batch, committing the surviving rows in a
        single outer commit.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        good_point = SimpleNamespace(exit_code=0)
        bad_point = SimpleNamespace(exit_code=0)
        results = [
            ComputeResult(point=_as_point(good_point)),
            ComputeResult(point=_as_point(bad_point)),
        ]

        # ``conn.transaction()`` is used both for the outer batch transaction
        # and the per-VS-point savepoint. ``nullcontext`` is a stateless
        # stand-in that propagates exceptions instead of swallowing them
        # like a default MagicMock ``__exit__`` would.
        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        def insert_point(_conn, _order_id, point, _error=None, _settings=None) -> int:
            if point is bad_point:
                raise RuntimeError("write failed")
            return 42

        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.connect",
                return_value=fake_conn,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_point",
                side_effect=insert_point,
            ),
        ):
            outcomes = _write_batch(sink, 7, results)

        # One outer transaction + one savepoint per VS point = three calls.
        self.assertEqual(fake_conn.transaction.call_count, 3)
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].committed)
        self.assertEqual(outcomes[0].exit_code, 0)
        self.assertFalse(outcomes[1].committed)
        self.assertEqual(outcomes[1].exit_code, -1)
        error_message = outcomes[1].error_message
        self.assertIsNotNone(error_message)
        if error_message is None:
            raise AssertionError("expected error_message on failed outcome")
        self.assertIn("write failed", error_message)

    def test_write_batch_ticks_progress_only_for_committed_rows(self) -> None:
        """
        Ensure PostgresSink.write_batch emits one progress tick per durably-
        written row and no tick for a row that failed to write.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        good_a = SimpleNamespace(exit_code=0)
        bad = SimpleNamespace(exit_code=0)
        good_b = SimpleNamespace(exit_code=0)
        results = [
            ComputeResult(point=_as_point(good_a)),
            ComputeResult(point=_as_point(bad)),
            ComputeResult(point=_as_point(good_b)),
        ]

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        def insert_point(_conn, _order_id, point, _error=None, _settings=None) -> int:
            if point is bad:
                raise RuntimeError("write failed")
            if point is good_a:
                return 10
            return 11

        progress = mock.Mock()
        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.connect",
                return_value=fake_conn,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_point",
                side_effect=insert_point,
            ),
        ):
            outcomes = _write_batch(sink, 7, results, progress=progress)

        self.assertEqual(len(outcomes), 3)
        # Two successful writes => two ticks.
        self.assertEqual(progress.tick.call_count, 2)
        self.assertTrue(outcomes[0].committed)
        self.assertFalse(outcomes[1].committed)
        self.assertTrue(outcomes[2].committed)

    def test_write_batch_without_progress_handle_is_silent(self) -> None:
        """
        Ensure PostgresSink.write_batch tolerates progress=None (the default).
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        point = SimpleNamespace(exit_code=0)
        results = [ComputeResult(point=_as_point(point))]

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.connect",
                return_value=fake_conn,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_point",
                return_value=5,
            ),
        ):
            outcomes = _write_batch(sink, 7, results)

        # Smoke test: if the call didn't raise, the default-None path is fine.
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].committed)
        self.assertEqual(outcomes[0].exit_code, 0)

    def test_postgres_begin_run_preserves_caller_supplied_version_on_fresh_insert(
        self,
    ) -> None:
        """
        Ensure begin_run keeps the caller's ``order.eleanor_version`` when it
        is already set and the order has no id yet -- only the unset case
        gets the running ``__version__`` stamped on it.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(eleanor_version="custom-v1")
        with mock.patch(
            "eleanor.output.postgres.sink.repositories.insert_order",
            return_value=SimpleNamespace(id=42),
        ) as insert_order:
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 42)
        self.assertEqual(order.eleanor_version, "custom-v1")
        insert_order.assert_called_once_with(settings.database, order)

    def test_write_batch_with_empty_results_returns_empty_outcomes(self) -> None:
        """
        Ensure an empty batch is a clean no-op: no per-VS-point work is
        scheduled, ``insert_point`` is never invoked, and the returned
        outcomes list is empty. Callers (notably the executor loop) treat
        an empty list as "this batch contributed zero rows".
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.connect",
                return_value=fake_conn,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_point",
            ) as insert_point,
        ):
            outcomes = _write_batch(sink, 7, [])

        self.assertEqual(outcomes, [])
        insert_point.assert_not_called()

    def test_write_batch_passes_order_id_to_insert_point(self) -> None:
        """
        Ensure the ``variable_space.order_id`` foreign key comes from the
        ``order_id`` the sink was called with, not from any field on the
        point. The point graph carries no order id at all, so the batch
        context is the only source, and every point in the batch must get
        the same one.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        results = [
            ComputeResult(point=_as_point(SimpleNamespace(exit_code=0))),
            ComputeResult(point=_as_point(SimpleNamespace(exit_code=0))),
        ]

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.connect",
                return_value=fake_conn,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_point",
                return_value=1,
            ) as insert_point,
        ):
            _ = _write_batch(sink, 42, results)

        self.assertEqual(insert_point.call_count, 2)
        # insert_point(conn, order_id, point, error, settings)
        self.assertEqual([call.args[1] for call in insert_point.call_args_list], [42, 42])

    def test_write_batch_logs_per_point_failure_to_stderr_with_traceback(self) -> None:
        """
        Ensure savepoint-rolled-back failures get logged on stderr with
        the VS-point index, the exception class name, the message, and
        a full traceback. Without this output we can't tell why a batch
        wrote less than expected; the silent-failure regression is the
        whole reason this branch exists.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        good = SimpleNamespace(exit_code=0)
        bad = SimpleNamespace(exit_code=0)
        results = [
            ComputeResult(point=_as_point(good)),
            ComputeResult(point=_as_point(bad)),
        ]

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        def insert_point(_conn, _order_id, point, _error=None, _settings=None) -> int:
            if point is bad:
                raise ValueError("inner write failed")
            return 9

        captured = io.StringIO()
        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.connect",
                return_value=fake_conn,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_point",
                side_effect=insert_point,
            ),
            mock.patch("eleanor.output.postgres.sink.sys.stderr", captured),
        ):
            outcomes = _write_batch(sink, 7, results)

        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].committed)
        self.assertFalse(outcomes[1].committed)
        text = captured.getvalue()
        # The summary line carries the failing VS index + exception class
        # + message; the traceback follows.
        self.assertIn("VS point index 1", text)
        self.assertIn("ValueError", text)
        self.assertIn("inner write failed", text)
        self.assertIn("Traceback", text)

    def test_postgres_package_re_exports_postgres_sink(self) -> None:
        """Ensure :mod:`eleanor.output.postgres` eagerly re-exports ``PostgresSink``."""
        import eleanor.output.postgres as postgres_pkg
        from eleanor.output.postgres.sink import PostgresSink as _PostgresSink

        self.assertIs(postgres_pkg.PostgresSink, _PostgresSink)

    def test_write_batch_outer_commit_failure_demotes_pending_slots(self) -> None:
        """
        Ensure an outer-transaction commit failure rewrites every pending
        success placeholder to a failed ``WriteOutcome`` carrying the commit
        error, while leaving per-VS-point failures (which already have an
        error message recorded inside the loop) untouched. Progress is not
        ticked because no row durably committed.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        good_a = SimpleNamespace(exit_code=0)
        bad = SimpleNamespace(exit_code=0)
        good_b = SimpleNamespace(exit_code=1)
        results = [
            ComputeResult(point=_as_point(good_a)),
            ComputeResult(point=_as_point(bad)),
            ComputeResult(point=_as_point(good_b)),
        ]

        class _RaisesOnExit:
            def __init__(self, exc: BaseException) -> None:
                self.exc = exc

            def __enter__(self) -> "_RaisesOnExit":
                return self

            def __exit__(
                self,
                _exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                _tb: object,
            ) -> bool:
                # Only raise on a clean exit so we don't mask in-flight
                # exceptions from the inner block.
                if exc_val is None:
                    raise self.exc
                return False

        fake_conn = mock.MagicMock()
        # First call is the outer transaction; the next three are per-VS-point
        # savepoints. We make the outer commit raise on exit so the loop
        # completes normally and the failure surfaces only at the outermost
        # ``__exit__``.
        fake_conn.transaction.side_effect = [
            _RaisesOnExit(RuntimeError("commit died")),
            nullcontext(),
            nullcontext(),
            nullcontext(),
        ]

        def insert_point(_conn, _order_id, point, _error=None, _settings=None) -> int:
            if point is bad:
                raise ValueError("per-point oops")
            return 11 if point is good_a else 22

        progress = mock.Mock()
        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.connect",
                return_value=fake_conn,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_point",
                side_effect=insert_point,
            ),
        ):
            outcomes = _write_batch(sink, 7, results, progress=progress)

        self.assertEqual(len(outcomes), 3)
        for outcome in outcomes:
            self.assertFalse(outcome.committed)
        # Originally-pending slots now carry the commit error.
        self.assertEqual(outcomes[0].error_message, "commit died")
        self.assertEqual(outcomes[2].error_message, "commit died")
        # The per-VS-point failure keeps its original message.
        commit_error = outcomes[1].error_message
        self.assertIsNotNone(commit_error)
        if commit_error is None:
            raise AssertionError("expected per-point error message")
        self.assertIn("per-point oops", commit_error)
        # No row durably committed, so progress was never ticked.
        progress.tick.assert_not_called()


def _order_for_begin_run() -> Order:
    """Minimal order accepted by every in-tree sink's ``begin_run``."""
    return _as_order(SimpleNamespace(eleanor_version="v1", vs_points=[]))


class TestPostgresConnectionSharing(TestCase):
    """Two Postgres sinks on one database must not close each other's socket.

    The connection cache is keyed on the database settings rather than on the
    sink, so sinks pointed at the same database share connections. Before
    reference counting, whichever sink finalized first closed the shared
    socket, and the other one carried on writing through a dead connection.
    """

    def setUp(self) -> None:
        self.database = PostgresDatabaseSettings(
            database="db", username="u", password="p"
        )
        # Two sinks that differ only outside PostgresDatabaseSettings, so they
        # collide on the cache key.
        self.first = PostgresSink(
            PostgresSinkSettings(database=self.database, write_unformed=True)
        )
        self.second = PostgresSink(
            PostgresSinkSettings(database=self.database, write_unformed=False)
        )

    def tearDown(self) -> None:
        connection._owners.clear()  # pyright: ignore[reportPrivateUsage]

    def _initialize(self, sink: PostgresSink) -> None:
        with mock.patch(
            "eleanor.output.postgres.sink.repositories.apply_pending_migrations"
        ):
            sink.initialize()

    def test_first_finalize_does_not_close_shared_connection(self) -> None:
        """Ensure only the *last* sink to finalize actually closes."""
        self._initialize(self.first)
        self._initialize(self.second)

        with mock.patch(
            "eleanor.output.postgres.persistence.connection.close_connection"
        ) as close:
            self.first.finalize()
            close.assert_not_called()

            self.second.finalize()
            close.assert_called_once_with(self.database)

    def test_finalize_without_initialize_closes_immediately(self) -> None:
        """Ensure an unmatched release still closes, as a bare finalize did."""
        with mock.patch(
            "eleanor.output.postgres.persistence.connection.close_connection"
        ) as close:
            self.first.finalize()
        close.assert_called_once_with(self.database)

    def test_redundant_initialize_takes_one_reference(self) -> None:
        """Ensure a second ``initialize`` does not leave a reference stranded.

        ``PostgresSink.initialize`` is documented as once-per-instance but
        already tolerates being called twice (it guards the psycopg log-level
        snapshot for exactly that reason). An unguarded acquire would mean the
        single matching ``finalize`` never closed.
        """
        self._initialize(self.first)
        self._initialize(self.first)

        with mock.patch(
            "eleanor.output.postgres.persistence.connection.close_connection"
        ) as close:
            self.first.finalize()
        close.assert_called_once_with(self.database)

    def test_distinct_databases_are_counted_separately(self) -> None:
        """Ensure a sink on another database is not kept alive by this one."""
        other_database = PostgresDatabaseSettings(
            database="other", username="u", password="p"
        )
        other = PostgresSink(PostgresSinkSettings(database=other_database))

        self._initialize(self.first)
        self._initialize(other)

        with mock.patch(
            "eleanor.output.postgres.persistence.connection.close_connection"
        ) as close:
            other.finalize()
        close.assert_called_once_with(other_database)


class TestSinkTargetKeys(TestCase):
    """A sink must name the store it writes to, so two cannot share one.

    Eleanor deduplicates sink *names*, and a name says nothing about where the
    sink points, so this is the only thing standing between a copy-pasted
    config block and two writers on one file.
    """

    def test_target_key_defaults_to_none(self) -> None:
        """Ensure a sink with no exclusive target opts out, as do older plugins."""
        self.assertIsNone(NullSink(NullSinkSettings(support_worker_commit=False)).target_key())
        self.assertIsNone(MemorySink(MemorySinkSettings(support_worker_commit=False)).target_key())

    def test_csv_sinks_collide_on_one_file_however_it_is_spelled(self) -> None:
        """Ensure the path is resolved, so ``./rows.csv`` and ``rows.csv`` match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            query = {
                "row_scope": "vs_points[*]",
                "columns": [{"path": "vs_point.exit_code", "name": "exit_code"}],
            }
            direct = CsvSink(CsvSinkSettings(filename=Path(tmpdir) / "rows.csv", query=query))
            indirect = CsvSink(CsvSinkSettings(filename=Path(tmpdir) / "sub" / ".." / "rows.csv", query=query))
            elsewhere = CsvSink(CsvSinkSettings(filename=Path(tmpdir) / "other.csv", query=query))

            self.assertEqual(direct.target_key(), indirect.target_key())
            self.assertNotEqual(direct.target_key(), elsewhere.target_key())

    def test_postgres_sinks_collide_on_one_database(self) -> None:
        """Ensure settings around the database do not make two sinks look distinct.

        ``bulk_load_optimization`` is exactly the setting that differs between
        two such sinks, and exactly the one that makes sharing dangerous.
        """
        database = PostgresDatabaseSettings(database="db", username="u", password="p")
        loading = PostgresSink(PostgresSinkSettings(database=database, bulk_load_optimization=True))
        plain = PostgresSink(PostgresSinkSettings(database=database, bulk_load_optimization=False))
        other = PostgresSink(
            PostgresSinkSettings(database=PostgresDatabaseSettings(database="other", username="u", password="p")),
        )

        self.assertEqual(loading.target_key(), plain.target_key())
        self.assertNotEqual(loading.target_key(), other.target_key())


class TestSinkPicklability(TestCase):
    """Every sink must survive the trip into a worker process.

    ``prepare_batch`` always runs in a worker, so Eleanor pickles the sink
    once per chunk. That is a stronger requirement than it looks: pickle
    stores a class *by name*, so the class must also be importable, and any
    custom ``__getstate__`` must actually work on an instance. Both of those
    broke real code during the prepare/commit split, and neither showed up in
    a test that only ever used a sink in-process.
    """

    @staticmethod
    def _round_trip(sink: AbstractOutputSink[int]) -> AbstractOutputSink[int]:
        return cast(AbstractOutputSink[int], pickle.loads(pickle.dumps(sink)))

    def _assert_prepares_after_round_trip(self, sink: AbstractOutputSink[int], order: Order) -> None:
        """A pickled sink must still be able to prepare a batch."""
        order_id = sink.begin_run(order)
        clone = self._round_trip(sink)
        results = [ComputeResult(point=_as_point(SimpleNamespace(exit_code=0)))]

        prepared = clone.prepare_batch(order_id, results)

        self.assertEqual(len(prepared), 1, "prepare_batch must yield one item per result")

    def test_null_sink_round_trips(self) -> None:
        sink = NullSink(NullSinkSettings(support_worker_commit=False))
        self._assert_prepares_after_round_trip(sink, _order_for_begin_run())

    def test_memory_sink_round_trips(self) -> None:
        sink = MemorySink(MemorySinkSettings(support_worker_commit=False))
        self._assert_prepares_after_round_trip(sink, _order_for_begin_run())

    def test_memory_sink_does_not_ship_its_retained_graph_to_workers(self) -> None:
        """Ensure committed points do not inflate the per-chunk pickle.

        This sink retains the whole compute graph, and the sink is pickled
        into a worker once per chunk, so leaving the graph in its state makes
        a run pay for its own output quadratically.
        """
        sink = MemorySink(MemorySinkSettings(support_worker_commit=False))
        order = _order_for_begin_run()
        order_id = sink.begin_run(order)
        empty = len(pickle.dumps(sink))

        points = [_as_point(SimpleNamespace(exit_code=0, payload=bytes(f"{i:04d}", "ascii") * 200)) for i in range(200)]
        _ = sink.commit_batch(order_id, sink.prepare_batch(order_id, [ComputeResult(point=p) for p in points]))

        self.assertEqual(len(order.vs_points), 200, "the points must still be retained in the parent")
        self.assertLessEqual(len(pickle.dumps(sink)) - empty, 64)

    def test_csv_sink_does_not_ship_the_orders_points_to_workers(self) -> None:
        """Ensure another sink's appends do not inflate this sink's pickle.

        ``prepare_batch`` replaces ``vs_points`` with the single point it is
        evaluating, so the list is dead weight -- and a ``MemorySink`` in the
        same run appends its results to the very same ``Order``.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            sink = CsvSink(
                CsvSinkSettings(
                    filename=Path(tmpdir) / "rows.csv",
                    query={
                        "row_scope": "vs_points[*]",
                        "columns": [{"path": "vs_point.exit_code", "name": "exit_code"}],
                    },
                ),
            )
            sink.initialize()
            order = _order_for_begin_run()
            _ = sink.begin_run(order)
            empty = len(pickle.dumps(sink))

            order.vs_points.extend(
                _as_point(SimpleNamespace(exit_code=0, payload=bytes(f"{i:04d}", "ascii") * 200)) for i in range(200)
            )

            self.assertLessEqual(len(pickle.dumps(sink)) - empty, 64)
            self.assertEqual(len(order.vs_points), 200, "the live order must not be emptied")

    def test_csv_sink_round_trips_and_rebuilds_its_compiled_query(self) -> None:
        """``CsvSink`` drops the compiled query on pickling and re-derives it.

        The query is bulky to pickle and memoised to rebuild, so it is
        deliberately excluded from the sink's state.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                CsvSinkSettings(
                    filename=filename,
                    query={
                        "row_scope": "vs_points[*]",
                        "columns": [{"path": "vs_point.exit_code", "name": "exit_code"}],
                    },
                ),
            )
            sink.initialize()

            self.assertNotIn("_compiled", pickle.dumps(sink).decode("latin-1"))
            clone = self._round_trip(sink)
            self.assertIsNotNone(clone._compiled)

            self._assert_prepares_after_round_trip(sink, _order_for_begin_run())

    def test_postgres_sink_round_trips(self) -> None:
        sink = PostgresSink(
            PostgresSinkSettings(database=PostgresDatabaseSettings(database="unused")),
        )
        clone = self._round_trip(sink)

        # No begin_run here: that would touch a database. Preparing needs only
        # the settings, which is the point -- prepare must not depend on
        # parent-side connection state.
        prepared = clone.prepare_batch(7, [ComputeResult(point=_as_point(SimpleNamespace(exit_code=0)))])
        self.assertEqual(len(prepared), 1)

    def test_a_sink_class_defined_at_runtime_cannot_reach_a_worker(self) -> None:
        """Document the by-name constraint that pickling a sink imposes.

        A subclass synthesised with ``type(...)`` has no importable name, so
        it cannot be sent to a worker even though its *state* is trivially
        picklable. Anything that adjusts a sink's behaviour by building a
        class on the fly has to be a real, module-level class instead.
        """
        runtime_subclass = type(
            "RuntimeNullSink",
            (NullSink,),
            {"supports_worker_commit": lambda _self: False},
        )
        sink = runtime_subclass(NullSinkSettings(support_worker_commit=False))

        with self.assertRaises((pickle.PicklingError, AttributeError)):
            _ = pickle.dumps(sink)


class TestResumeOptIn(TestCase):
    """``supports_resume`` defaults to True and is overridable."""

    def test_builtin_sinks_support_resume(self) -> None:
        """Ensure the capability is a pure extension point for now.

        All four built-ins accept a resume token today, so none of them may
        change behaviour when the flag starts being consulted.
        """
        sinks: list[AbstractOutputSink[object]] = [
            cast("AbstractOutputSink[object]", NullSink(NullSinkSettings(support_worker_commit=False))),
            cast("AbstractOutputSink[object]", MemorySink(MemorySinkSettings(support_worker_commit=False))),
            cast(
                "AbstractOutputSink[object]",
                PostgresSink(
                    PostgresSinkSettings(
                        database=PostgresDatabaseSettings(
                            database="db", username="u", password="p"
                        ),
                    ),
                ),
            ),
        ]
        for sink in sinks:
            with self.subTest(sink=type(sink).__name__):
                self.assertTrue(sink.supports_resume())

    def test_default_is_true_for_a_bare_subclass(self) -> None:
        """Ensure a third-party sink predating the flag keeps resuming."""

        class BareSink(AbstractOutputSink[int]):
            @override
            def begin_run(self, order: Order, *, requested_id: str | None = None) -> int:
                return 0

            @override
            def prepare_batch(
                self, order_id: int, results: Sequence[ComputeResult]
            ) -> Sequence[object]:
                return list(results)

            @override
            def commit_batch(
                self,
                order_id: int,
                prepared: Sequence[object],
                progress: ProgressHandle | None = None,
            ) -> list[WriteOutcome]:
                return []

            @override
            def finalize_run(self) -> None:
                return

        self.assertTrue(BareSink().supports_resume())

    def test_a_sink_can_decline(self) -> None:
        """Ensure a sink with nothing to resume can say so."""

        class EphemeralSink(NullSink):
            @override
            def supports_resume(self) -> bool:
                return False

        self.assertFalse(EphemeralSink(NullSinkSettings(support_worker_commit=False)).supports_resume())


class TestBackgroundCommitOptIn(TestCase):
    """Which sinks claim the writer thread, and why.

    The capability is not free: a writer thread overlaps with the dispatch
    loop only while the commit releases the GIL. A commit that is CPU-bound
    Python contends instead, and measures slower than committing inline.
    """

    def test_csv_sink_opts_in(self) -> None:
        """Its conversion runs in prepare, leaving commit as file I/O."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sink = CsvSink(
                CsvSinkSettings(
                    filename=Path(tmpdir) / "rows.csv",
                    query={
                        "row_scope": "vs_points[*]",
                        "columns": [{"path": "vs_point.exit_code", "name": "exit_code"}],
                    },
                ),
            )
            self.assertTrue(sink.supports_background_commit())

    def test_postgres_sink_opts_out(self) -> None:
        """Its commit still does the row conversion, so it holds the GIL.

        Pinned deliberately: flipping this to ``True`` before the conversion
        moves into ``prepare_batch`` made a forced-serial run measurably
        slower, not faster.
        """
        sink = PostgresSink(
            PostgresSinkSettings(database=PostgresDatabaseSettings(database="unused")),
        )
        self.assertFalse(sink.supports_background_commit())

    def test_the_default_is_to_opt_out(self) -> None:
        """Third-party sinks must not be enrolled without measuring."""

        class MinimalSink(AbstractOutputSink[int]):
            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def prepare_batch(
                self, order_id: int, results: Sequence[ComputeResult]
            ) -> Sequence[object]:
                return list(results)

            @override
            def commit_batch(
                self, order_id: int, prepared: Sequence[object], progress=None
            ) -> list[WriteOutcome]:
                _ = progress
                return []

            @override
            def finalize_run(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_background_commit())


class TestSinkBindingPicklability(TestCase):
    """A binding crosses into workers, so it and its parts must pickle.

    ``prepare_batch`` always runs in a worker, so this holds for every sink
    regardless of where it commits.
    """

    def test_a_binding_round_trips(self) -> None:
        """Ensure the binding survives the process boundary intact."""
        sink = NullSink(NullSinkSettings(support_worker_commit=True))
        binding = SinkBinding.bind("null", cast("AbstractOutputSink[object]", sink), 7)

        revived = cast(SinkBinding, pickle.loads(pickle.dumps(binding)))

        self.assertEqual(revived.name, "null")
        self.assertEqual(revived.order_id, 7)
        self.assertTrue(revived.commit_in_worker)
        self.assertIsInstance(revived.sink, NullSink)

    def test_bind_snapshots_the_commit_strategy(self) -> None:
        """Ensure the strategy is read once, so parent and worker agree."""
        worker = NullSink(NullSinkSettings(support_worker_commit=True))
        serial = NullSink(NullSinkSettings(support_worker_commit=False))

        self.assertTrue(
            SinkBinding.bind("a", cast("AbstractOutputSink[object]", worker), 0).commit_in_worker
        )
        self.assertFalse(
            SinkBinding.bind("b", cast("AbstractOutputSink[object]", serial), 0).commit_in_worker
        )

    def test_a_chunk_result_round_trips(self) -> None:
        """Ensure what a worker returns survives the trip home."""
        result = ChunkResult(
            point_count=2,
            sinks=[
                SinkChunkResult(name="pg", outcomes=[WriteOutcome(exit_code=0, committed=True)]),
                SinkChunkResult(name="csv", prepared=[{"row": 1}]),
            ],
        )

        revived = cast(ChunkResult, pickle.loads(pickle.dumps(result)))

        self.assertEqual(revived.point_count, 2)
        self.assertEqual([s.name for s in revived.sinks], ["pg", "csv"])
        self.assertIsNone(revived.sinks[0].prepared)
        self.assertIsNone(revived.sinks[1].outcomes)
