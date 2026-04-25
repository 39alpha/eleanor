"""Connection configuration for the Postgres output sink.

This module owns :class:`DatabaseConfig` (and the corresponding
:class:`DatabaseRaw` / :class:`PostgresArgsRaw` raw-mapping schemas) used by
the built-in postgres output sink. The on-disk raw block lives at
``output.args.database``; other sinks that need their own connection config
must define their own dataclass.

:class:`DatabaseConfig` is :func:`~dataclasses.dataclass` ``frozen=True``
so it is hashable, which lets the persistence layer key its per-process
connection cache on the config identity. Dialect validation is deliberately
*not* performed here: the postgres sink's
:class:`~eleanor.output.postgres.sink.PostgresSink` rejects non-postgresql
dialects in its constructor. The ``dialect`` / ``dbapi`` fields exist for
backward compatibility with on-disk configs that still spell them out; they
no longer drive the connection-string format because the rewritten sink
opens a psycopg3 connection directly.
"""

from dataclasses import dataclass
from typing import TypedDict

from ...typing import cast


class DatabaseRaw(TypedDict, total=False):
    """Schema for the ``output.args.database`` block of a raw config document.

    This block is purely about how to *connect* to the database. Sink-
    behaviour knobs (e.g. ``bulk_load_optimization``) live on the parent
    :class:`PostgresArgsRaw` block, not here.
    """

    dialect: str
    dbapi: str | None
    host: str | None
    port: int | None
    database: str | None
    username: str | None
    password: str | None
    sslmode: str | None


class PostgresArgsRaw(TypedDict, total=False):
    """Schema for the postgres sink's ``output.args`` block.

    ``database`` carries the connection settings (see :class:`DatabaseRaw`).
    ``bulk_load_optimization`` is a sink-behaviour knob that controls
    whether :class:`~eleanor.output.postgres.sink.PostgresSink` strips
    secondary constraints / indexes for the lifetime of the sink; see
    the field's documentation on
    :class:`~eleanor.output.postgres.sink.PostgresSink` for details.
    """

    database: DatabaseRaw
    bulk_load_optimization: bool


@dataclass(frozen=True)
class DatabaseConfig(object):
    """Frozen connection-config dataclass for the postgres output sink.

    Hashable; safe to use as a dict key in the per-process connection
    cache. ``dialect`` and ``dbapi`` are kept for raw-config compatibility
    only -- the rewritten sink ignores them and uses psycopg3 directly.
    """

    dialect: str = "postgresql"
    dbapi: str | None = "psycopg"
    host: str | None = "localhost"
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    sslmode: str | None = None

    @staticmethod
    def from_raw(raw: DatabaseRaw) -> "DatabaseConfig":
        return DatabaseConfig(
            dialect=raw.get("dialect", "postgresql"),
            dbapi=raw.get("dbapi", "psycopg"),
            host=raw.get("host", "localhost"),
            port=raw.get("port"),
            database=raw.get("database"),
            username=raw.get("username"),
            password=raw.get("password"),
            sslmode=raw.get("sslmode"),
        )


def database_config_from_config(config: object) -> DatabaseConfig:
    """Build a :class:`DatabaseConfig` from ``config.raw['output']['args']['database']``.

    Returns a default :class:`DatabaseConfig` when any segment of the path is
    missing or not a mapping. Callers that care about whether the database is
    actually set should inspect the returned dataclass (e.g.
    ``result.database is None``).
    """
    raw_attr = getattr(config, "raw", None)
    if not isinstance(raw_attr, dict):
        return DatabaseConfig()
    raw: dict[str, object] = cast(dict[str, object], cast(object, raw_attr))
    output_raw = raw.get("output")
    if not isinstance(output_raw, dict):
        return DatabaseConfig()
    output: dict[str, object] = cast(dict[str, object], cast(object, output_raw))
    args_raw = output.get("args")
    if not isinstance(args_raw, dict):
        return DatabaseConfig()
    args: dict[str, object] = cast(dict[str, object], cast(object, args_raw))
    database_raw = args.get("database")
    if not isinstance(database_raw, dict):
        return DatabaseConfig()
    return DatabaseConfig.from_raw(cast(DatabaseRaw, cast(object, database_raw)))
