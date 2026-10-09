from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from eleanor.cli.util import config_from_args, config_options, require_config
from eleanor.config import Config
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.settings import (
    PostgresDatabaseSettings,
    PostgresSinkSettings,
)
from pytest_mock import MockerFixture


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

    assert len(result.output) == 1
    assert isinstance(result.output[0].settings, PostgresSinkSettings)
    assert result.output[0].settings.database.database == "override_db"


def test_database_override_does_not_modify_other_properties(
    mocker: MockerFixture,
) -> None:
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

    assert len(result.output) == 1
    assert isinstance(result.output[0].settings, PostgresSinkSettings)
    assert result.output[0].settings.database == PostgresDatabaseSettings(
        database="new_db",
        username="alice",
        host="db.local",
    )


def test_database_override_raises_for_non_postgres_sinks(mocker: MockerFixture) -> None:
    non_postgres = Config.from_dict(
        {
            "output": {
                "kind": "null",
            },
        }
    )

    _ = mocker.patch("eleanor.cli.util.load_config", return_value=non_postgres)
    with pytest.raises(EleanorError, match="postgres"):
        _ = config_from_args("/fake.yaml", "db")


def test_database_required_when_not_configured(mocker: MockerFixture) -> None:
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


def test_database_requirement_can_be_disabled(mocker: MockerFixture) -> None:
    base = Config.from_dict(
        {
            "output": {"kind": "postgres"},
        }
    )
    _ = mocker.patch("eleanor.cli.util.load_config", return_value=base)
    result = config_from_args("/fake.yaml", None, require_database=False)

    assert result is base


def test_no_config_file_yields_empty_config() -> None:
    result = config_from_args(None, None)

    assert result.output == []


def test_no_config_file_assumes_local_postgres_for_database(mocker: MockerFixture) -> None:
    load_config = mocker.patch("eleanor.cli.util.load_config")

    result = config_from_args(None, "demo_db", assume_default_postgres=True)

    load_config.assert_not_called()
    assert len(result.output) == 1
    assert result.output[0].kind == "postgres"
    assert result.output[0].settings == PostgresSinkSettings(
        database=PostgresDatabaseSettings(host="localhost", database="demo_db"),
    )


def test_no_config_file_and_no_database_points_at_database_flag() -> None:
    with pytest.raises(click.ClickException, match="-d/--database"):
        _ = config_from_args(None, None, assume_default_postgres=True)


def test_assume_default_postgres_keeps_configured_postgres_sink(mocker: MockerFixture) -> None:
    base = Config.from_dict(
        {
            "output": {
                "kind": "postgres",
                "database": {"host": "db.remote", "username": "alice"},
            },
        }
    )
    _ = mocker.patch("eleanor.cli.util.load_config", return_value=base)

    result = config_from_args("/fake.yaml", "demo_db", assume_default_postgres=True)

    assert len(result.output) == 1
    assert isinstance(result.output[0].settings, PostgresSinkSettings)
    assert result.output[0].settings.database == PostgresDatabaseSettings(
        host="db.remote",
        username="alice",
        database="demo_db",
    )


def test_config_file_is_expanded_and_loaded(mocker: MockerFixture) -> None:
    load_config = mocker.patch("eleanor.cli.util.load_config", return_value=Config())

    _ = config_from_args("~/eleanor.yaml", None)

    load_config.assert_called_once_with(Path("~/eleanor.yaml").expanduser())


def test_require_config_returns_given_path() -> None:
    assert require_config(Path("/fake.yaml")) == Path("/fake.yaml")


def test_require_config_names_flag_and_default_location(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    with pytest.raises(click.ClickException) as excinfo:
        _ = require_config(None)

    assert "-c/--config" in excinfo.value.message
    assert str(tmp_path / "eleanor" / "config.yaml") in excinfo.value.message


def _probe(*, required: bool) -> click.Command:
    """Build a command exposing the values ``config_options`` resolves."""

    @click.command()
    @config_options(required=required)
    def probe(config: Path | None, database: str | None) -> None:
        click.echo(f"config={config!r}")
        click.echo(f"database={database!r}")

    return probe


@pytest.fixture
def xdg_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "xdg"
    home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return home


def _write_default_config(xdg_home: Path) -> Path:
    path = xdg_home / "eleanor" / "config.yaml"
    path.parent.mkdir()
    _ = path.write_text("output:\n  kind: postgres\n", encoding="utf-8")
    return path


def test_config_options_required_without_config_fails(xdg_home: Path) -> None:
    result = CliRunner().invoke(_probe(required=True), [])

    assert result.exit_code == 1
    assert "configuration is required" in result.output
    assert str(xdg_home / "eleanor" / "config.yaml") in result.output


def test_config_options_optional_without_config_passes_none(xdg_home: Path) -> None:
    _ = xdg_home
    result = CliRunner().invoke(_probe(required=False), [])

    assert result.exit_code == 0, result.output
    assert "config=None" in result.output
    assert "database=None" in result.output


@pytest.mark.parametrize("required", [True, False])
def test_config_options_explicit_config_is_a_path(xdg_home: Path, required: bool) -> None:
    _ = xdg_home
    result = CliRunner().invoke(_probe(required=required), ["-c", "/fake.yaml", "-d", "demo_db"])

    assert result.exit_code == 0, result.output
    assert f"config={Path('/fake.yaml')!r}" in result.output
    assert "database='demo_db'" in result.output


@pytest.mark.parametrize("required", [True, False])
def test_config_options_defaults_to_existing_xdg_config(xdg_home: Path, required: bool) -> None:
    default = _write_default_config(xdg_home)

    result = CliRunner().invoke(_probe(required=required), [])

    assert result.exit_code == 0, result.output
    assert f"config={default!r}" in result.output


def test_config_options_explicit_config_overrides_xdg_default(xdg_home: Path) -> None:
    _ = _write_default_config(xdg_home)

    result = CliRunner().invoke(_probe(required=True), ["-c", "/fake.yaml"])

    assert result.exit_code == 0, result.output
    assert f"config={Path('/fake.yaml')!r}" in result.output


def test_config_options_ignores_directory_at_default_location(xdg_home: Path) -> None:
    (xdg_home / "eleanor" / "config.yaml").mkdir(parents=True)

    result = CliRunner().invoke(_probe(required=False), [])

    assert result.exit_code == 0, result.output
    assert "config=None" in result.output


def test_config_options_reads_environment(xdg_home: Path) -> None:
    _ = xdg_home
    result = CliRunner().invoke(
        _probe(required=True),
        [],
        env={"ELEANOR_CONFIG": "/env.yaml", "ELEANOR_DATABASE": "env_db"},
    )

    assert result.exit_code == 0, result.output
    assert f"config={Path('/env.yaml')!r}" in result.output
    assert "database='env_db'" in result.output


@pytest.mark.parametrize("required", [True, False])
def test_config_options_help_does_not_mark_config_required(xdg_home: Path, required: bool) -> None:
    _ = xdg_home
    result = CliRunner().invoke(_probe(required=required), ["--help"])

    assert result.exit_code == 0, result.output
    assert "[required]" not in result.output


def test_config_options_help_shows_existing_default(xdg_home: Path) -> None:
    default = _write_default_config(xdg_home)

    result = CliRunner().invoke(_probe(required=True), ["--help"], terminal_width=500)

    assert result.exit_code == 0, result.output
    assert str(default) in result.output
