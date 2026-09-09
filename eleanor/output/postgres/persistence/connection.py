import atexit
import contextlib
import json
import os
import threading

import psycopg
from psycopg.types.json import set_json_dumps

from eleanor.output.postgres.settings import PostgresDatabaseSettings

_ConnectionKey = tuple[PostgresDatabaseSettings, int, int]

_connections: dict[_ConnectionKey, psycopg.Connection] = {}

_OwnerKey = tuple[PostgresDatabaseSettings, int]

_owners: dict[_OwnerKey, int] = {}


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
    key = (config, os.getpid(), threading.get_ident())
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
    """Close every memoized connection for ``config`` in this process.

    Unconditional: it ignores the :func:`acquire` reference count, so a sink
    sharing ``config`` with another loses its connection too. Sinks therefore
    go through :func:`release` instead; this is for callers that genuinely own
    ``config`` outright, such as tests tearing a database down. Safe to call
    when no connection is cached; safe to call when a cached connection has
    already been closed elsewhere.

    Deliberately spans threads: connections are keyed per thread, so a run
    that committed on a background writer thread has a connection this call
    must also reap. ``finalize`` runs on the main thread after the writer has
    been joined, so the writer's connection is idle by then and would
    otherwise leak for the lifetime of the process.
    """
    pid = os.getpid()
    stale = [key for key in _connections if key[0] == config and key[1] == pid]
    for key in stale:
        conn = _connections.pop(key, None)
        if conn is not None and not conn.closed:
            conn.close()


def acquire(config: PostgresDatabaseSettings) -> None:
    """Claim a reference to ``config``'s memoized connections for this process.

    The connection cache is keyed on the *database settings*, not on whoever
    asked for it, so two sinks pointed at one database share its connections.
    That sharing is fine -- the cache is already keyed per thread, so nothing
    interleaves transactions -- but it makes shutdown ambiguous: an unguarded
    :func:`close_connection` from the first sink to finish would close the
    socket the second one is still writing through.

    :func:`acquire` / :func:`release` resolve that by counting live claimants.
    Only the last :func:`release` actually closes anything. Callers that do not
    participate (``repositories`` helpers, the CLI, ``doctor``) are unaffected;
    they open connections through :func:`connect` as before and are reaped by
    the last :func:`release`, or failing that by :mod:`atexit`.
    """
    key = (config, os.getpid())
    _owners[key] = _owners.get(key, 0) + 1


def release(config: PostgresDatabaseSettings) -> None:
    """Drop a reference taken by :func:`acquire`; close at the last one.

    Releasing without a matching :func:`acquire` closes immediately, which is
    what a bare ``finalize`` on a never-initialized sink should do.
    """
    key = (config, os.getpid())
    remaining = _owners.get(key, 0) - 1
    if remaining > 0:
        _owners[key] = remaining
        return

    _ = _owners.pop(key, None)
    close_connection(config)


def _close_all_connections() -> None:
    """Close every memoized connection in this process. Used by :mod:`atexit`."""
    closed_connections: list[_ConnectionKey] = []

    for key, conn in _connections.items():
        if key[1] != os.getpid():
            continue

        if not conn.closed:
            with contextlib.suppress(Exception):
                conn.close()

        closed_connections.append(key)

    for key in closed_connections:
        del _connections[key]

    pid = os.getpid()
    for key in [owner for owner in _owners if owner[1] == pid]:
        del _owners[key]


_ = atexit.register(_close_all_connections)


__all__ = ["acquire", "close_connection", "connect", "release"]
