"""End-to-end config resolution for the ``eleanor postgres`` subcommands.

Every database-facing subcommand must work against a local server given only
``-d/--database``, with no configuration file. Only the database-touching
helper is mocked, so the real ``config_options`` / ``config_from_args`` path is
exercised.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner, Result
from pytest_mock import MockerFixture

from eleanor.cli import main
from eleanor.output.postgres.settings import PostgresDatabaseSettings

ID = str(uuid.UUID("018f3a1c-0000-7000-8000-000000000000"))


@dataclass(frozen=True)
class Subcommand:
    args: tuple[str, ...]
    target: str
    succeeds: bool

    @property
    def id(self) -> str:
        return " ".join(arg for arg in self.args if arg != ID)


SUBCOMMANDS = [
    Subcommand(("bulkload", "drop", "-y"), "eleanor.output.postgres.cli.bulkload.drop_bulk_load_objects", True),
    Subcommand(("bulkload", "recreate"), "eleanor.output.postgres.cli.bulkload.recreate_bulk_load_objects", True),
    Subcommand(("migrate",), "eleanor.output.postgres.persistence.repositories.apply_pending_migrations", True),
    Subcommand(("dump", "order", ID), "eleanor.output.postgres.cli.dump.order.get_order", False),
    Subcommand(("dump", "vs", ID), "eleanor.output.postgres.cli.dump.variable_space.get_vs_as_order", False),
    Subcommand(("dump", "scratch", ID), "eleanor.output.postgres.cli.dump.scratch.load_scratch_entry", False),
    Subcommand(("export", "duckdb"), "eleanor.output.postgres.cli.export.duckdb.export_duckdb", True),
]


@pytest.fixture(params=SUBCOMMANDS, ids=[sub.id for sub in SUBCOMMANDS])
def subcommand(request: pytest.FixtureRequest) -> Subcommand:
    return cast(Subcommand, request.param)


def invoke(
    runner: CliRunner,
    subcommand: Subcommand,
    tmp_path: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> Result:
    extra = ("-o", str(tmp_path / "out.db")) if subcommand.args[0] == "export" else ()
    return runner.invoke(main, ["postgres", *subcommand.args, *extra, *args], env=env)


def stub(mocker: MockerFixture, subcommand: Subcommand) -> MagicMock:
    """Patch the subcommand's database helper; lookups report nothing found."""
    return mocker.patch(subcommand.target, return_value=None)


def assert_dispatched(result: Result, subcommand: Subcommand, helper: MagicMock) -> PostgresDatabaseSettings:
    """Assert the helper ran once and return the database settings it was handed."""
    if subcommand.succeeds:
        assert result.exit_code == 0, result.output
    else:
        # Lookup stubs return None, so these exit through their "not found" branch.
        assert result.exit_code == 1, result.output
        assert f"found with id {ID}" in result.output, result.output
    helper.assert_called_once()
    settings = cast(object, helper.call_args.args[0])
    assert isinstance(settings, PostgresDatabaseSettings)
    return settings


def write_config(tmp_path: Path, database: dict[str, object]) -> Path:
    lines = ["output:", "  kind: postgres", "  database:"]
    lines.extend(f"    {key}: {value}" for key, value in database.items())
    path = tmp_path / "config.yaml"
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_database_flag_alone_targets_local_postgres(
    mocker: MockerFixture,
    runner: CliRunner,
    subcommand: Subcommand,
    tmp_path: Path,
) -> None:
    helper = stub(mocker, subcommand)

    result = invoke(runner, subcommand, tmp_path, "-d", "demo_db")

    settings = assert_dispatched(result, subcommand, helper)
    assert settings == PostgresDatabaseSettings(host="localhost", database="demo_db")


def test_database_from_environment_targets_local_postgres(
    mocker: MockerFixture,
    runner: CliRunner,
    subcommand: Subcommand,
    tmp_path: Path,
) -> None:
    helper = stub(mocker, subcommand)

    result = invoke(runner, subcommand, tmp_path, env={"ELEANOR_DATABASE": "env_db"})

    settings = assert_dispatched(result, subcommand, helper)
    assert settings == PostgresDatabaseSettings(host="localhost", database="env_db")


def test_missing_database_without_config_fails_before_dispatch(
    mocker: MockerFixture,
    runner: CliRunner,
    subcommand: Subcommand,
    tmp_path: Path,
) -> None:
    helper = stub(mocker, subcommand)

    result = invoke(runner, subcommand, tmp_path)

    assert result.exit_code == 1
    assert "no database provided" in result.output
    assert "-d/--database" in result.output
    assert "Traceback" not in result.output
    helper.assert_not_called()


def test_config_file_settings_are_used(
    mocker: MockerFixture,
    runner: CliRunner,
    subcommand: Subcommand,
    tmp_path: Path,
) -> None:
    config = write_config(tmp_path, {"host": "db.remote", "port": 6543, "username": "alice", "database": "cfg_db"})
    helper = stub(mocker, subcommand)

    result = invoke(runner, subcommand, tmp_path, "-c", str(config))

    settings = assert_dispatched(result, subcommand, helper)
    assert settings == PostgresDatabaseSettings(host="db.remote", port=6543, username="alice", database="cfg_db")


def test_database_flag_overrides_config_file(
    mocker: MockerFixture,
    runner: CliRunner,
    subcommand: Subcommand,
    tmp_path: Path,
) -> None:
    config = write_config(tmp_path, {"host": "db.remote", "database": "cfg_db"})
    helper = stub(mocker, subcommand)

    result = invoke(runner, subcommand, tmp_path, "-c", str(config), "-d", "demo_db")

    settings = assert_dispatched(result, subcommand, helper)
    assert settings == PostgresDatabaseSettings(host="db.remote", database="demo_db")


def test_dump_scratch_reports_config_only_when_given(mocker: MockerFixture, runner: CliRunner, tmp_path: Path) -> None:
    _ = mocker.patch("eleanor.output.postgres.cli.dump.scratch.load_scratch_entry", return_value=None)
    config = write_config(tmp_path, {"database": "cfg_db"})

    without = runner.invoke(main, ["postgres", "dump", "scratch", ID, "-d", "demo_db"])
    with_config = runner.invoke(main, ["postgres", "dump", "scratch", ID, "-c", str(config)])

    assert "Loading" not in without.output
    assert f"Loading {config}" in with_config.output


def test_schema_needs_neither_config_nor_database(mocker: MockerFixture, runner: CliRunner) -> None:
    connect = mocker.patch("eleanor.output.postgres.persistence.connection.connect")

    result = runner.invoke(main, ["postgres", "schema"])

    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE IF NOT EXISTS "orders"' in result.output
    connect.assert_not_called()


def test_schema_writes_to_output_file(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "schema.sql"

    result = runner.invoke(main, ["postgres", "schema", "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE IF NOT EXISTS "orders"' in out.read_text(encoding="utf-8")
