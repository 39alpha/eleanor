import json
import os.path
import tomllib
from dataclasses import dataclass, field
from typing import Self, TypedDict

import yaml

from .exceptions import EleanorConfigurationException, EleanorException
from .typing import cast


class OutputRaw(TypedDict, total=False):
    """Schema for the ``output`` section of a raw config document."""

    kind: str
    args: dict[str, object]


class ParallelRaw(TypedDict, total=False):
    """Schema for the ``parallel`` section of a raw config document."""

    backend: str
    chunks_per_worker: int


class ConfigRaw(TypedDict, total=False):
    """Schema for a raw config document loaded from YAML/TOML/JSON."""

    output: OutputRaw
    parallel: ParallelRaw


@dataclass
class OutputConfig(object):
    kind: str | None = None
    args: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: OutputRaw) -> Self:
        output_args_raw: object = raw.get("args", {})
        if not isinstance(output_args_raw, dict):
            raise EleanorConfigurationException("output.args must be a dict")
        output_args_items = cast(dict[object, object], output_args_raw).items()
        output_args: dict[str, object] = {str(k): v for k, v in output_args_items}
        return cls(kind=raw.get("kind"), args=output_args)


@dataclass
class ParallelConfig(object):
    backend: str = "multiprocessing"
    chunks_per_worker: int = 10

    def __post_init__(self):
        if self.chunks_per_worker <= 0:
            msg = f'the chunks_per_worker value "{self.chunks_per_worker}" is invalid; choose a value >= 1'
            raise EleanorConfigurationException(msg)

    @staticmethod
    def from_raw(raw: ParallelRaw) -> "ParallelConfig":
        return ParallelConfig(
            backend=raw.get("backend", "multiprocessing"),
            chunks_per_worker=raw.get("chunks_per_worker", 10),
        )


@dataclass(init=False)
class Config(object):
    output: OutputConfig
    parallel: ParallelConfig
    raw: ConfigRaw

    def __init__(self, raw: ConfigRaw | None = None):
        if raw is None:
            raw = ConfigRaw(output=OutputRaw(), parallel=ParallelRaw())
        # Guard against the old top-level 'database:' key from configs written
        # before the schema moved database settings to output.args.database.
        # Silently ignoring the key would produce a confusing "no database
        # provided" error with no hint of what changed.
        if cast(dict[str, object], cast(object, raw)).get("database") is not None:
            raise EleanorConfigurationException(
                'the top-level "database:" config key is no longer supported; '
                + 'move your database settings under "output.args.database:" instead'
            )
        object.__setattr__(self, "raw", raw)
        raw_output = self.raw.get("output", OutputRaw())
        raw_parallel = self.raw.get("parallel", ParallelRaw())
        object.__setattr__(self, "output", OutputConfig.from_raw(raw_output))
        object.__setattr__(self, "parallel", ParallelConfig.from_raw(raw_parallel))

    @staticmethod
    def from_yaml(fname: str) -> "Config":
        with open(fname, "rb") as handle:
            raw = cast(ConfigRaw, cast(object, yaml.safe_load(handle)))
            return Config(raw)

    @staticmethod
    def from_toml(fname: str) -> "Config":
        with open(fname, "rb") as handle:
            raw = cast(ConfigRaw, cast(object, tomllib.load(handle)))
            return Config(raw)

    @staticmethod
    def from_json(fname: str) -> "Config":
        with open(fname, "rb") as handle:
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
