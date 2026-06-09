import re
import time
from collections import Counter
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import TracebackType
from typing import override

import psycopg
from psycopg import sql
from psycopg.abc import Params, QueryNoTemplate
from psycopg.copy import Copy, Writer
from psycopg.rows import TupleRow

from eleanor.exceptions import EleanorException
from eleanor.output.postgres.persistence import connection as connection_module
from eleanor.output.postgres.settings import PostgresDatabaseSettings

# Bulk-write detector: matches ``INSERT INTO {table}`` and
# ``COPY {table}`` (the form ``_bulk_copy`` emits, with FROM STDIN). Both
# are bucketed under the same per-table counters in the report because
# they're two implementations of the same logical operation -- a fast
# bulk write into a known table -- and conflating them keeps the
# "INSERTs by statement count" view legible when ``_bulk_insert`` swaps
# between the two paths above the COPY threshold.
_BULK_WRITE_RE = re.compile(
    r'^\s*(?:INSERT\s+INTO|COPY)\s+"?(?P<table>\w+)"?',
    re.IGNORECASE,
)


# Process-local handle to the currently active profiler. ``__enter__`` sets
# it; ``__exit__`` clears it. ``_ProfilingCursor`` consults this so the
# cursor subclass stays a no-cost passthrough when no profiler is active.
_active: StatementProfiler | None = None


class _ProfilingCursor(psycopg.Cursor[TupleRow]):
    """Cursor subclass that reports execute / executemany to the active profiler.

    Override signatures track ``psycopg.Cursor.execute`` /
    ``executemany`` exactly so we satisfy LSP. The ``# pyright: ignore``
    on ``_record_before`` / ``_record_after`` is intentional: those
    methods are private to :class:`StatementProfiler` and the cursor is
    its only legitimate caller.
    """

    @override
    def execute(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        query: QueryNoTemplate,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ) -> "psycopg.Cursor[TupleRow]":
        # ``psycopg.Cursor.execute``'s type stub admits ``Query`` (which
        # includes ``string.templatelib.Template``), but the runtime
        # implementation only accepts ``QueryNoTemplate``. Narrowing the
        # override matches reality at the cost of one suppression.
        prof = _active
        if prof is None:
            return super().execute(query, params, prepare=prepare, binary=binary)
        prof._record_before(self, _to_text(query), params, executemany=False)  # pyright: ignore[reportPrivateUsage]
        t0 = time.perf_counter()
        try:
            return super().execute(query, params, prepare=prepare, binary=binary)
        finally:
            prof._record_after(self, time.perf_counter() - t0)  # pyright: ignore[reportPrivateUsage]

    @override
    def executemany(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        query: QueryNoTemplate,
        params_seq: Iterable[Params],
        *,
        returning: bool = False,
    ) -> None:
        # See the comment on :meth:`execute`; same narrowing applies.
        prof = _active
        if prof is None:
            return super().executemany(query, params_seq, returning=returning)
        prof._record_before(self, _to_text(query), params_seq, executemany=True)  # pyright: ignore[reportPrivateUsage]
        t0 = time.perf_counter()
        try:
            return super().executemany(query, params_seq, returning=returning)
        finally:
            prof._record_after(self, time.perf_counter() - t0)  # pyright: ignore[reportPrivateUsage]

    @override
    @contextmanager
    def copy(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        statement: QueryNoTemplate,
        params: Params | None = None,
        *,
        writer: Writer | None = None,
    ) -> Generator[Copy]:
        # Mirror the ``execute`` shape: when no profiler is active, just
        # delegate to the parent's context manager. Otherwise time the whole
        # COPY round-trip and let ``_record_after`` reconcile the row count
        # from ``cursor.rowcount`` once the COPY commits.
        prof = _active
        if prof is None:
            with super().copy(statement, params, writer=writer) as cp:
                yield cp
            return
        prof._record_before(self, _to_text(statement), params, executemany=False)  # pyright: ignore[reportPrivateUsage]
        t0 = time.perf_counter()
        try:
            with super().copy(statement, params, writer=writer) as cp:
                yield cp
        finally:
            prof._record_after(self, time.perf_counter() - t0)  # pyright: ignore[reportPrivateUsage]


def _to_text(query: object) -> str:
    """Render a psycopg ``Query`` (str / bytes / SQL / Composed) as text for matching.

    The profiler only inspects the leading keyword and table name, so a
    best-effort string round-trip is fine. ``psycopg.sql.SQL`` /
    ``Composed`` expose ``as_string(None)``; everything else gets
    :func:`str`.
    """
    if isinstance(query, (sql.SQL, sql.Composed)):
        return query.as_string(None)
    if isinstance(query, bytes):
        return query.decode("utf-8", errors="replace")
    return str(query)


