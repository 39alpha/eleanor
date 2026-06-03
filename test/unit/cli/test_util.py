import click
import pytest
from pytest_mock import MockerFixture

from eleanor.cli.util import config_from_args
from eleanor.config import Config
from eleanor.exceptions import EleanorException
from eleanor.output.postgres.settings import PostgresDatabaseSettings, PostgresSinkSettings


def test_database_overrides_postgres_database(mocker: MockerFixture) -> None:
    base = Config.from_dict(
        {
            "output": {
                "kind": "postgres",
            },
        }
    )

    _ = mocker.patch("eleanor.cli.util.load_config", return_value=base)
    result = config_from_args("/fake.yaml", "override_db")

    assert result.output is not None
    assert isinstance(result.output.settings, PostgresSinkSettings)
    assert result.output.settings.database.database == "override_db"


def test_database_override_does_not_modify_other_properties(mocker: MockerFixture):
    base = Config.from_dict(
        {
            "output": {
                "kind": "postgres",
                "database": {"username": "alice", "host": "db.local"},
            },
        }
    )
    _ = mocker.patch("eleanor.cli.util.load_config", return_value=base)
    result = config_from_args("/fake.yaml", "new_db")

    assert result.output is not None
    assert isinstance(result.output.settings, PostgresSinkSettings)
    assert result.output.settings.database == PostgresDatabaseSettings(
        database="new_db",
        username="alice",
        host="db.local",
    )


def test_database_override_raises_for_non_postgres_sinks(mocker: MockerFixture):
    non_postgres = Config.from_dict(
        {
            "output": {
                "kind": "null",
            },
        }
    )

    _ = mocker.patch("eleanor.cli.util.load_config", return_value=non_postgres)
    with pytest.raises(EleanorException, match="postgres"):
        _ = config_from_args("/fake.yaml", "db")


def test_database_required_when_not_configured(mocker: MockerFixture):
    base = Config.from_dict(
        {
            "output": {
                "kind": "postgres",
            },
        },
    )
    _ = mocker.patch("eleanor.cli.util.load_config", return_value=base)
    with pytest.raises(click.ClickException):
        _ = config_from_args("/fake.yaml", None)


def test_database_requirement_can_be_disabled(mocker: MockerFixture):
    base = Config.from_dict(
        {
            "output": {"kind": "postgres"},
        }
    )
    _ = mocker.patch("eleanor.cli.util.load_config", return_value=base)
    result = config_from_args("/fake.yaml", None, require_database=False)

    assert result is base
