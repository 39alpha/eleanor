from pathlib import Path
from typing import Protocol

import pytest
from eleanor.config import Config
from eleanor.config.executor import ExecutorConfig
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorException
from eleanor.output.postgres.settings import (
    PostgresDatabaseSettings,
    PostgresSinkSettings,
)

FORMATS = ["yaml", "yml", "toml", "json"]


class Helpers(Protocol):
    @staticmethod
    def write_config(data: dict[str, object], tmp_path: Path, fmt: str) -> Path: ...


def test_default_config() -> None:
    config = Config()
    assert config == Config(output=None, executor=ExecutorConfig())


@pytest.mark.parametrize("fmt", FORMATS)
def test_config_from_file_format(
    helpers: type[Helpers], tmp_path: Path, fmt: str
) -> None:
    data: dict[str, object] = {
        "output": {
            "kind": "postgres",
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "sample",
                "username": "alice",
                "password": "secret",
                "sslmode": "require",
            },
        },
    }

    path = helpers.write_config(data, tmp_path, fmt)

    match fmt:
        case "yaml" | "yml":
            config = Config.from_yaml(str(path))
        case "toml":
            config = Config.from_toml(str(path))
        case "json":
            config = Config.from_json(str(path))
        case _:
            pytest.fail("unexpected config format")

    assert config.output == OutputSinkConfig(
        kind="postgres",
        settings=PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                host="localhost",
                port=5432,
                database="sample",
                username="alice",
                password="secret",
                sslmode="require",
            ),
            bulk_load_optimization=False,
        ),
    )


@pytest.mark.parametrize("fmt", FORMATS)
def test_config_from_string_format(
    helpers: type[Helpers], tmp_path: Path, fmt: str
) -> None:
    data: dict[str, object] = {
        "output": {
            "kind": "postgres",
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "sample",
                "username": "alice",
                "password": "secret",
                "sslmode": "require",
            },
        },
    }

    path = helpers.write_config(data, tmp_path, fmt)

    with open(path, "r") as f:
        content = f.read()

    match fmt:
        case "yaml" | "yml":
            config = Config.from_yamls(content)
        case "toml":
            config = Config.from_tomls(content)
        case "json":
            config = Config.from_jsons(content)
        case _:
            pytest.fail("unexpected config format")

    assert config.output == OutputSinkConfig(
        kind="postgres",
        settings=PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                host="localhost",
                port=5432,
                database="sample",
                username="alice",
                password="secret",
                sslmode="require",
            ),
            bulk_load_optimization=False,
        ),
    )


@pytest.mark.parametrize("fmt", FORMATS)
def test_config_from_file(helpers: type[Helpers], tmp_path: Path, fmt: str) -> None:
    data: dict[str, object] = {
        "output": {
            "kind": "postgres",
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "sample",
                "username": "alice",
                "password": "secret",
                "sslmode": "require",
            },
        },
    }

    path = helpers.write_config(data, tmp_path, fmt)

    config = Config.from_file(str(path))
    assert config.output == OutputSinkConfig(
        kind="postgres",
        settings=PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                host="localhost",
                port=5432,
                database="sample",
                username="alice",
                password="secret",
                sslmode="require",
            ),
            bulk_load_optimization=False,
        ),
    )


@pytest.mark.parametrize("fmt", FORMATS)
def test_config_from_string(helpers: type[Helpers], tmp_path: Path, fmt: str) -> None:
    data: dict[str, object] = {
        "output": {
            "kind": "postgres",
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "sample",
                "username": "alice",
                "password": "secret",
                "sslmode": "require",
            },
        },
    }

    path = helpers.write_config(data, tmp_path, fmt)

    with open(path, "r") as f:
        content = f.read()

    config = Config.from_str(content)
    assert config.output == OutputSinkConfig(
        kind="postgres",
        settings=PostgresSinkSettings(
            database=PostgresDatabaseSettings(
                host="localhost",
                port=5432,
                database="sample",
                username="alice",
                password="secret",
                sslmode="require",
            ),
            bulk_load_optimization=False,
        ),
    )


def test_config_from_string_rejects_bad_str() -> None:
    bad_content = "18sadf8hh1"
    with pytest.raises(EleanorException, match="failed to parse"):
        _ = Config.from_str(bad_content)


def test_config_from_file_rejects_bad_extension(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    with open(path, "w") as f:
        _ = f.write("[output]\n")

    with pytest.raises(EleanorException, match="failed to parse"):
        _ = Config.from_file(str(path))
