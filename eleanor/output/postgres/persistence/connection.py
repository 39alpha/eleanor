"""psycopg3 connection helper for the postgres output sink.

The persistence layer stays connectionless: every public function in
``repositories.py`` either takes an open :class:`psycopg.Connection` or
acquires one via :func:`connect` and returns. :func:`connect` memoizes one
connection per ``(DatabaseConfig, pid)`` key for the lifetime of the
process, so repeated calls inside one worker share a single TCP/TLS
session instead of opening and tearing one down per call.

Lifecycle
---------
* The connection is opened lazily on the first :func:`connect` call.
* It is closed by :func:`close_connection` (which the postgres sink calls
  from its :meth:`OutputSink.finalize` hook) -- the explicit, normal
  shutdown path.
* :func:`_close_all_connections` is registered with :mod:`atexit` as a
  belt-and-suspenders safety net for crashes / hard exits where the sink's
  :meth:`finalize` does not run.

Process safety
--------------
Connections are keyed on ``(config, os.getpid())``. Under the
multiprocessing executor a worker forks from the parent and therefore
inherits the parent's cache dict; the child's :func:`os.getpid` returns
a fresh value, so the inherited entries are invisible to it and a fresh
connection is opened on first use. This matches the standard "do not
share libpq connections across :func:`os.fork`" guidance.
"""

import atexit
import json
import os

import psycopg
from psycopg.types.json import set_json_dumps

from ..config import DatabaseConfig

# Process-local memoized connections, keyed on (config, pid).
# After fork(), child processes have a different pid, see no entry, and
# open a fresh connection.
_connections: dict[tuple[DatabaseConfig, int], psycopg.Connection] = {}


def _json_dumps(value: object) -> str:
    """JSON encoder used for every JSONB column the sink writes.

    Passes ``default=str`` so non-JSON-native leaves (e.g. ``datetime``
    in ``orders.raw`` from a TOML config) get stringified instead of
    raising. JSON-native scalars / containers pass through untouched.
    """
    return json.dumps(value, default=str)


def connect(config: DatabaseConfig) -> psycopg.Connection:
    """Return a process-local memoized :class:`psycopg.Connection` for ``config``.

    Opens lazily on first call, reuses on subsequent calls within the same
    process. If the cached connection has been closed under us (server
    restart, network blip), it is replaced transparently. The caller is
    responsible for the transactional shape of any work done against the
    returned connection -- typically by entering
    :meth:`psycopg.Connection.transaction` (with an optional
    ``savepoint_name=`` for nested per-VS-point isolation).
    """
    key = (config, os.getpid())
    cached = _connections.get(key)
    if cached is not None and not cached.closed:
        return cached
    if cached is not None:
        # Cached connection is dead; fall through to reopen.
        del _connections[key]
    # Pass each field as its own kwarg so psycopg's typed signature is
    # respected. Fields that are ``None`` are omitted so libpq falls back
    # to its own defaults / the local environment (e.g. ``PGHOST``).
    conn = psycopg.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.username,
        password=config.password,
        sslmode=config.sslmode,
    )
    _connections[key] = conn
    return conn


def close_connection(config: DatabaseConfig) -> None:
    """Close the memoized connection for ``config`` in this process.

    Called from :meth:`PostgresSink.finalize` as part of the normal sink
    shutdown sequence. Safe to call when no connection is cached; safe to
    call when the cached connection has already been closed elsewhere.
    """
    key = (config, os.getpid())
    conn = _connections.pop(key, None)
    if conn is not None and not conn.closed:
        conn.close()


def _close_all_connections() -> None:
    """Close every memoized connection in this process. Used by :mod:`atexit`."""
    while _connections:
        _, conn = _connections.popitem()
        if not conn.closed:
            try:
                conn.close()
            except Exception:
                # Best-effort cleanup; never raise from atexit.
                pass


# Configure psycopg3's JSON encoder at import time. Installs our
# ``default=str`` dumper so any JSONB column accepts ``datetime`` / other
# non-JSON-native leaves (e.g. ``orders.raw`` from a TOML config). The
# adapter registration is global to psycopg's adapters singleton, which is
# fine: this process is a postgres-sink process top to bottom.
#
# Dict-typed values are wrapped explicitly with :class:`psycopg.types.json.Jsonb`
# at the bind site in ``repositories.py`` rather than registering a global
# ``dict -> Jsonb`` dumper, which keeps the boundary visible at the call site.
set_json_dumps(_json_dumps)

_ = atexit.register(_close_all_connections)
