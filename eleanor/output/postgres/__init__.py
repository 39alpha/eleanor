"""Public surface of the built-in postgres output sink.

:class:`PostgresSink` transitively pulls in psycopg and the
``persistence`` module graph (schema / converters / queries / connection),
so it is loaded on demand through :pep:`562`'s ``__getattr__`` hook with a
matching ``TYPE_CHECKING`` block so static type checkers see it as a
regular re-export. The connection-config symbols
(:class:`DatabaseConfig`, :class:`DatabaseRaw`, :class:`PostgresArgsRaw`, and
:func:`database_config_from_config`) live in the leaf
:mod:`eleanor.output.postgres.config` module and are re-exported here on
demand without forcing the psycopg load.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import DatabaseConfig as DatabaseConfig
    from .config import DatabaseRaw as DatabaseRaw
    from .config import PostgresArgsRaw as PostgresArgsRaw
    from .config import database_config_from_config as database_config_from_config
    from .sink import PostgresSink as PostgresSink


def __getattr__(name: str) -> object:
    if name == "PostgresSink":
        from .sink import PostgresSink

        return PostgresSink
    if name == "DatabaseConfig":
        from .config import DatabaseConfig

        return DatabaseConfig
    if name == "DatabaseRaw":
        from .config import DatabaseRaw

        return DatabaseRaw
    if name == "PostgresArgsRaw":
        from .config import PostgresArgsRaw

        return PostgresArgsRaw
    if name == "database_config_from_config":
        from .config import database_config_from_config

        return database_config_from_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DatabaseConfig",
    "DatabaseRaw",
    "PostgresArgsRaw",
    "PostgresSink",
    "database_config_from_config",
]
