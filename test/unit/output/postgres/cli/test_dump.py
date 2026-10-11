import pytest
from click.testing import CliRunner
from eleanor.cli import main
from pytest_mock import MockerFixture


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


def test_postgres_dump_vs_help_succeeds(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "dump", "vs", "--help"])
    assert result.exit_code == 0


_VS_ID = "018f3a1c-0000-7000-8000-000000000000"


def test_dump_vs_reports_lookup_failures(runner: CliRunner, mocker: MockerFixture) -> None:
    _ = mocker.patch(
        "eleanor.output.postgres.cli.dump.variable_space.get_vs_as_order",
        side_effect=RuntimeError("boom"),
    )

    result = runner.invoke(main, ["postgres", "dump", "vs", _VS_ID, "-d", "demo_db"])

    assert result.exit_code == 1
    assert result.stderr == "Error: failed to dump variable space point - boom\n"


@pytest.mark.parametrize("flag", ["-v", "--verbose"])
def test_dump_vs_verbose_prints_the_traceback(runner: CliRunner, mocker: MockerFixture, flag: str) -> None:
    _ = mocker.patch(
        "eleanor.output.postgres.cli.dump.variable_space.get_vs_as_order",
        side_effect=RuntimeError("boom"),
    )

    result = runner.invoke(main, ["postgres", "dump", "vs", flag, _VS_ID, "-d", "demo_db"])

    assert result.exit_code == 1
    assert "Traceback" in result.stderr
    assert "RuntimeError: boom" in result.stderr
