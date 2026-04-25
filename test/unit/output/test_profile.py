"""Unit tests for the psycopg3-based StatementProfiler.

These cover counter behaviour and lifecycle without spinning up a real
psycopg connection. End-to-end behaviour (cursor_factory swapping,
``executemany`` row-counting against actual psycopg) is exercised by the
real-PG integration suite.
"""
from types import SimpleNamespace
from unittest import mock

import eleanor.output.postgres.tools.profile as profile_module
from eleanor.output.postgres.config import DatabaseConfig
from eleanor.output.postgres.tools.profile import StatementProfiler, _ProfilingCursor, _to_text

from ..common import TestCase


class TestStatementProfilerLifecycle(TestCase):
    """
    The profiler context manager swaps a cursor_factory in and restores it
    on exit, and is non-reentrant.
    """

    def test_cannot_be_entered_twice(self):
        """
        Ensure re-entering a profiler instance raises rather than double-
        installing the cursor_factory swap.
        """
        prof = StatementProfiler()
        with prof:
            with self.assertRaises(RuntimeError):
                with prof:
                    pass

    def test_only_one_active_profiler_at_a_time(self):
        """
        Ensure two profilers cannot be active simultaneously -- the second
        ``__enter__`` raises.
        """
        outer = StatementProfiler()
        inner = StatementProfiler()
        with outer:
            with self.assertRaises(RuntimeError):
                with inner:
                    pass

    def test_exit_restores_connection_module_connect(self):
        """
        Ensure :func:`connection_module.connect` is restored to its original
        binding after the profiler exits.
        """
        from eleanor.output.postgres.persistence import connection as connection_module

        original = connection_module.connect
        with StatementProfiler():
            self.assertIsNot(connection_module.connect, original)
        self.assertIs(connection_module.connect, original)


