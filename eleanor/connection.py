"""Database connection configuration.

:class:`DatabaseConfig` is intentionally kept separate from
:mod:`eleanor.config` so that :mod:`eleanor.yeoman` and
:mod:`eleanor.output.postgres` can import it without pulling in the full
config module and its plugin-registry dependencies, which would create a
circular import.
"""
from dataclasses import dataclass
from typing import TypedDict, override

from .exceptions import EleanorConfigurationException


class DatabaseRaw(TypedDict, total=False):
    """Schema for the ``database`` section of a raw config document."""
    dialect: str
    dbapi: str | None
    host: str | None
    port: int | None
    database: str | None
    username: str | None
    password: str | None
    sslmode: str | None


@dataclass
class DatabaseConfig(object):
    dialect: str = 'postgresql'
    dbapi: str | None = 'psycopg'
    host: str | None = 'localhost'
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    sslmode: str | None = None

    def __post_init__(self):
        if self.dialect not in ['postgresql']:
            msg = f'the "{self.dialect}" database dialect is not supported; choose "postgresql"'
            raise EleanorConfigurationException(msg)

    @override
    def __str__(self) -> str:
        identity = self.username if self.username is not None else ''
        if self.password is not None and self.password != "":
            identity = identity + ':' + self.password
        port = f':{self.port}' if self.port is not None else ''
        return f'{self.dialect}+{self.dbapi}://{identity}@{self.host}{port}/{self.database}'

    @staticmethod
    def from_raw(raw: DatabaseRaw) -> "DatabaseConfig":
        return DatabaseConfig(
            dialect=raw.get('dialect', 'postgresql'),
            dbapi=raw.get('dbapi', 'psycopg'),
            host=raw.get('host', 'localhost'),
            port=raw.get('port'),
            database=raw.get('database'),
            username=raw.get('username'),
            password=raw.get('password'),
            sslmode=raw.get('sslmode'),
        )
