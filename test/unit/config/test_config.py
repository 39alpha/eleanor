from pathlib import Path
from typing import Protocol

import pytest
from eleanor.config import Config
from eleanor.config.executor import ExecutorConfig
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorError
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
    assert config == Config(output=[], executor=ExecutorConfig())


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

    assert config.output == [
        OutputSinkConfig(
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
    ]


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

    assert config.output == [
        OutputSinkConfig(
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
    ]


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
    assert config.output == [
        OutputSinkConfig(
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
    ]


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
    assert config.output == [
        OutputSinkConfig(
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
    ]


def test_config_from_string_rejects_bad_str() -> None:
    bad_content = "18sadf8hh1"
    with pytest.raises(EleanorError, match="failed to parse"):
        _ = Config.from_str(bad_content)


def test_config_from_file_rejects_bad_extension(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    with open(path, "w") as f:
        _ = f.write("[output]\n")

    with pytest.raises(EleanorError, match="failed to parse"):
        _ = Config.from_file(str(path))


def test_output_accepts_a_list_of_sinks() -> None:
    """Ensure several sinks can be declared, and keep their declared order."""
    config = Config.from_dict(
        {
            "output": [
                {"kind": "null"},
                {"kind": "memory"},
            ],
        }
    )

    assert [entry.kind for entry in config.output] == ["null", "memory"]


def test_output_name_defaults_to_kind() -> None:
    """Ensure the common case needs no explicit name."""
    config = Config.from_dict({"output": {"kind": "null"}})
    assert [entry.name for entry in config.output] == ["null"]


def test_output_name_is_honoured_and_kept_out_of_settings() -> None:
    """Ensure ``name`` addresses the sink without leaking into its settings.

    Settings parsing receives every key that is not Eleanor's own, so a
    forgotten exclusion would hand ``name`` to the plugin as a setting.
    """
    config = Config.from_dict(
        {"output": [{"kind": "null", "name": "discard", "verbose": True}]}
    )

    (entry,) = config.output
    assert entry.name == "discard"
    assert entry.kind == "null"
    assert entry.settings.verbose
    assert not hasattr(entry.settings, "name")


def test_two_sinks_of_one_kind_need_distinct_names() -> None:
    """Ensure the duplicate-name guard fires, since names address sinks."""
    with pytest.raises(EleanorError, match="duplicate output sink name"):
        _ = Config.from_dict({"output": [{"kind": "null"}, {"kind": "null"}]})


def test_two_sinks_of_one_kind_are_allowed_when_named() -> None:
    """Ensure the motivating case -- two CSVs, different files -- parses."""
    config = Config.from_dict(
        {
            "output": [
                {"kind": "null", "name": "first"},
                {"kind": "null", "name": "second"},
            ],
        }
    )

    assert [entry.name for entry in config.output] == ["first", "second"]


def test_empty_output_list_is_rejected() -> None:
    """Ensure an empty list is called out rather than read as "no sinks"."""
    with pytest.raises(EleanorError, match="omit the key entirely"):
        _ = Config.from_dict({"output": []})


def test_output_of_the_wrong_shape_is_rejected() -> None:
    """Ensure a scalar under ``output`` gets a pointed error."""
    with pytest.raises(EleanorError, match="must be a mapping or a list"):
        _ = Config.from_dict({"output": "postgres"})


def test_missing_output_means_no_sinks() -> None:
    """Ensure omitting the key stays legal; a sink may be supplied in code."""
    assert Config.from_dict({}).output == []
