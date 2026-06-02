from click.testing import CliRunner

from eleanor.cli import main


def test_doctor_lists_postgres_cli_plugin(runner: CliRunner) -> None:
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "CLI commands" in result.output
    assert "postgres" in result.output
