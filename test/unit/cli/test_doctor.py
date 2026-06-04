from click.testing import CliRunner
from pytest_mock import MockerFixture

from eleanor.cli import main
from eleanor.config import Config
from eleanor.output.postgres.persistence.migrations import MigrationFile


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


def _conn_with_fetchone(mocker: MockerFixture, rows: list[tuple[object, ...]]) -> object:
    conn = mocker.MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = rows
    return conn


def test_doctor_lists_postgres_cli_plugin(runner: CliRunner) -> None:
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "CLI commands" in result.output
    assert "postgres" in result.output


def test_doctor_no_config_skips_postgres_section(runner: CliRunner) -> None:
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "connection failed" not in result.output


def test_doctor_reports_connection_failure(runner: CliRunner, mocker: MockerFixture) -> None:
    mocker.patch("eleanor.cli.doctor.config_from_args", return_value=_postgres_config())
    mocker.patch(
        "eleanor.output.postgres.persistence.connection.connect",
        side_effect=RuntimeError("boom"),
    )
    result = runner.invoke(main, ["doctor", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "connection failed" in result.output
    assert "boom" in result.output


def test_doctor_tracking_table_missing_untracked(runner: CliRunner, mocker: MockerFixture) -> None:
    conn = _conn_with_fetchone(mocker, [(False,), (True,)])
    mocker.patch("eleanor.cli.doctor.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.persistence.connection.connect", return_value=conn)
    result = runner.invoke(main, ["doctor", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "tracking table missing" in result.output
    assert "--stamp" in result.output


def test_doctor_reports_up_to_date(runner: CliRunner, mocker: MockerFixture) -> None:
    conn = _conn_with_fetchone(mocker, [(True,), (2,)])
    mocker.patch("eleanor.cli.doctor.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.persistence.connection.connect", return_value=conn)
    mocker.patch("eleanor.output.postgres.persistence.migrations.discover", return_value=_fake_migrations())
    mocker.patch("eleanor.output.postgres.persistence.schema.verify_against_tables", return_value=[])
    result = runner.invoke(main, ["doctor", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "up to date" in result.output
    assert "schema matches TABLES" in result.output


def test_doctor_reports_pending_migrations(runner: CliRunner, mocker: MockerFixture) -> None:
    conn = _conn_with_fetchone(mocker, [(True,), (1,)])
    mocker.patch("eleanor.cli.doctor.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.persistence.connection.connect", return_value=conn)
    mocker.patch("eleanor.output.postgres.persistence.migrations.discover", return_value=_fake_migrations())
    mocker.patch("eleanor.output.postgres.persistence.schema.verify_against_tables", return_value=[])
    result = runner.invoke(main, ["doctor", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "pending" in result.output


def test_doctor_reports_drift(runner: CliRunner, mocker: MockerFixture) -> None:
    conn = _conn_with_fetchone(mocker, [(True,), (2,)])
    mocker.patch("eleanor.cli.doctor.config_from_args", return_value=_postgres_config())
    mocker.patch("eleanor.output.postgres.persistence.connection.connect", return_value=conn)
    mocker.patch("eleanor.output.postgres.persistence.migrations.discover", return_value=_fake_migrations())
    mocker.patch(
        "eleanor.output.postgres.persistence.schema.verify_against_tables",
        return_value=["index 'orders_name_idx' on 'orders' is missing or invalid"],
    )
    result = runner.invoke(main, ["doctor", "-c", "x.yaml"])
    assert result.exit_code == 0
    assert "drift" in result.output
    assert "orders_name_idx" in result.output
