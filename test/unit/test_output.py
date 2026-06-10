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
from eleanor.output.postgres.sink import PostgresSink
from eleanor.progress import ProgressHandle


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
        Ensure AbstractOutputSink subclasses that do not override supports_worker_writes
        opt out of worker-side writes by default.
        """

        class MinimalSink(AbstractOutputSink):
            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def write_batch(
                self, order_id: int, results: Sequence[ComputeResult], progress=None
            ) -> list[WriteOutcome]:
                _ = progress
                return []

            @override
            def finalize_run(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_worker_writes())

    def test_output_sink_defaults_to_no_progress(self) -> None:
        """
        Ensure AbstractOutputSink subclasses that do not override supports_progress
        opt out of the output bar by default -- protecting third-party sinks
        from silent breakage when the progress protocol evolves.
        """

        class MinimalSink(AbstractOutputSink):
            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def write_batch(
                self, order_id: int, results: Sequence[ComputeResult], progress=None
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

        class RecordingSink(AbstractOutputSink):
            @override
            def initialize(self) -> None:
                calls.append("initialize")

            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def write_batch(
                self,
                order_id: int,
                results: Sequence[ComputeResult],
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

    def test_postgres_sink_supports_worker_writes(self) -> None:
        """
        Ensure PostgresSink opts in to worker-side writes.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        self.assertTrue(sink.supports_worker_writes())

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
        does NOT call drop_indexes.
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
                "eleanor.output.postgres.sink.repositories.drop_indexes"
            ) as drop_indexes,
        ):
            sink.initialize()
        apply_mig.assert_called_once_with(settings.database)
        drop_indexes.assert_not_called()

    def test_postgres_initialize_drops_indexes_when_bulk_load_optimization_is_on(
        self,
    ) -> None:
        """
        Ensure PostgresSink.initialize calls
        :func:`repositories.drop_indexes` *after* ``apply_pending_migrations``
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
                "eleanor.output.postgres.sink.repositories.drop_indexes",
                manager.drop_indexes,
            ),
        ):
            sink.initialize()
        manager.apply_pending_migrations.assert_called_once_with(settings.database)
        manager.drop_indexes.assert_called_once_with(settings.database)
        # mock.Mock records every child-attr call on the parent in order;
        # we use that ordering to pin the migrate-then-drop sequence.
        self.assertEqual(
            [c[0] for c in manager.method_calls],
            ["apply_pending_migrations", "drop_indexes"],
        )

    def test_postgres_finalize_closes_connection(self) -> None:
        """
        Ensure PostgresSink.finalize closes the persistent connection
        through ``connection_module.close_connection``, and -- with
        bulk_load_optimization off -- does NOT call recreate_indexes.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)
        with (
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.close_connection"
            ) as close,
            mock.patch(
                "eleanor.output.postgres.sink.repositories.recreate_indexes"
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
        :func:`repositories.recreate_indexes` *before* the connection
        is closed when the sink was constructed with
        ``bulk_load_optimization=True``. Order matters: the recreate
        uses the same connection cache, so it must run before
        ``close_connection`` evicts the cached entry.
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
                "eleanor.output.postgres.sink.repositories.recreate_indexes",
                manager.recreate_indexes,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.close_connection",
                manager.close_connection,
            ),
        ):
            sink.finalize()
        manager.recreate_indexes.assert_called_once_with(settings.database)
        manager.close_connection.assert_called_once_with(settings.database)
        self.assertEqual(
            [c[0] for c in manager.method_calls],
            ["recreate_indexes", "close_connection"],
        )

    def test_postgres_finalize_still_closes_connection_when_recreate_raises(
        self,
    ) -> None:
        """
        Ensure PostgresSink.finalize closes the persistent connection
        even when :func:`recreate_indexes` raises -- typically because
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
                "eleanor.output.postgres.sink.repositories.recreate_indexes",
                side_effect=RuntimeError("check constraint violated"),
            ),
            mock.patch(
                "eleanor.output.postgres.sink.connection_module.close_connection",
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
                "eleanor.output.postgres.sink.connection_module.close_connection",
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

    def test_postgres_begin_run_returns_existing_order_id(self) -> None:
        """
        Ensure begin_run returns existing order.id.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(id=17, eleanor_version="v1")
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
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 17)
        self.assertEqual(order.eleanor_version, "v1")
        get_order.assert_called_once_with(settings.database, 17)
        insert_order.assert_not_called()

    def test_postgres_begin_run_writes_order_with_preassigned_id(self) -> None:
        """
        Ensure begin_run inserts a caller-preassigned id when no matching row exists.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(id=99, eleanor_version="v1")

        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.get_order", return_value=None
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_order",
                return_value=SimpleNamespace(id=99),
            ) as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 99)
        self.assertEqual(order.id, 99)
        self.assertEqual(order.eleanor_version, "v1")
        insert_order.assert_called_once_with(settings.database, order)

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

        order = SimpleNamespace(id=17, eleanor_version="v2")
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.get_order",
                return_value=existing,
            ),
            self.assertRaisesRegex(EleanorError, "different version of Eleanor"),
        ):
            _ = sink.begin_run(_as_order(order))

    def test_postgres_begin_run_writes_new_order_and_returns_id(self) -> None:
        """
        Ensure begin_run writes a new order and returns its generated id.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(id=None, eleanor_version="v1")
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_order",
                return_value=SimpleNamespace(id=42),
            ) as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 42)
        self.assertEqual(order.id, 42)
        self.assertEqual(order.eleanor_version, "v1")
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

        good_point = SimpleNamespace(exit_code=0, order_id=None)
        bad_point = SimpleNamespace(exit_code=0, order_id=None)
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

        def insert_point(_conn, _order_id, point) -> int:
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
            outcomes = sink.write_batch(order_id=7, results=results)

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

        good_a = SimpleNamespace(exit_code=0, order_id=None)
        bad = SimpleNamespace(exit_code=0, order_id=None)
        good_b = SimpleNamespace(exit_code=0, order_id=None)
        results = [
            ComputeResult(point=_as_point(good_a)),
            ComputeResult(point=_as_point(bad)),
            ComputeResult(point=_as_point(good_b)),
        ]

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        def insert_point(_conn, _order_id, point) -> int:
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
            outcomes = sink.write_batch(order_id=7, results=results, progress=progress)

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

        point = SimpleNamespace(exit_code=0, order_id=None)
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
            outcomes = sink.write_batch(order_id=7, results=results)

        # Smoke test: if the call didn't raise, the default-None path is fine.
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].committed)
        self.assertEqual(outcomes[0].exit_code, 0)

    def test_postgres_begin_run_returns_existing_id_when_versions_match(self) -> None:
        """
        Ensure begin_run is a no-op insert when the caller supplies an
        ``order.id`` whose row already exists with a matching
        ``eleanor_version`` -- the existing id is returned without re-
        inserting.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        order = SimpleNamespace(id=17, eleanor_version="v1")
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
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 17)
        self.assertEqual(order.eleanor_version, "v1")
        get_order.assert_called_once_with(settings.database, 17)
        insert_order.assert_not_called()

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

        order = SimpleNamespace(id=None, eleanor_version="custom-v1")
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
            outcomes = sink.write_batch(order_id=7, results=[])

        self.assertEqual(outcomes, [])
        insert_point.assert_not_called()

    def test_write_batch_mutates_point_order_id(self) -> None:
        """
        Ensure ``write_batch`` stamps ``order_id`` on every result's point
        before persistence. The docstring documents this as a deliberate
        side effect so downstream code can read ``point.order_id`` without
        consulting the batch context.
        """
        settings = PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                database="db", username="u", password="p"
            ),
        )
        sink = PostgresSink(settings)

        point_a = SimpleNamespace(exit_code=0, order_id=None)
        point_b = SimpleNamespace(exit_code=0, order_id=99)
        results = [
            ComputeResult(point=_as_point(point_a)),
            ComputeResult(point=_as_point(point_b)),
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
            ),
        ):
            _ = sink.write_batch(order_id=42, results=results)

        self.assertEqual(point_a.order_id, 42)
        # Pre-existing ``order_id`` is overwritten -- the contract is
        # "sink owns this field for the lifetime of the batch".
        self.assertEqual(point_b.order_id, 42)

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

        good = SimpleNamespace(exit_code=0, order_id=None)
        bad = SimpleNamespace(exit_code=0, order_id=None)
        results = [
            ComputeResult(point=_as_point(good)),
            ComputeResult(point=_as_point(bad)),
        ]

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        def insert_point(_conn, _order_id, point) -> int:
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
            outcomes = sink.write_batch(order_id=7, results=results)

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

        good_a = SimpleNamespace(exit_code=0, order_id=None)
        bad = SimpleNamespace(exit_code=0, order_id=None)
        good_b = SimpleNamespace(exit_code=1, order_id=None)
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

        def insert_point(_conn, _order_id, point) -> int:
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
            outcomes = sink.write_batch(
                order_id=7,
                results=results,
                progress=progress,
            )

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
