import json
import tomllib
from dataclasses import asdict, dataclass

import yaml

from .exceptions import EleanorConfigurationException, EleanorException
from .typing import Any, Callable, Optional, cast


@dataclass
class DatabaseConfig(object):
    dialect: str = 'sqlite'
    dbapi: Optional[str] = None
    host: Optional[str] = 'localhost'
    port: Optional[int] = None
    database: Optional[str] = 'campaign.sql'
    username: Optional[str] = None
    password: Optional[str] = None
    use_actor: bool = False

    def __post_init__(self):
        if self.dialect not in ['sqlite', 'postgresql']:
            msg = f'the "{self.dialect}" database dialect is not supported; choose either "sqlite" or "postgresql"'
            raise EleanorConfigurationException(msg)

        if self.dialect != 'sqlite' and any(x is None for x in [self.dbapi, self.username, self.password]):
            msg = f'must provide a dbapi, username and password for {self.dialect} databases'
            raise EleanorConfigurationException(msg)

    def __str__(self) -> str:
        if self.dialect == 'sqlite':
            return f'sqlite:///{self.database}'
        else:
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
        parsers: dict[str, Callable[[str], Order]] = {  # type: ignore
            'yaml': Config.from_yaml,
            'toml': Config.from_toml,
            'json': Config.from_json
        }

        for filetype, func in parsers.items():
            try:
                return func(fname)
            except Exception:
                pass

        raise EleanorException(f'failed to parse "{fname}" as yaml, toml or json')


def load_config(config: Optional[str | Config]) -> Config:
    if config is None:
        config = Config()
    elif isinstance(config, str):
        config = Config.from_file(config)

    return cast(Config, config)
