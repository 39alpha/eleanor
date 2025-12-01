import json
import os.path
import tomllib
from dataclasses import asdict, dataclass

import yaml
from xdg_base_dirs import xdg_config_home

from .exceptions import EleanorConfigurationException, EleanorException
from .typing import Any, Callable, Optional, cast


@dataclass
class DatabaseConfig(object):
    dialect: str = 'postgresql'
    dbapi: Optional[str] = 'psycopg'
    host: Optional[str] = 'localhost'
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    def __post_init__(self):
        if self.dialect not in ['postgresql']:
            msg = f'the "{self.dialect}" database dialect is not supported; choose "postgresql"'
            raise EleanorConfigurationException(msg)

        if any(x is None for x in [self.dbapi, self.username, self.password]):
            msg = f'must provide a dbapi, username and password for {self.dialect} databases'
            raise EleanorConfigurationException(msg)

    def __str__(self) -> str:
        port = f':{self.port}' if self.port is not None else ''
        return f'{self.dialect}+{self.dbapi}://{self.username}:{self.password}@{self.host}{port}/{self.database}'


@dataclass(init=False)
class Config(object):
    database: DatabaseConfig
    raw: dict[str, Any]

    def __init__(self, raw: Optional[dict[str, Any]] = None):
        if raw is None:
            raw = {'database': asdict(DatabaseConfig())}
        object.__setattr__(self, 'raw', raw)
        object.__setattr__(self, 'database', DatabaseConfig(**self.raw.get('database', {})))

    @staticmethod
    def from_yaml(fname: str):
        with open(fname, 'rb') as handle:
            raw = yaml.safe_load(handle)
            return Config(raw)

    @staticmethod
    def from_toml(fname: str):
        with open(fname, 'rb') as handle:
            raw = tomllib.load(handle)
            return Config(raw)

    @staticmethod
    def from_json(fname: str):
        with open(fname, 'rb') as handle:
            raw = json.load(handle)
            return Config(raw)

    @staticmethod
    def from_file(fname: str):
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


def load_config(config: Optional[str | Config]) -> Config:
    if config is None:
        config = Config()
    elif isinstance(config, str):
        config = Config.from_file(config)

    return cast(Config, config)
