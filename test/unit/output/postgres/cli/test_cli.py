from click.testing import CliRunner
from eleanor.cli import main


def test_postgres_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "--help"])
    assert result.exit_code == 0
    for sub in ("schema", "bulkload", "migrate", "dump"):
        assert sub in result.output


def test_postgres_schema_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "schema", "--help"])
    assert result.exit_code == 0


def test_postgres_bulkload_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "bulkload", "--help"])
    assert result.exit_code == 0


def test_postgres_migrate_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "migrate", "--help"])
    assert result.exit_code == 0
