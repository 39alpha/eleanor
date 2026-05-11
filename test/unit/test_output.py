import io
import logging
import warnings
from collections.abc import Sequence
from contextlib import nullcontext
from types import SimpleNamespace
from typing import cast, override
from unittest import mock

import eleanor.variable_space as vs
from eleanor.config import Config
from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.order import Order
from eleanor.output import ComputeResult, ErrorInfo, OutputSink, PostgresSink, RunStats, WriteOutcome
from eleanor.output.factories import build_postgres as _build_postgres
from eleanor.output.postgres.config import DatabaseConfig
from eleanor.progress import ProgressHandle

from .common import TestCase


def _as_order(order: SimpleNamespace) -> Order:
    return cast(Order, cast(object, order))


def _as_point(point: SimpleNamespace) -> vs.Point:
    return cast(vs.Point, cast(object, point))


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
            WriteOutcome(exit_code=0, committed=True),
            WriteOutcome(exit_code=1, committed=True),
            WriteOutcome(exit_code=0, committed=False, error_message="x"),
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
            OutputSink()  # pyright: ignore[reportAbstractUsage]

    def test_output_sink_defaults_to_no_worker_writes(self):
        """
        Ensure OutputSink subclasses that do not override supports_worker_writes
        opt out of worker-side writes by default.
        """

        class MinimalSink(OutputSink):
            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def write_batch(self, order_id: int, results: Sequence[ComputeResult], progress=None) -> list[WriteOutcome]:
                _ = progress
                return []

            @override
            def finalize_run(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_worker_writes())

    def test_output_sink_defaults_to_no_progress(self):
        """
        Ensure OutputSink subclasses that do not override supports_progress
        opt out of the output bar by default -- protecting third-party sinks
        from silent breakage when the progress protocol evolves.
        """

        class MinimalSink(OutputSink):
            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def write_batch(self, order_id: int, results: Sequence[ComputeResult], progress=None) -> list[WriteOutcome]:
                _ = progress
                return []

            @override
            def finalize_run(self) -> None:
                pass

        self.assertFalse(MinimalSink().supports_progress())

    def test_output_sink_context_manager_calls_initialize_and_finalize(self):
        """
        Ensure OutputSink.__enter__ calls initialize and returns the sink,
        and __exit__ calls finalize, matching the AbstractExecutor pattern.
        """

        calls: list[str] = []

        class RecordingSink(OutputSink):
            @override
            def initialize(self) -> None:
                calls.append("initialize")

            @override
            def begin_run(self, order: Order) -> int:
                _ = order
                return 0

            @override
            def write_batch(
                self, order_id: int, results: Sequence[ComputeResult], progress: ProgressHandle | None = None
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

    def test_postgres_sink_rejects_non_postgres_dialect(self):
        """
        Ensure sink-specific dialect validation rejects non-postgresql configs.
        """
        cfg = DatabaseConfig(dialect="sqlite", database="db", username="u", password="p")
        with self.assertRaises(EleanorConfigurationException):
            _ = PostgresSink(cfg)

    def test_postgres_initialize_runs_setup_schema(self):
        """
        Ensure PostgresSink.initialize calls repositories.setup_schema once
        with the active config, and -- with bulk_load_optimization off --
        does NOT call drop_indexes.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)
        with (
            mock.patch("eleanor.output.postgres.sink.repositories.setup_schema") as setup_schema,
            mock.patch("eleanor.output.postgres.sink.repositories.drop_indexes") as drop_indexes,
        ):
            sink.initialize()
        setup_schema.assert_called_once_with(cfg)
        drop_indexes.assert_not_called()

    def test_postgres_initialize_drops_indexes_when_bulk_load_optimization_is_on(self):
        """
        Ensure PostgresSink.initialize calls
        :func:`repositories.drop_indexes` *after* ``setup_schema`` when
        the sink was constructed with ``bulk_load_optimization=True``.
        The order matters: tables must exist before we try to alter
        them on a fresh database.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg, bulk_load_optimization=True)
        manager = mock.MagicMock()
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.setup_schema",
                manager.setup_schema,
            ),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.drop_indexes",
                manager.drop_indexes,
            ),
        ):
            sink.initialize()
        manager.setup_schema.assert_called_once_with(cfg)
        manager.drop_indexes.assert_called_once_with(cfg)
        # mock.Mock records every child-attr call on the parent in order;
        # we use that ordering to pin the schema-then-drop sequence.
        self.assertEqual(
            [c[0] for c in manager.method_calls],
            ["setup_schema", "drop_indexes"],
        )

    def test_postgres_finalize_closes_connection(self):
        """
        Ensure PostgresSink.finalize closes the persistent connection
        through ``connection_module.close_connection``, and -- with
        bulk_load_optimization off -- does NOT call recreate_indexes.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)
        with (
            mock.patch("eleanor.output.postgres.sink.connection_module.close_connection") as close,
            mock.patch("eleanor.output.postgres.sink.repositories.recreate_indexes") as recreate,
        ):
            sink.finalize()
        close.assert_called_once_with(cfg)
        recreate.assert_not_called()

    def test_postgres_finalize_recreates_indexes_when_bulk_load_optimization_is_on(self):
        """
        Ensure PostgresSink.finalize calls
        :func:`repositories.recreate_indexes` *before* the connection
        is closed when the sink was constructed with
        ``bulk_load_optimization=True``. Order matters: the recreate
        uses the same connection cache, so it must run before
        ``close_connection`` evicts the cached entry.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg, bulk_load_optimization=True)
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
        manager.recreate_indexes.assert_called_once_with(cfg)
        manager.close_connection.assert_called_once_with(cfg)
        self.assertEqual(
            [c[0] for c in manager.method_calls],
            ["recreate_indexes", "close_connection"],
        )

    def test_postgres_finalize_still_closes_connection_when_recreate_raises(self):
        """
        Ensure PostgresSink.finalize closes the persistent connection
        even when :func:`recreate_indexes` raises -- typically because
        the bulk-loaded data violates a constraint. The recreate
        exception must propagate to the caller (so the failure isn't
        silently swallowed) but the libpq socket must not leak.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg, bulk_load_optimization=True)
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
        close.assert_called_once_with(cfg)

    def test_postgres_verbose_initialize_finalize_restores_psycopg_log_level(self):
        """
        Ensure a verbose sink snapshots the psycopg logger's level
        during :meth:`initialize` and restores it during
        :meth:`finalize`.  A redundant second ``initialize`` must
        not clobber the original snapshot.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg, verbose=True)
        logger = logging.getLogger("psycopg")
        original_level = logging.WARNING
        logger.setLevel(original_level)
        try:
            with mock.patch("eleanor.output.postgres.sink.repositories.setup_schema"):
                sink.initialize()
            self.assertEqual(logger.level, logging.DEBUG)
            # Second initialize must NOT overwrite the snapshot.
            with mock.patch("eleanor.output.postgres.sink.repositories.setup_schema"):
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

    def test_postgres_finalize_run_is_noop(self):
        """
        Ensure PostgresSink.finalize_run is a no-op today (reserved for
        the bulk-load follow-up).
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)
        # Just verify it returns without raising / reaching the connection layer.
        sink.finalize_run()

    def test_postgres_begin_run_returns_existing_order_id(self):
        """
        Ensure begin_run returns existing order.id and copies stored eleanor_version when unset.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=17, eleanor_version=None)
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        with (
            mock.patch("eleanor.output.postgres.sink.repositories.get_order", return_value=existing) as get_order,
            mock.patch("eleanor.output.postgres.sink.repositories.insert_order") as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 17)
        self.assertEqual(order.eleanor_version, "v1")
        get_order.assert_called_once_with(cfg, 17)
        insert_order.assert_not_called()

    def test_postgres_begin_run_writes_order_with_preassigned_id(self):
        """
        Ensure begin_run inserts a caller-preassigned id when no matching row exists.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=99, eleanor_version=None)

        with (
            mock.patch("eleanor.output.postgres.sink.repositories.get_order", return_value=None),
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_order",
                return_value=SimpleNamespace(id=99),
            ) as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 99)
        self.assertEqual(order.id, 99)
        self.assertIsNotNone(order.eleanor_version)
        insert_order.assert_called_once_with(cfg, order)

    def test_postgres_begin_run_raises_on_version_mismatch(self):
        """
        Ensure begin_run rejects extending an order from a different Eleanor version.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=17, eleanor_version="v2")
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        with (
            mock.patch("eleanor.output.postgres.sink.repositories.get_order", return_value=existing),
            self.assertRaisesRegex(EleanorException, "different version of Eleanor"),
        ):
            sink.begin_run(_as_order(order))

    def test_postgres_begin_run_writes_new_order_and_returns_id(self):
        """
        Ensure begin_run writes a new order and returns its generated id.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=None, eleanor_version=None)
        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.insert_order",
                return_value=SimpleNamespace(id=42),
            ) as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 42)
        self.assertEqual(order.id, 42)
        self.assertIsNotNone(order.eleanor_version)
        insert_order.assert_called_once_with(cfg, order)

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
        Ensure write_batch catches per-point failures via savepoints and
        keeps processing the batch, committing the surviving rows in a
        single outer commit.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        good_point = SimpleNamespace(exit_code=0, order_id=None)
        bad_point = SimpleNamespace(exit_code=0, order_id=None)
        results = [ComputeResult(point=_as_point(good_point)), ComputeResult(point=_as_point(bad_point))]

        # ``conn.transaction()`` is used both for the outer batch transaction
        # and the per-VS-point savepoint. ``nullcontext`` is a stateless
        # stand-in that propagates exceptions instead of swallowing them
        # like a default MagicMock ``__exit__`` would.
        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        def insert_point(_conn, _order_id, point):
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

    def test_write_batch_ticks_progress_only_for_committed_rows(self):
        """
        Ensure PostgresSink.write_batch emits one progress tick per durably-
        written row and no tick for a row that failed to write.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

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

        def insert_point(_conn, _order_id, point):
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

    def test_write_batch_without_progress_handle_is_silent(self):
        """
        Ensure PostgresSink.write_batch tolerates progress=None (the default).
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

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

    def test_build_postgres_recognizes_database_kwarg(self):
        """
        Ensure the postgres factory accepts a ``database`` keyword argument
        without warning. The registry splats ``output.args`` as kwargs, so the
        factory must treat ``database`` as a recognized name.
        """
        cfg = Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {"database": {"database": "db", "username": "u", "password": "p"}},
                },
            }
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sink = _build_postgres(cfg, database=cfg.output.args["database"])
        self.assertIsInstance(sink, PostgresSink)
        self.assertEqual([w for w in caught if issubclass(w.category, RuntimeWarning)], [])

    def test_build_postgres_warns_on_unknown_kwargs(self):
        """
        Ensure the postgres factory warns about kwargs other than ``database``.
        """
        cfg = Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {"database": {"database": "db", "username": "u", "password": "p"}},
                },
            }
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _ = _build_postgres(cfg, database=cfg.output.args["database"], foo=1)
        runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        self.assertEqual(len(runtime_warnings), 1)
        self.assertIn("foo", str(runtime_warnings[0].message))

    def test_build_postgres_without_database_kwarg_uses_default_config(self):
        """
        Ensure ``_build_postgres`` falls through to a default ``DatabaseConfig``
        when the registry hands it no ``database`` block. The factory must
        still produce a usable ``PostgresSink`` -- the dialect default is
        ``'postgresql'`` so the sink's own dialect check passes.
        """
        cfg = Config(raw={"output": {"type": "postgres", "args": {}}})
        sink = _build_postgres(cfg)
        self.assertIsInstance(sink, PostgresSink)
        self.assertEqual(sink.config.dialect, "postgresql")

    def test_build_postgres_propagates_verbose(self):
        """
        Ensure the ``verbose`` kwarg threads from the factory into the sink
        so verbose runs flip the same flag the sink consults internally.
        """
        cfg = Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {"database": {"database": "db", "username": "u", "password": "p"}},
                },
            }
        )
        sink = _build_postgres(
            cfg,
            database=cfg.output.args["database"],
            verbose=True,
        )
        self.assertTrue(sink.verbose)

    def test_build_postgres_threads_bulk_load_optimization_to_sink(self):
        """
        Ensure ``bulk_load_optimization`` (a sibling of ``database`` in
        ``output.args``) is recognised by the factory without warning
        and lands on the sink instance rather than on the
        :class:`DatabaseConfig`. The flag is a sink-behaviour knob, so
        keeping it off the connection-config dataclass keeps the
        connection-cache key stable across runs that toggle it.
        """
        cfg = Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {
                        "database": {"database": "db", "username": "u", "password": "p"},
                        "bulk_load_optimization": True,
                    },
                },
            }
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sink = _build_postgres(
                cfg,
                database=cfg.output.args["database"],
                bulk_load_optimization=cfg.output.args["bulk_load_optimization"],
            )
        self.assertIsInstance(sink, PostgresSink)
        self.assertTrue(sink.bulk_load_optimization)
        # The factory must NOT have stuffed the flag onto the
        # connection-config dataclass; that field no longer exists.
        self.assertFalse(hasattr(sink.config, "bulk_load_optimization"))
        # And it must not have warned about an unknown kwarg.
        self.assertEqual(
            [w for w in caught if issubclass(w.category, RuntimeWarning)],
            [],
        )

    def test_build_postgres_defaults_bulk_load_optimization_to_false(self):
        """
        Ensure ``bulk_load_optimization`` defaults to ``False`` when the
        config doesn't mention it -- matching the safe-default contract
        documented on :class:`PostgresSink`.
        """
        cfg = Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {"database": {"database": "db", "username": "u", "password": "p"}},
                },
            }
        )
        sink = _build_postgres(cfg, database=cfg.output.args["database"])
        self.assertFalse(sink.bulk_load_optimization)

    def test_postgres_begin_run_returns_existing_id_when_versions_match(self):
        """
        Ensure begin_run is a no-op insert when the caller supplies an
        ``order.id`` whose row already exists with a matching
        ``eleanor_version`` -- the existing id is returned without re-
        inserting.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=17, eleanor_version="v1")
        existing = SimpleNamespace(id=17, eleanor_version="v1")

        with (
            mock.patch(
                "eleanor.output.postgres.sink.repositories.get_order",
                return_value=existing,
            ) as get_order,
            mock.patch("eleanor.output.postgres.sink.repositories.insert_order") as insert_order,
        ):
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 17)
        self.assertEqual(order.eleanor_version, "v1")
        get_order.assert_called_once_with(cfg, 17)
        insert_order.assert_not_called()

    def test_postgres_begin_run_preserves_caller_supplied_version_on_fresh_insert(self):
        """
        Ensure begin_run keeps the caller's ``order.eleanor_version`` when it
        is already set and the order has no id yet -- only the unset case
        gets the running ``__version__`` stamped on it.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        order = SimpleNamespace(id=None, eleanor_version="custom-v1")
        with mock.patch(
            "eleanor.output.postgres.sink.repositories.insert_order",
            return_value=SimpleNamespace(id=42),
        ) as insert_order:
            order_id = sink.begin_run(_as_order(order))

        self.assertEqual(order_id, 42)
        self.assertEqual(order.eleanor_version, "custom-v1")
        insert_order.assert_called_once_with(cfg, order)

    def test_write_batch_with_empty_results_returns_empty_outcomes(self):
        """
        Ensure an empty batch is a clean no-op: no per-VS-point work is
        scheduled, ``insert_point`` is never invoked, and the returned
        outcomes list is empty. Callers (notably the executor loop) treat
        an empty list as "this batch contributed zero rows".
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

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

    def test_write_batch_mutates_point_order_id(self):
        """
        Ensure ``write_batch`` stamps ``order_id`` on every result's point
        before persistence. The docstring documents this as a deliberate
        side effect so downstream code can read ``point.order_id`` without
        consulting the batch context.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        point_a = SimpleNamespace(exit_code=0, order_id=None)
        point_b = SimpleNamespace(exit_code=0, order_id=99)
        results = [ComputeResult(point=_as_point(point_a)), ComputeResult(point=_as_point(point_b))]

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

    def test_write_batch_logs_per_point_failure_to_stderr_with_traceback(self):
        """
        Ensure savepoint-rolled-back failures get logged on stderr with
        the VS-point index, the exception class name, the message, and
        a full traceback. Without this output we can't tell why a batch
        wrote less than expected; the silent-failure regression is the
        whole reason this branch exists.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

        good = SimpleNamespace(exit_code=0, order_id=None)
        bad = SimpleNamespace(exit_code=0, order_id=None)
        results = [ComputeResult(point=_as_point(good)), ComputeResult(point=_as_point(bad))]

        fake_conn = mock.MagicMock()
        fake_conn.transaction.return_value = nullcontext()

        def insert_point(_conn, _order_id, point):
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

    def test_postgres_lazy_re_exports_resolve_via_getattr(self):
        """
        Ensure :mod:`eleanor.output.postgres`'s :pep:`562` ``__getattr__``
        hook successfully resolves every documented re-export
        (``DatabaseConfig``, ``DatabaseRaw``, ``PostgresArgsRaw``,
        ``PostgresSink``, ``database_config_from_config``) and raises
        ``AttributeError`` for any unknown name. The lazy import keeps
        SQLAlchemy off the module-load critical path; this test pins
        the contract down so a refactor cannot silently regress it.
        """
        import eleanor.output.postgres as postgres_pkg
        from eleanor.output.postgres.config import (
            DatabaseConfig as _DatabaseConfig,
        )
        from eleanor.output.postgres.config import (
            DatabaseRaw as _DatabaseRaw,
        )
        from eleanor.output.postgres.config import (
            PostgresArgsRaw as _PostgresArgsRaw,
        )
        from eleanor.output.postgres.config import (
            database_config_from_config as _database_config_from_config,
        )
        from eleanor.output.postgres.sink import PostgresSink as _PostgresSink

        self.assertIs(postgres_pkg.DatabaseConfig, _DatabaseConfig)
        self.assertIs(postgres_pkg.DatabaseRaw, _DatabaseRaw)
        self.assertIs(postgres_pkg.PostgresArgsRaw, _PostgresArgsRaw)
        self.assertIs(postgres_pkg.database_config_from_config, _database_config_from_config)
        self.assertIs(postgres_pkg.PostgresSink, _PostgresSink)
        with self.assertRaisesRegex(AttributeError, "no attribute"):
            _ = postgres_pkg.nonexistent_symbol  # type: ignore[attr-defined]

    def test_write_batch_outer_commit_failure_demotes_pending_slots(self):
        """
        Ensure an outer-transaction commit failure rewrites every pending
        success placeholder to a failed ``WriteOutcome`` carrying the commit
        error, while leaving per-VS-point failures (which already have an
        error message recorded inside the loop) untouched. Progress is not
        ticked because no row durably committed.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sink = PostgresSink(cfg)

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

        def insert_point(_conn, _order_id, point):
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
