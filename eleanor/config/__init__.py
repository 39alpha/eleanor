import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self, cast

import yaml

from eleanor.config.executor import ExecutorConfig
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorError
from eleanor.typing import StrPath
from eleanor.util import require_dict


def _reject_duplicate_names(entries: list[OutputSinkConfig]) -> None:
    """Reject two output sinks sharing a name."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for entry in entries:
        if entry.name in seen and entry.name not in duplicates:
            duplicates.append(entry.name)
        seen.add(entry.name)

    if duplicates:
        joined = ", ".join(repr(name) for name in duplicates)
        msg = f'duplicate output sink name(s): {joined}; give each sink a distinct "name"'
        raise EleanorError(msg)


def _parse_output(raw: object) -> list[OutputSinkConfig]:
    """Parse the ``output`` key, which may name one sink or several.

    A single mapping -- the only form that existed before runs could drive
    more than one sink -- is equivalent to a one-element list, so existing
    configurations parse unchanged::

        output:
          kind: postgres
          database: {...}

        output:
          - kind: postgres
            database: {...}
          - {kind: csv, name: export, filename: out.csv, query: {...}}
    """
    if raw is None:
        return []

    if isinstance(raw, dict):
        return [OutputSinkConfig.from_dict(cast(dict[str, object], raw))]

    if isinstance(raw, list):
        entries = [
            OutputSinkConfig.from_dict(cast(dict[str, object], require_dict(entry, f"output[{index}]")))
            for index, entry in enumerate(cast(list[object], raw))
        ]
        if not entries:
            msg = 'the "output" list is empty; omit the key entirely to configure no sink'
            raise EleanorError(msg)
        _reject_duplicate_names(entries)
        return entries

    msg = f"output must be a mapping or a list of mappings, got {type(raw).__name__}"
    raise EleanorError(msg)


@dataclass(kw_only=True)
class Config:
    """Machine-side configuration: where results go, and how work is spread."""

    output: list[OutputSinkConfig] = field(default_factory=list)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)

    def __post_init__(self) -> None:
        _reject_duplicate_names(self.output)

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        # Guard against the old top-level 'database:' key from configs written
        # before the schema moved database settings to output.args.database.
        # Silently ignoring the key would produce a confusing "no database
        # provided" error with no hint of what changed.
        if cast(dict[str, object], cast(object, raw)).get("database") is not None:
            msg = (
                'the top-level "database:" config key is no longer supported; '
                + 'move your database settings under "output.args.database:" instead'
            )
            raise EleanorError(msg)

        output_config = _parse_output(raw.get("output"))

        executor_raw = cast(dict[str, object], require_dict(raw.get("executor", {}), "executor"))
        executor_config = ExecutorConfig.from_dict(executor_raw)

        return cls(
            output=output_config,
            executor=executor_config,
        )

    @classmethod
    def from_yaml(cls, fname: StrPath) -> Self:
        with Path(fname).open("rb") as handle:
            raw = cast(dict[str, object], yaml.safe_load(handle))
            return cls.from_dict(raw)

    @classmethod
    def from_yamls(cls, content: str) -> Self:
        return cls.from_dict(cast(dict[str, object], yaml.safe_load(content)))

    @classmethod
    def from_toml(cls, fname: StrPath) -> Self:
        with Path(fname).open("rb") as handle:
            raw = cast(dict[str, object], tomllib.load(handle))
            return cls.from_dict(raw)

    @classmethod
    def from_tomls(cls, content: str) -> Self:
        return cls.from_dict(cast(dict[str, object], tomllib.loads(content)))

    @classmethod
    def from_json(cls, fname: StrPath) -> Self:
        with Path(fname).open("rb") as handle:
            raw = cast(dict[str, object], json.load(handle))
            return cls.from_dict(raw)

    @classmethod
    def from_jsons(cls, content: str) -> Self:
        return cls.from_dict(cast(dict[str, object], json.loads(content)))

    @classmethod
    def from_str(cls, content: str) -> Self:
        exceptions: list[Exception] = []
        for parser in [cls.from_yamls, cls.from_tomls, cls.from_jsons]:
            try:
                return parser(content)
            except Exception as e:
                exceptions.append(e)

        eg = ExceptionGroup("failed to parse", exceptions)
        msg = "failed to parse string as yaml, toml or json"
        raise EleanorError(msg) from eg

    @classmethod
    def from_file(cls, fname: StrPath) -> Self:
        try:
            fname = Path(fname)
            match fname.suffix:
                case ".yaml" | ".yml":
                    return cls.from_yaml(fname)
                case ".toml":
                    return cls.from_toml(fname)
                case ".json":
                    return cls.from_json(fname)
                case _:
                    msg = f"unsupported file extension {fname.suffix!r}"
                    raise RuntimeError(msg)
        except Exception as e:
            msg = f"failed to parse {str(fname)!r} as yaml, toml or json"
            raise EleanorError(msg) from e


def load_config(config: StrPath | Config | None) -> Config:
    if config is None:
        return Config()
    if isinstance(config, (str, Path)):
        return Config.from_file(config)
    return config


__all__ = ["Config"]
