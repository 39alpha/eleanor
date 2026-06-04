"""Smoke tests for the ``eleanor postgres migrate`` CLI command."""

import psycopg
from click.testing import CliRunner
from pytest_mock import MockerFixture

from eleanor.cli import main
from eleanor.config import Config
from eleanor.output.postgres import cli as pg_cli
from eleanor.output.postgres.persistence.migrations import MigrationFile
from eleanor.output.postgres.settings import PostgresSinkSettings


def _postgres_config(database: str = "demo") -> Config:
    return Config.from_dict(
        {
            "output": {
                "kind": "postgres",
                "database": {"database": database},
            },
        }
    )


def _fake_migrations() -> tuple[MigrationFile, ...]:
    return (
        MigrationFile(version=1, slug="initial_schema", transactional=True, sql="SELECT 1;"),
        MigrationFile(version=2, slug="add_thing", transactional=True, sql="SELECT 2;"),
    )


def test_postgres_migrate_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "migrate", "--help"])
    assert result.exit_code == 0
    for flag in ("--dry-run", "--list", "--stamp", "--verify", "--yes"):
        assert flag in result.output


def test_postgres_migrate_rejects_verify_plus_stamp(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch(
        "eleanor.output.postgres.cli.config_from_args",
        return_value=_postgres_config(),
    )
    result = runner.invoke(main, ["postgres", "migrate", "--verify", "--stamp", "-c", "x.yaml"])
    assert result.exit_code != 0
    combined = (result.output or "") + (str(result.exception) if result.exception else "")
    assert "exclusive" in combined.lower() or "usage" in combined.lower()


def test_postgres_migrate_rejects_dryrun_plus_list(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch(
        "eleanor.output.postgres.cli.config_from_args",
        return_value=_postgres_config(),
    )
    result = runner.invoke(main, ["postgres", "migrate", "--dry-run", "--list", "-c", "x.yaml"])
    assert result.exit_code != 0


def test_postgres_migrate_dispatches_to_apply(runner: CliRunner, mocker: MockerFixture) -> None:
    apply = mocker.patch(
        "eleanor.output.postgres.cli.repositories.apply_pending_migrations",
    )
    mocker.patch(
        "eleanor.output.postgres.cli.config_from_args",
        return_value=_postgres_config("demo"),
    )
    result = runner.invoke(main, ["postgres", "migrate", "-c", "x.yaml", "-d", "demo"])
    assert result.exit_code == 0
    apply.assert_called_once()


def test_postgres_migrate_verify_clean(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._connection.connect", return_value=mocker.MagicMock())
    mocker.patch("eleanor.output.postgres.cli._schema.verify_against_tables", return_value=[])
    result = runner.invoke(main, ["postgres", "migrate", "--verify", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "in sync" in result.output


def test_postgres_migrate_verify_reports_drift(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._connection.connect", return_value=mocker.MagicMock())
    mocker.patch(
        "eleanor.output.postgres.cli._schema.verify_against_tables",
        return_value=["index 'orders_name_idx' on 'orders' is missing or invalid"],
    )
    result = runner.invoke(main, ["postgres", "migrate", "--verify", "-c", "x.yaml"])
    assert result.exit_code != 0
    assert "orders_name_idx" in result.output


def test_postgres_migrate_list_shows_applied_and_pending(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._migrations.discover", return_value=_fake_migrations())
    mocker.patch("eleanor.output.postgres.cli._read_applied_versions", return_value={1})
    result = runner.invoke(main, ["postgres", "migrate", "--list", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "initial_schema" in result.output
    assert "applied" in result.output
    assert "pending" in result.output


def test_postgres_migrate_dry_run_lists_only_pending(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._migrations.discover", return_value=_fake_migrations())
    mocker.patch("eleanor.output.postgres.cli._read_applied_versions", return_value={1})
    result = runner.invoke(main, ["postgres", "migrate", "--dry-run", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "add_thing" in result.output
    assert "initial_schema" not in result.output


def test_postgres_migrate_dry_run_none_pending(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._migrations.discover", return_value=_fake_migrations())
    mocker.patch("eleanor.output.postgres.cli._read_applied_versions", return_value={1, 2})
    result = runner.invoke(main, ["postgres", "migrate", "--dry-run", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "no pending migrations" in result.output


def test_postgres_migrate_stamp_inserts_all(runner: CliRunner, mocker: MockerFixture) -> None:
    conn = mocker.MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._connection.connect", return_value=conn)
    mocker.patch("eleanor.output.postgres.cli._schema.verify_against_tables", return_value=[])
    mocker.patch("eleanor.output.postgres.cli._migrations.discover", return_value=_fake_migrations())
    result = runner.invoke(main, ["postgres", "migrate", "--stamp", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "Stamped 2 migration(s)." in result.output
    # one CREATE TABLE + one INSERT per declared migration.
    assert cur.execute.call_count == 1 + len(_fake_migrations())


def test_postgres_migrate_stamp_through_version(runner: CliRunner, mocker: MockerFixture) -> None:
    conn = mocker.MagicMock()
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._connection.connect", return_value=conn)
    mocker.patch("eleanor.output.postgres.cli._schema.verify_against_tables", return_value=[])
    mocker.patch("eleanor.output.postgres.cli._migrations.discover", return_value=_fake_migrations())
    result = runner.invoke(main, ["postgres", "migrate", "--stamp", "1", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "Stamped 1 migration(s)." in result.output


def test_postgres_migrate_stamp_refuses_drift_without_yes(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._connection.connect", return_value=mocker.MagicMock())
    mocker.patch(
        "eleanor.output.postgres.cli._schema.verify_against_tables",
        return_value=["constraint 'foo' on 'orders' is missing"],
    )
    discover = mocker.patch("eleanor.output.postgres.cli._migrations.discover", return_value=_fake_migrations())
    result = runner.invoke(main, ["postgres", "migrate", "--stamp", "-c", "x.yaml"])
    assert result.exit_code != 0
    assert "drift" in result.output.lower()
    discover.assert_not_called()


def test_postgres_migrate_stamp_drift_overridden_by_yes(runner: CliRunner, mocker: MockerFixture) -> None:
    conn = mocker.MagicMock()
    mocker.patch("eleanor.output.postgres.cli.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.cli._connection.connect", return_value=conn)
    mocker.patch(
        "eleanor.output.postgres.cli._schema.verify_against_tables",
        return_value=["constraint 'foo' on 'orders' is missing"],
    )
    mocker.patch("eleanor.output.postgres.cli._migrations.discover", return_value=_fake_migrations())
    result = runner.invoke(main, ["postgres", "migrate", "--stamp", "--yes", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "Stamped" in result.output


def test_read_applied_versions_returns_empty_on_undefined_table(mocker: MockerFixture) -> None:
    conn = mocker.MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.execute.side_effect = psycopg.errors.UndefinedTable("relation does not exist")
    mocker.patch("eleanor.output.postgres.cli._connection.connect", return_value=conn)
    settings = _postgres_config().output
    assert settings is not None
    pg_settings = settings.settings
    assert isinstance(pg_settings, PostgresSinkSettings)
    result = pg_cli._read_applied_versions(pg_settings)
    assert result == set()
