"""The built-in postgres :class:`OutputSink` implementation.

Talks to Postgres via psycopg3 through :mod:`persistence.repositories`.
The lifecycle hooks land on the right helpers:

* :meth:`initialize` -- opens the persistent connection, ensures the
  schema exists (eager: bad credentials / unreachable DB / schema-create
  failures surface before any work is queued), and -- when the sink
  was constructed with ``bulk_load_optimization=True`` -- strips every
  secondary index + FK / CHECK constraint via
  :func:`repositories.drop_indexes` so the per-row INSERT / COPY hot
  path is unencumbered. Also raises the ``psycopg`` stdlib logger to
  ``DEBUG`` when the sink was constructed with ``verbose=True`` so
  connection-time and statement-level traffic shows up on whatever
  handlers the embedding application has configured.
* :meth:`begin_run` -- per-order metadata insert / version check.
* :meth:`write_batch` -- one outer transaction over the batch with a
  per-VS-point ``savepoint`` inside, so a single bad point only rolls
  back its own savepoint and the surviving rows commit together.
* :meth:`finalize_run` -- per-run no-op for now; reserved for run-scoped
  bookkeeping the future bulk-load follow-up will wire in.
* :meth:`finalize` -- when ``bulk_load_optimization=True``, reattaches
  the dropped indexes + constraints via
  :func:`repositories.recreate_indexes`, then closes the persistent
  connection. The recreate runs in a :keyword:`try` block so the
  connection is still closed even when the recreate fails (typically
  because the bulk-loaded data violates a constraint); the recreate
  exception then propagates to the caller.
"""

import logging
import sys
import traceback
from collections.abc import Sequence
from typing import override

from ...exceptions import EleanorConfigurationException, EleanorException
from ...order import Order
from ...progress import ProgressHandle
from ...version import __version__
from ..interface import ComputeResult, OutputSink, WriteOutcome
from .config import DatabaseConfig
from .persistence import connection as connection_module
from .persistence import repositories

#: Name of the stdlib logger psycopg3 uses for connection / statement diagnostics.
#: See https://www.psycopg.org/psycopg3/docs/basic/usage.html#connection-logging
_PSYCOPG_LOGGER_NAME = "psycopg"