class TestStatementProfilerCounters(TestCase):
    """
    Counter bookkeeping in :meth:`StatementProfiler._record_before` /
    ``_record_after`` is the part of the profiler we can exercise without
    a real psycopg connection.
    """

    def test_records_single_row_insert_by_table(self):
        """
        Ensure a single-row ``INSERT INTO foo ...`` increments the
        per-table statement and row counters.
        """
        prof = StatementProfiler()
        cursor = SimpleNamespace(rowcount=1)
        prof._record_before(  # pyright: ignore[reportPrivateUsage]
            cursor,
            'INSERT INTO foo (a) VALUES (%(a)s)',
            {'a': 1},
            executemany=False,
        )
        prof._record_after(cursor, elapsed=0.001)  # pyright: ignore[reportPrivateUsage]

        self.assertEqual(prof.insert_statements_by_table['foo'], 1)
        self.assertEqual(prof.insert_rows_by_table['foo'], 1)
        self.assertEqual(prof.total_statements, 1)

    def test_records_executemany_row_count_from_params_seq(self):
        """
        Ensure executemany INSERTs credit one statement and ``len(params)`` rows.
        """
        prof = StatementProfiler()
        cursor = SimpleNamespace(rowcount=3)
        prof._record_before(  # pyright: ignore[reportPrivateUsage]
            cursor,
            'INSERT INTO foo (a) VALUES (%(a)s)',
            [{'a': 1}, {'a': 2}, {'a': 3}],
            executemany=True,
        )
        prof._record_after(cursor, elapsed=0.001)  # pyright: ignore[reportPrivateUsage]

        self.assertEqual(prof.insert_statements_by_table['foo'], 1)
        self.assertEqual(prof.insert_rows_by_table['foo'], 3)

    def test_reconciles_rowcount_against_parameter_estimate(self):
        """
        Ensure the after-hook upgrades the parameter-based estimate when
        ``cursor.rowcount`` reports more rows. Mirrors psycopg3's
        ``insertmanyvalues`` path where many rows ship in one statement.
        """
        prof = StatementProfiler()
        cursor = SimpleNamespace(rowcount=42)
        # Parameter-based estimate would credit 1 row (single dict, not
        # an executemany), while ``cursor.rowcount=42`` is the truth.
        prof._record_before(  # pyright: ignore[reportPrivateUsage]
            cursor,
            'INSERT INTO foo (a) VALUES (%(a)s)',
            {'a': 1},
            executemany=False,
        )
        prof._record_after(cursor, elapsed=0.0)  # pyright: ignore[reportPrivateUsage]

        self.assertEqual(prof.insert_rows_by_table['foo'], 42)
        self.assertEqual(prof.total_rows_inserted, 42)

    def test_records_copy_statement_as_bulk_write(self):
        """
        Ensure ``COPY {table} ... FROM STDIN ...`` is bucketed under the
        same per-table counters as INSERT, with ``cursor.rowcount`` driving
        the after-the-fact row total. Without this, binary-COPY leaf
        inserts vanish from the report once ``_bulk_insert`` routes large
        batches through COPY instead of executemany.
        """
        prof = StatementProfiler()
        cursor = SimpleNamespace(rowcount=1500)
        prof._record_before(  # pyright: ignore[reportPrivateUsage]
            cursor,
            'COPY "equilibrium_aqueous_species" ("equilibrium_space_id", "name") '
            'FROM STDIN WITH (FORMAT BINARY)',
            None,
            executemany=False,
        )
        prof._record_after(cursor, elapsed=0.01)  # pyright: ignore[reportPrivateUsage]

        self.assertEqual(prof.insert_statements_by_table['equilibrium_aqueous_species'], 1)
        self.assertEqual(prof.insert_rows_by_table['equilibrium_aqueous_species'], 1500)
        self.assertEqual(prof.total_rows_inserted, 1500)
        # COPY must not also leak into the ``other_statements`` keyword bucket.
        self.assertNotIn('COPY', prof.other_statements)

    def test_buckets_non_insert_statements(self):
        """
        Ensure non-INSERT statements are bucketed by their leading keyword.
        """
        prof = StatementProfiler()
        cursor = SimpleNamespace(rowcount=-1)
        prof._record_before(cursor, 'BEGIN', None, executemany=False)  # pyright: ignore[reportPrivateUsage]
        prof._record_after(cursor, elapsed=0.0)  # pyright: ignore[reportPrivateUsage]
        prof._record_before(cursor, 'COMMIT', None, executemany=False)  # pyright: ignore[reportPrivateUsage]
        prof._record_after(cursor, elapsed=0.0)  # pyright: ignore[reportPrivateUsage]
        prof._record_before(cursor, 'SELECT 1', None, executemany=False)  # pyright: ignore[reportPrivateUsage]
        prof._record_after(cursor, elapsed=0.0)  # pyright: ignore[reportPrivateUsage]

        self.assertEqual(prof.other_statements['BEGIN'], 1)
        self.assertEqual(prof.other_statements['COMMIT'], 1)
        self.assertEqual(prof.other_statements['SELECT'], 1)

    def test_report_renders_without_error(self):
        """
        Ensure :meth:`StatementProfiler.report` produces a non-empty summary
        after capturing some traffic. Wording is intentionally not pinned --
        this is a smoke test of the formatter.
        """
        prof = StatementProfiler()
        cursor = SimpleNamespace(rowcount=1)
        prof._record_before(  # pyright: ignore[reportPrivateUsage]
            cursor,
            'INSERT INTO orders (a) VALUES (%(a)s)',
            {'a': 1},
            executemany=False,
        )
        prof._record_after(cursor, elapsed=0.001)  # pyright: ignore[reportPrivateUsage]

        report = prof.report()
        self.assertIn('Total statements', report)
        self.assertIn('orders', report)


class TestStatementProfilerConnectionRetrofit(TestCase):
    """
    Connections present in the persistence module's cache when the profiler
    activates have their ``cursor_factory`` swapped, and the swap is undone
    on exit.
    """

    def test_existing_connections_get_factory_swapped(self):
        """
        Ensure connections in :data:`connection_module._connections` at
        ``__enter__`` time have their ``cursor_factory`` set to the
        profiling subclass and restored on exit.
        """
        from eleanor.output.postgres.persistence import connection as connection_module

        fake_conn = mock.MagicMock()
        original_factory = mock.sentinel.original_factory
        fake_conn.cursor_factory = original_factory
        with mock.patch.dict(
            connection_module._connections,  # pyright: ignore[reportPrivateUsage]
            {('cfg-key', 0): fake_conn},
            clear=False,
        ):
            with StatementProfiler():
                self.assertIs(fake_conn.cursor_factory, _ProfilingCursor)
            self.assertIs(fake_conn.cursor_factory, original_factory)


