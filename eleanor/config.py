import json
import os.path
import tomllib
from dataclasses import dataclass, field
from typing import Self, TypedDict

import yaml

from eleanor.executor.config import Config as ExecutorConfig
from eleanor.executor.config import ConfigRaw as ExecutorRaw
from eleanor.output.config import Config as OutputConfig
from eleanor.output.config import ConfigRaw as OutputRaw

from .exceptions import EleanorConfigurationException, EleanorException
from .typing import cast


class ConfigRaw(TypedDict, total=False):
    """Schema for a raw config document loaded from YAML/TOML/JSON."""

    output: OutputRaw
    executor: ExecutorRaw


@dataclass(kw_only=True)
class Config(object):
    output: OutputConfig = field(default_factory=OutputConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)

    @classmethod
    def from_dict(cls, raw: ConfigRaw) -> Self:
        # Guard against the old top-level 'database:' key from configs written
        # before the schema moved database settings to output.args.database.
        # Silently ignoring the key would produce a confusing "no database
        # provided" error with no hint of what changed.
        if cast(dict[str, object], cast(object, raw)).get("database") is not None:
            raise EleanorConfigurationException(
                'the top-level "database:" config key is no longer supported; '
                + 'move your database settings under "output.args.database:" instead'
            )

        return cls(
            output=OutputConfig.from_raw(raw.get("output", OutputRaw())),
            executor=ExecutorConfig.from_raw(raw.get("executor", ExecutorRaw())),
        )

    @classmethod
    def from_yaml(cls, fname: str) -> Self:
        with open(fname, "rb") as handle:
            raw = cast(ConfigRaw, cast(object, yaml.safe_load(handle)))
            return cls.from_dict(raw)

    @classmethod
    def from_toml(cls, fname: str) -> Self:
        with open(fname, "rb") as handle:
            raw = cast(ConfigRaw, cast(object, tomllib.load(handle)))
            return cls.from_dict(raw)

    @classmethod
    def from_json(cls, fname: str) -> Self:
        with open(fname, "rb") as handle:
            raw = cast(ConfigRaw, cast(object, json.load(handle)))
            return cls.from_dict(raw)

    @classmethod
    def from_file(cls, fname: str) -> Self:
        try:
            _, ext = os.path.splitext(fname)
            match ext:
                case ".yaml":
                    return cls.from_yaml(fname)
                case ".yml":
                    return cls.from_yaml(fname)
                case ".toml":
                    return cls.from_toml(fname)
                case ".json":
                    return cls.from_json(fname)
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


__all__ = [
    "ConfigRaw",
    "Config",
]
