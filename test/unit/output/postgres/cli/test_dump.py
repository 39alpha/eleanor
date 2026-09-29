from click.testing import CliRunner
from eleanor.cli import main


def test_dump_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "dump", "--help"])
    assert result.exit_code == 0
    for sub in ("order", "scratch"):
        assert sub in result.output


def test_postgres_dump_order_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "dump", "order", "--help"])
    assert result.exit_code == 0


def test_postgres_dump_scratch_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "dump", "scratch", "--help"])
    assert result.exit_code == 0