@dataclass
class StatementProfiler:
    """Counts and times SQL statements issued through any psycopg connection.

    Use as a context manager. The instance is *not* reentrant; create a
    fresh profiler per profiled run. Activation swaps a profiling
    ``cursor_factory`` onto every connection :mod:`connection` has cached
    plus any opened during the profiling window; exit restores the
    previous factories.
    """

    insert_statements_by_table: Counter[str] = field(default_factory=Counter)
    insert_rows_by_table: Counter[str] = field(default_factory=Counter)
    other_statements: Counter[str] = field(default_factory=Counter)
    total_statements: int = 0
    total_rows_inserted: int = 0
    total_cursor_time: float = 0.0
    _started: bool = False
    # ``cursor_factory`` overrides we installed and need to restore. Keyed
    # on ``id(connection)`` because ``Connection`` is not hashable.
    _prev_factories: dict[int, type[psycopg.Cursor[TupleRow]]] = field(default_factory=dict)
    _patched_connections: list[psycopg.Connection] = field(default_factory=list)
    # ``_pending[id(cursor)]`` carries the table name + tentative row count
    # the corresponding ``execute`` recorded; ``_record_after`` reads it.
    _pending: dict[int, tuple[str, int] | None] = field(default_factory=dict)
    # Saved reference to the real ``connection.connect`` so ``__exit__`` can
    # restore it. Initialised in ``__enter__`` after we capture the value.
    _real_connect: Callable[[PostgresDatabaseSettings], psycopg.Connection] | None = None

    def __enter__(self) -> StatementProfiler:
        global _active  # noqa: PLW0603
        if self._started:
            msg = "StatementProfiler is not reentrant"
            raise EleanorException(msg)
        if _active is not None:
            msg = "another StatementProfiler is already active"
            raise EleanorException(msg)
        self._started = True
        _active = self
        # Retrofit every already-cached connection so any cursor() call
        # made through them during the profiling window goes through
        # _ProfilingCursor. Connections opened later via ``connect`` go
        # through ``_patch_factory`` below.
        # ``_connections`` is the persistence layer's process-local cache;
        # the profiler legitimately needs to see every existing connection
        # to retrofit the cursor_factory. Ignore the private-access warning.
        for conn in list(connection_module._connections.values()):  # pyright: ignore[reportPrivateUsage]
            self._patch_factory(conn)
        # Wrap ``connect`` so connections opened during the profiling
        # window also get the profiling factory installed.
        self._real_connect = connection_module.connect
        connection_module.connect = self._wrapped_connect
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        global _active  # noqa: PLW0603
        if self._real_connect is not None:
            connection_module.connect = self._real_connect
            self._real_connect = None
        for conn in self._patched_connections:
            prev = self._prev_factories.get(id(conn))
            # Restore whatever was there before; default cursor_factory if
            # we never saw a value.
            conn.cursor_factory = prev if prev is not None else psycopg.Cursor
        self._patched_connections.clear()
        self._prev_factories.clear()
        _active = None
        self._started = False

    def _record_before(
        self,
        cursor: psycopg.Cursor[TupleRow],
        query_text: str,
        params: object,
        executemany: bool,
    ) -> None:
        self.total_statements += 1
        match = _BULK_WRITE_RE.match(query_text)
        if match:
            table = match.group("table").lower()
            self.insert_statements_by_table[table] += 1
            # ``executemany`` is the only path where we have a reliable
            # parameter-sequence length up front; ``execute`` and ``copy``
            # both ship a single statement whose true row count surfaces
            # in ``cursor.rowcount`` after completion. ``_record_after``
            # corrects the tentative ``1`` from cursor.rowcount in those
            # cases (multi-row INSERTs and binary COPY both populate it).
            n_rows = 1
            if executemany and isinstance(params, Sequence) and not isinstance(params, (str, bytes)):
                n_rows = len(params)
            self.insert_rows_by_table[table] += n_rows
            self.total_rows_inserted += n_rows
            self._pending[id(cursor)] = (table, n_rows)
            return
        head = query_text.lstrip().split(None, 1)
        kind = head[0].upper() if head else "<empty>"
        self.other_statements[kind] += 1
        self._pending[id(cursor)] = None

    def _record_after(self, cursor: psycopg.Cursor[TupleRow], elapsed: float) -> None:
        self.total_cursor_time += elapsed
        pending = self._pending.pop(id(cursor), None)
        if pending is None:
            return
        table, tentative = pending
        # ``cursor.rowcount`` is the DB-API count of rows affected by the
        # most recent statement. For multi-row VALUES INSERTs (psycopg3's
        # `insertmanyvalues` path) it reports the true row count even
        # when our parameter-based estimate undercounted.
        actual = getattr(cursor, "rowcount", None)
        if isinstance(actual, int) and actual > 0 and actual != tentative:
            delta = actual - tentative
            self.insert_rows_by_table[table] += delta
            self.total_rows_inserted += delta

    def _patch_factory(self, conn: psycopg.Connection) -> None:
        """Save ``conn``'s previous ``cursor_factory`` and install ours."""
        if id(conn) in self._prev_factories:
            return
        self._prev_factories[id(conn)] = conn.cursor_factory
        conn.cursor_factory = _ProfilingCursor
        self._patched_connections.append(conn)

    def _wrapped_connect(self, config: PostgresDatabaseSettings) -> psycopg.Connection:
        """Drop-in replacement for :func:`connection.connect` while profiling."""
        if self._real_connect is None:
            msg = "StatementProfiler._real_connect not captured"
            raise EleanorException(msg)
        conn = self._real_connect(config)
        self._patch_factory(conn)
        return conn

    def report(self) -> str:
        """Return a multi-line human-readable summary of the captured stats."""
        lines = [
            f"Total statements:       {self.total_statements}",
            f"Total INSERTed rows:    {self.total_rows_inserted}",
            f"Total cursor time (s):  {self.total_cursor_time:.3f}",
            "",
            "Bulk writes (INSERT/COPY) by statement count (top 20):",
        ]
        for table, count in self.insert_statements_by_table.most_common(20):
            rows = self.insert_rows_by_table[table]
            avg = rows / count if count else 0.0
            lines.append(f"  {table:<40s}  {count:>8d} statements  {rows:>8d} rows  ({avg:6.2f}/stmt)")
        lines.append("")
        lines.append("Other statements:")
        for kind, count in self.other_statements.most_common():
            lines.append(f"  {kind:<40s}  {count:>8d}")
        return "\n".join(lines)


__all__ = ["StatementProfiler"]
