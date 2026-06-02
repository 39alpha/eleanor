import json
import os.path
import tomllib
from dataclasses import dataclass, field
from typing import Self, TypedDict, cast

import yaml

from eleanor.config.executor import ExecutorConfig
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorConfigurationException, EleanorException


class ConfigRaw(TypedDict, total=False):
    output: dict[str, object]
    executor: dict[str, object]


@dataclass(kw_only=True)
class Config(object):
    output: OutputSinkConfig | None = None
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

        output_raw = raw.get("output")
        output_config = OutputSinkConfig.from_dict(output_raw) if output_raw is not None else None

        return cls(
            output=output_config,
            executor=ExecutorConfig.from_dict(raw.get("executor", {})),
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