class PostgresSink(OutputSink):
    """Persist Eleanor compute results into PostgreSQL via psycopg3.

    ``bulk_load_optimization`` (default ``False``) opts the sink in to
    a lifecycle-bracketed bulk-load window: :meth:`initialize` calls
    :func:`repositories.drop_indexes` after the schema is in place, and
    :meth:`finalize` calls :func:`repositories.recreate_indexes` just
    before the connection is closed. The constraints / indexes declared
    on the schema are therefore absent for the lifetime of the sink,
    which makes the per-row INSERT / COPY hot path substantially faster
    on large workloads. If the sink crashes between ``initialize`` and
    ``finalize`` -- e.g. the process is killed -- the constraints stay
    missing; ``eleanor bulkload recreate`` (or :func:`recreate_indexes`
    directly) will reattach them.
    """

    config: DatabaseConfig
    verbose: bool
    bulk_load_optimization: bool

    def __init__(
        self,
        config: DatabaseConfig,
        verbose: bool = False,
        bulk_load_optimization: bool = False,
    ):
        self.config = config
        self.verbose = verbose
        self.bulk_load_optimization = bulk_load_optimization
        if self.config.dialect != "postgresql":
            msg = f'the "{self.config.dialect}" database dialect is not supported; choose "postgresql"'
            raise EleanorConfigurationException(msg)

    @override
    def initialize(self) -> None:
        """Open the connection and ensure the schema. Runs once per sink instance.

        Per the lifecycle docstring on :class:`OutputSink`, this is the
        eager moment for connection / schema setup: we want bad
        credentials, network problems, or schema mismatch to surface
        before any work has been queued.
        """
        if self.verbose:
            # psycopg3 emits its own connection-attempt and statement
            # diagnostics through ``logging.getLogger("psycopg")``. We only
            # adjust the level here -- handler / formatter wiring is the
            # embedding application's responsibility, exactly as it is for
            # any other library logger. Doing this in ``initialize`` rather
            # than ``__init__`` keeps the side effect bracketed by the
            # sink's lifetime; ``finalize`` is a deliberate no-op for the
            # logger because we don't own the level the caller had before
            # us and silently restoring it would surprise applications
            # that configured logging themselves.
            logging.getLogger(_PSYCOPG_LOGGER_NAME).setLevel(logging.DEBUG)
        # ``repositories.setup_schema`` opens a connection via
        # ``connection.connect`` and delegates to ``schema.ensure_schema``,
        # which wraps every ``CREATE TABLE`` / ``CREATE INDEX`` in a single
        # transaction so a partial schema never lands.
        repositories.setup_schema(self.config)
        if self.bulk_load_optimization:
            # Strip every secondary index + FK / CHECK constraint so the
            # per-row INSERT / COPY work the sink is about to do does not
            # pay maintenance / validation cost. The recreate happens in
            # :meth:`finalize`. Run *after* ``setup_schema`` so the
            # tables are guaranteed to exist before we try to alter them
            # on a fresh database.
            repositories.drop_indexes(self.config)

    @override
    def begin_run(self, order: Order) -> int:
        if order.id is None:
            if order.eleanor_version is None:
                order.eleanor_version = __version__
            persisted = repositories.insert_order(self.config, order)
            order.id = persisted.id
            return order.id

        existing = repositories.get_order(self.config, order.id)
        if existing is None:
            # Caller-chosen id with no matching row; insert it as new.
            if order.eleanor_version is None:
                order.eleanor_version = __version__
            persisted = repositories.insert_order(self.config, order)
            order.id = persisted.id
        elif order.eleanor_version is None:
            order.eleanor_version = existing.eleanor_version
        elif order.eleanor_version != existing.eleanor_version:
            raise EleanorException("cannot extend an order generated by a different version of Eleanor")

        return order.id

    @override
    def write_batch(
        self,
        order_id: int,
        results: Sequence[ComputeResult],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        """Persist a batch of compute results.

        One outer transaction over the whole batch (so all surviving rows
        commit with a single fsync); each VS point lives inside its own
        ``savepoint`` so a single bad row can roll back without poisoning
        the rest. Successful outcomes are upgraded to ``committed=True``
        only after the outer commit lands, and the progress bar is ticked
        once per durably-written row.
        """
        outcomes: list[WriteOutcome] = []
        # Slots in ``outcomes`` we tentatively credit to a successful
        # savepoint; promoted to ``committed=True`` after the outer commit.
        pending_slots: list[int] = []
        pending_results: list[int] = []

        conn = connection_module.connect(self.config)
        try:
            with conn.transaction():
                for index, result in enumerate(results):
                    point = result.point
                    # ``order_id`` mutation is a documented side effect of
                    # writing a batch.
                    point.order_id = order_id
                    try:
                        with conn.transaction(savepoint_name=f"vs_point_{index}"):
                            _ = repositories.insert_point(conn, order_id, point)
                        pending_slots.append(len(outcomes))
                        pending_results.append(point.exit_code)
                        outcomes.append(
                            WriteOutcome(
                                exit_code=-1,
                                committed=False,
                            )
                        )
                    except Exception as e:
                        # The savepoint already rolled this VS point's writes
                        # back; surface the error on stderr so silent
                        # per-point failures stop being invisible. The full
                        # traceback is preserved in addition to the message
                        # we stash on ``WriteOutcome.error_message`` because
                        # ``str(e)`` on a psycopg ``DatabaseError`` typically
                        # loses the originating call site.
                        message = (
                            f"PostgresSink.write_batch: VS point index {index} "
                            f"failed and was rolled back: {type(e).__name__}: {e}"
                        )
                        print(message, file=sys.stderr)
                        traceback.print_exc(file=sys.stderr)
                        outcomes.append(
                            WriteOutcome(
                                exit_code=-1,
                                committed=False,
                                error_message=str(e),
                            )
                        )
        except Exception as e:
            # The outer transaction failed at commit time; every pending
            # row is now non-durable. Surface the commit error on each.
            err = str(e)
            for slot in pending_slots:
                outcomes[slot] = WriteOutcome(
                    exit_code=-1,
                    committed=False,
                    error_message=err,
                )
            return outcomes

        # The outer commit landed. Promote the pending placeholders to
        # ``committed=True`` and tick the output bar -- once per durably
        # written row, matching the per-row cadence the docstring on
        # :meth:`OutputSink.write_batch` documents.
        for slot, exit_code in zip(pending_slots, pending_results):
            outcomes[slot] = WriteOutcome(
                exit_code=exit_code,
                committed=True,
            )
            if progress is not None:
                progress.tick()
        return outcomes

    @override
    def finalize_run(self) -> None:
        """Per-run cleanup. Currently a no-op; reserved for the bulk-load follow-up."""
        return None

    @override
    def finalize(self) -> None:
        """Close the persistent connection on sink shutdown.

        When ``bulk_load_optimization`` is enabled, reattach the
        constraints + indexes stripped in :meth:`initialize` *before*
        the connection is closed (recreate uses the same connection
        cache). The recreate runs inside a :keyword:`try` whose
        :keyword:`finally` always closes the connection, so a recreate
        failure (typically because the bulk-loaded data violates a
        constraint) leaves the database with constraints missing and
        propagates the exception, but never leaks the libpq socket.
        """
        try:
            if self.bulk_load_optimization:
                repositories.recreate_indexes(self.config)
        finally:
            connection_module.close_connection(self.config)

    @override
    def supports_worker_writes(self) -> bool:
        return True

    @override
    def supports_progress(self) -> bool:
        return True
