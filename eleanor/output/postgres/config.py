from dataclasses import dataclass
from typing import TypedDict

from eleanor.output.config import Config
from eleanor.typing import cast


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
    def from_dict(raw: DatabaseRaw) -> DatabaseConfig:
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


def database_config_from_config(config: Config) -> DatabaseConfig:
    """Build a :class:`DatabaseConfig` from ``config.args['database']``.

    Returns a default :class:`DatabaseConfig` when any segment of the path is
    missing or not a mapping. Callers that care about whether the database is
    actually set should inspect the returned dataclass (e.g.
    ``result.database is None``).
    """
    if not isinstance(cast(object, config), Config):
        return DatabaseConfig()

    raw = cast(DatabaseRaw, config.args.get("database", DatabaseRaw()))
    return DatabaseConfig.from_dict(raw)


__all__ = [
    "DatabaseRaw",
    "PostgresArgsRaw",
    "DatabaseConfig",
    "database_config_from_config",
]
