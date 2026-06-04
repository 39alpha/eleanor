import re
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from typing import Final, LiteralString, cast

import psycopg

import eleanor
from eleanor.exceptions import EleanorException
from eleanor.output.postgres.persistence import schema

_PKG: Final = files("eleanor.output.postgres.persistence").joinpath("migrations")
_FILENAME_RE: Final = re.compile(r"^(\d{4})_([a-z0-9_]+?)(\.notxn)?\.sql$")
_LOCK_NS: Final = "eleanor"
_LOCK_KEY: Final = "migrations"


@dataclass(frozen=True, slots=True)
class MigrationFile:
    version: int
    slug: str
    transactional: bool
    sql: str


def discover() -> tuple[MigrationFile, ...]:
    """Read every migration file out of the package, sorted by version.

    Raises on malformed filenames, duplicate versions, or non-contiguous
    numbering. Empty directory is a valid state (returns ()). These are
    developer / packaging faults, not operator input.
    """
    found: dict[int, MigrationFile] = {}
    for entry in sorted(p.name for p in _PKG.iterdir()):
        m = _FILENAME_RE.match(entry)
        if m is None:
            if entry.endswith(".sql"):
                raise EleanorException(f"malformed migration filename: {entry!r}")
            continue
        version = int(m.group(1))
        if version in found:
            raise EleanorException(f"duplicate migration version {version}")
        found[version] = MigrationFile(
            version=version,
            slug=m.group(2),
            transactional=m.group(3) is None,
            sql=_PKG.joinpath(entry).read_text(encoding="utf-8"),
        )
    ordered = tuple(found[v] for v in sorted(found))
    for i, mig in enumerate(ordered, start=1):
        if mig.version != i:
            raise EleanorException(f"non-contiguous migration numbering: expected {i}, found {mig.version}")
    return ordered


RECORD_SQL: LiteralString = (
    "INSERT INTO schema_migrations (version, name, applied_at, eleanor_version) VALUES (%s, %s, NOW(), %s)"
)

UNTRACKED_MSG: LiteralString = (
    "Database has existing eleanor tables but no migration tracking. "
    "If its schema already matches the current target, run "
    "`eleanor postgres migrate --stamp` to mark all migrations as "
    "applied without running them. Databases created from an older, "
    "incompatible schema cannot be upgraded in place and must be "
    "recreated from scratch."
)


def apply_pending_migrations(conn: psycopg.Connection) -> None:
    """Bring the database up to the latest declared migration.

    Acquires a session-scoped advisory lock so concurrent callers
    serialize. Bootstraps the tracking table. Refuses to auto-stamp a
    database that has data tables but no tracking. Applies every pending
    migration, each in its own transaction (transactional case) or in
    autocommit mode followed by a separate recording transaction
    (.notxn.sql case). Releases the lock unconditionally on exit.
    """
    migs = discover()
    with _advisory_lock(conn):
        applied = _bootstrap_and_read_applied(conn)
        for mig in migs:
            if mig.version in applied:
                continue
            _apply_one(conn, mig)


@contextmanager
def _advisory_lock(conn: psycopg.Connection) -> Generator[None]:
    """Hold pg_advisory_lock(int4, int4) for the duration of the body.

    Two-key form so the lock is namespaced under 'eleanor' rather than
    sharing the bigint keyspace with every other library that hashes a
    string. Session-level (not xact-level) because migrations span
    multiple successive transactions. Released in finally so a failure
    mid-loop still frees it.
    """
    with conn.transaction(), conn.cursor() as cur:
        _ = cur.execute(
            "SELECT pg_advisory_lock(hashtext(%s), hashtext(%s))",
            (_LOCK_NS, _LOCK_KEY),
        )
    try:
        yield
    finally:
        with conn.transaction(), conn.cursor() as cur:
            _ = cur.execute(
                "SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))",
                (_LOCK_NS, _LOCK_KEY),
            )


def _bootstrap_and_read_applied(conn: psycopg.Connection) -> set[int]:
    """Create the tracking table, read applied versions, refuse untracked DBs.

    The whole phase runs in one explicit transaction so the CREATE TABLE,
    the read, and the untracked-database check commit or roll back as a
    unit.
    """
    with conn.transaction(), conn.cursor() as cur:
        _ = cur.execute(cast(LiteralString, schema.to_create_table_sql(schema.SCHEMA_MIGRATIONS)))
        _ = cur.execute("SELECT version FROM schema_migrations")
        applied = {cast(int, row[0]) for row in cur.fetchall()}
        if not applied:
            _ = cur.execute("SELECT to_regclass('public.orders') IS NOT NULL")
            row = cur.fetchone()
            if row is not None and cast(bool, row[0]):
                raise EleanorException(UNTRACKED_MSG)
    return applied


def _apply_one(conn: psycopg.Connection, mig: MigrationFile) -> None:
    sql_text = cast(LiteralString, mig.sql)
    if mig.transactional:
        with conn.transaction(), conn.cursor() as cur:
            _ = cur.execute(sql_text)
            _ = cur.execute(RECORD_SQL, (mig.version, mig.slug, eleanor.__version__))
        return
    # Non-transactional: must run in autocommit (e.g. CREATE INDEX CONCURRENTLY).
    # The migration is REQUIRED to be idempotent — see MIGRATIONS.md.
    #
    # Diagnostic (not a guard): psycopg3 already raises if you set autocommit
    # inside an open transaction. This assert just turns that into a message
    # that names the precondition, in case the call ordering ever changes so
    # this runs with a dirty connection.
    assert not conn.info.transaction_status, "non-transactional migration requires a clean connection"
    prev = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            _ = cur.execute(sql_text)
    finally:
        conn.autocommit = prev
    with conn.transaction(), conn.cursor() as cur:
        _ = cur.execute(RECORD_SQL, (mig.version, mig.slug, eleanor.__version__))
