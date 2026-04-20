import json
import os.path
import tomllib
from dataclasses import dataclass
from typing import TypedDict, override

import yaml

from .exceptions import EleanorConfigurationException, EleanorException
from .typing import cast


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


class OutputRaw(TypedDict, total=False):
    """Schema for the ``output`` section of a raw config document."""
    type: str


class ConfigRaw(TypedDict, total=False):
    """Schema for a raw config document loaded from YAML/TOML/JSON."""
    database: DatabaseRaw
    output: OutputRaw


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


_VALID_OUTPUT_TYPES = {'postgres'}


@dataclass
class OutputConfig(object):
    type: str = 'postgres'

    def __post_init__(self):
        if self.type not in _VALID_OUTPUT_TYPES:
            valid = ', '.join(f'"{t}"' for t in sorted(_VALID_OUTPUT_TYPES))
            msg = f'the "{self.type}" output type is not supported; choose one of {valid}'
            raise EleanorConfigurationException(msg)

    @staticmethod
    def from_raw(raw: OutputRaw) -> "OutputConfig":
        return OutputConfig(type=raw.get('type', 'postgres'))


@dataclass(init=False)
class Config(object):
    database: DatabaseConfig
    output: OutputConfig
    raw: ConfigRaw

    def __init__(self, raw: ConfigRaw | None = None):
        if raw is None:
            raw = ConfigRaw(database=DatabaseRaw(), output=OutputRaw())
        object.__setattr__(self, 'raw', raw)
        raw_database = self.raw.get('database', DatabaseRaw())
        raw_output = self.raw.get('output', OutputRaw())
        object.__setattr__(self, 'database', DatabaseConfig.from_raw(raw_database))
        object.__setattr__(self, 'output', OutputConfig.from_raw(raw_output))

    @staticmethod
    def from_yaml(fname: str) -> "Config":
        with open(fname, 'rb') as handle:
            raw = cast(ConfigRaw, cast(object, yaml.safe_load(handle)))
            return Config(raw)

    @staticmethod
    def from_toml(fname: str) -> "Config":
        with open(fname, 'rb') as handle:
            raw = cast(ConfigRaw, cast(object, tomllib.load(handle)))
            return Config(raw)

    @staticmethod
    def from_json(fname: str) -> "Config":
        with open(fname, 'rb') as handle:
            raw = cast(ConfigRaw, cast(object, json.load(handle)))
            return Config(raw)

    @staticmethod
    def from_file(fname: str) -> "Config":
        try:
            _, ext = os.path.splitext(fname)
            match ext:
                case ".yaml":
                    return Config.from_yaml(fname)
                case ".yml":
                    return Config.from_yaml(fname)
                case ".toml":
                    return Config.from_toml(fname)
                case ".json":
                    return Config.from_json(fname)
                case _:
                    raise RuntimeError(f'unsupported file extension "{ext}"')
        except Exception as e:
            raise EleanorException(f'failed to parse "{fname}" as yaml, toml or json') from e


def load_config(config: str | Config | None) -> Config:
    if config is None:
        return Config()
    if isinstance(config, str):
        return Config.from_file(config)
    return config
