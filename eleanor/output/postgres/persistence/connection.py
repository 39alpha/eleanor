import atexit
import contextlib
import json
import os

import psycopg
from psycopg.types.json import set_json_dumps

from eleanor.output.postgres.settings import PostgresDatabaseSettings

# Process-local memoized connections, keyed on (config, pid).
# After fork(), child processes have a different pid, see no entry, and
# open a fresh connection.
_connections: dict[tuple[PostgresDatabaseSettings, int], psycopg.Connection] = {}


def _json_dumps(value: object) -> str:
    """JSON encoder used for every JSONB column the sink writes.

    Passes ``default=str`` so non-JSON-native leaves (e.g. ``create_date`` in
    ``orders`` from a TOML config) get stringified instead of raising.
    JSON-native scalars / containers pass through untouched.
    """
    return json.dumps(value, default=str)


def connect(config: PostgresDatabaseSettings) -> psycopg.Connection:
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
    # Register our ``default=str`` JSON encoder on this connection only,
    # so we never mutate psycopg's global adapters singleton.
    set_json_dumps(_json_dumps, conn)
    _connections[key] = conn
    return conn


def close_connection(config: PostgresDatabaseSettings) -> None:
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
    closed_connections: list[tuple[PostgresDatabaseSettings, int]] = []

    for key, conn in _connections.items():
        if key[1] != os.getpid():
            continue

        if not conn.closed:
            with contextlib.suppress(Exception):
                conn.close()

        closed_connections.append(key)

    for key in closed_connections:
        del _connections[key]


_ = atexit.register(_close_all_connections)


__all__ = ["close_connection", "connect"]