class TestToText(TestCase):
    """Per-input-shape coverage of the :func:`_to_text` query rendering helper."""

    def test_renders_sql_objects_via_as_string(self):
        """Ensure ``sql.SQL`` and ``sql.Composed`` go through ``as_string(None)``."""
        from psycopg import sql

        self.assertEqual(_to_text(sql.SQL('SELECT 1')), 'SELECT 1')
        composed = sql.SQL('INSERT INTO {t} (a) VALUES (%s)').format(t=sql.Identifier('foo'))
        self.assertIn('INSERT INTO "foo"', _to_text(composed))

    def test_decodes_bytes_to_utf8_with_replacement(self):
        """
        Ensure ``_to_text`` decodes ``bytes`` queries through utf-8 with
        ``errors='replace'`` -- the profiler must never raise on a query
        that happens to contain non-utf8 bytes.
        """
        self.assertEqual(_to_text(b'SELECT 1'), 'SELECT 1')
        self.assertEqual(_to_text(b'SELECT \xff'), 'SELECT \ufffd')

    def test_falls_back_to_str_for_unknown_query_shapes(self):
        """Ensure non-SQL/Composed/bytes inputs fall through to :func:`str`."""
        self.assertEqual(_to_text('SELECT 1'), 'SELECT 1')

        class _Custom:
            def __str__(self) -> str:
                return 'COPY foo FROM STDIN'

        self.assertEqual(_to_text(_Custom()), 'COPY foo FROM STDIN')


class TestStatementProfilerWiringEdges(TestCase):
    """Defensive edge cases in :class:`StatementProfiler`'s wiring."""

    def test_wrapped_connect_raises_when_real_connect_was_not_captured(self):
        """
        Ensure :meth:`_wrapped_connect` refuses to silently call into a
        ``None`` saved reference. The defensive ``if`` guards against a
        misuse of the profiler outside its ``__enter__`` block (e.g. a
        test directly invoking ``_wrapped_connect``).
        """
        prof = StatementProfiler()
        cfg = DatabaseConfig(database='db', username='u', password='p')
        with self.assertRaisesRegex(
            RuntimeError, '_real_connect not captured',
        ):
            _ = prof._wrapped_connect(cfg)  # pyright: ignore[reportPrivateUsage]

    def test_report_renders_other_statements_section_with_recorded_kinds(self):
        """
        Ensure :meth:`StatementProfiler.report` renders the ``Other
        statements`` section with each non-INSERT/COPY keyword the
        profiler observed. Without a non-bulk-write statement on record,
        that section's loop body never runs.
        """
        prof = StatementProfiler()
        cursor = SimpleNamespace(rowcount=-1)
        prof._record_before(cursor, 'BEGIN', None, executemany=False)  # pyright: ignore[reportPrivateUsage]
        prof._record_after(cursor, elapsed=0.0)  # pyright: ignore[reportPrivateUsage]

        report = prof.report()
        self.assertIn('Other statements:', report)
        self.assertIn('BEGIN', report)
        self.assertEqual(prof.other_statements['BEGIN'], 1)


class TestProfilingCursorPassthrough(TestCase):
    """With no active profiler, every override delegates to ``psycopg.Cursor``.

    These tests guard the no-op fast path the cursor takes when the
    process-local ``_active`` slot is ``None`` -- the default state
    outside a ``with StatementProfiler():`` block.
    """

    def test_execute_passes_through_when_no_active_profiler(self):
        """Ensure :meth:`_ProfilingCursor.execute` calls ``super().execute`` directly."""
        cursor = _ProfilingCursor.__new__(_ProfilingCursor)
        sentinel = object()
        with (
            mock.patch.object(profile_module, '_active', None),
            mock.patch(
                'eleanor.output.postgres.tools.profile.psycopg.Cursor.execute',
                return_value=sentinel,
            ) as super_execute,
        ):
            got = cursor.execute('SELECT 1', None)
        self.assertIs(got, sentinel)
        super_execute.assert_called_once()

    def test_executemany_passes_through_when_no_active_profiler(self):
        """Ensure :meth:`_ProfilingCursor.executemany` is a no-op wrapper."""
        cursor = _ProfilingCursor.__new__(_ProfilingCursor)
        sentinel = object()
        with (
            mock.patch.object(profile_module, '_active', None),
            mock.patch(
                'eleanor.output.postgres.tools.profile.psycopg.Cursor.executemany',
                return_value=sentinel,
            ) as super_executemany,
        ):
            got = cursor.executemany('INSERT INTO foo VALUES (%s)', [(1,), (2,)])
        self.assertIs(got, sentinel)
        super_executemany.assert_called_once()

    def test_copy_passes_through_when_no_active_profiler(self):
        """Ensure :meth:`_ProfilingCursor.copy` is a context-manager passthrough."""
        cursor = _ProfilingCursor.__new__(_ProfilingCursor)
        copy_obj = mock.MagicMock()
        cm = mock.MagicMock()
        cm.__enter__.return_value = copy_obj
        cm.__exit__.return_value = False
        with (
            mock.patch.object(profile_module, '_active', None),
            mock.patch(
                'eleanor.output.postgres.tools.profile.psycopg.Cursor.copy',
                return_value=cm,
            ) as super_copy,
        ):
            with cursor.copy('COPY foo FROM STDIN') as cp:
                self.assertIs(cp, copy_obj)
        super_copy.assert_called_once()
