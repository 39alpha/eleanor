from typing import Protocol

import pytest
from click import Path
from eleanor.config import Config, load_config
from eleanor.config.executor import ExecutorConfig
from eleanor.config.output import OutputSinkConfig
from eleanor.executor.settings import ExecutorSettings
from eleanor.output.postgres.settings import (
    PostgresDatabaseSettings,
    PostgresSinkSettings,
)

FORMATS = ["yaml", "yml", "toml", "json"]


class Helpers(Protocol):
    @staticmethod
    def write_config(data: dict[str, object], path: Path, fmt: str) -> Path: ...


def test_load_config_with_none_argument() -> None:
    config = load_config(None)
    assert config == Config(
        output=None,
        executor=ExecutorConfig(
            kind="multiprocessing",
            settings=ExecutorSettings(chunks_per_worker=10, num_workers=None),
        ),
    )


@pytest.mark.parametrize("fmt", FORMATS)
def test_load_config_with_path(
    helpers: type[Helpers], tmp_path: Path, fmt: str
) -> None:
    data: dict[str, object] = {
        "output": {
            "kind": "postgres",
            "database": {
                "host": "localhost",
                "database": "sample",
                "username": "alice",
                "password": "secret",
            },
        },
    }

    path = helpers.write_config(data, tmp_path, fmt)

    config = load_config(str(path))
    assert config == Config(
        output=OutputSinkConfig(
            kind="postgres",
            settings=PostgresSinkSettings(
                database=PostgresDatabaseSettings(
                    host="localhost",
                    database="sample",
                    username="alice",
                    password="secret",
                ),
                bulk_load_optimization=False,
            ),
        )
    )


def test_load_config_with_config() -> None:
    config = Config(executor=ExecutorConfig(kind="serial"))
    same = load_config(config)
    assert same is config
