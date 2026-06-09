import pytest
from click.testing import CliRunner
from eleanor.cli import main
from eleanor.cli.gen import FORMATS, validate_template
from eleanor.config import Config
from eleanor.order import Order


@pytest.mark.parametrize("fmt", FORMATS)
def test_emits_valid_config(runner: CliRunner, fmt: str) -> None:
    expected = validate_template("config", fmt)

    result = runner.invoke(main, ["gen", "config", "--format", fmt])
    assert result.exit_code == 0

    match fmt:
        case "yaml":
            got = Config.from_yamls(result.output)
        case "toml":
            got = Config.from_tomls(result.output)
        case "json":
            got = Config.from_jsons(result.output)
        case _:
            pytest.fail(f"uncovered config file format {fmt!r}")

    assert got == expected


def test_emits_error_for_invalid_config_format(runner: CliRunner) -> None:
    result = runner.invoke(main, ["gen", "config", "--format", "bogus"])
    assert result.exit_code != 0
    assert "'bogus' is not one of" in result.output


@pytest.mark.parametrize("fmt", FORMATS)
def test_emits_valid_order(runner: CliRunner, fmt: str) -> None:
    expected = validate_template("order", fmt)

    result = runner.invoke(main, ["gen", "order", "--format", fmt])
    assert result.exit_code == 0

    match fmt:
        case "yaml":
            got = Order.from_yamls(result.output)
        case "toml":
            got = Order.from_tomls(result.output)
        case "json":
            got = Order.from_jsons(result.output)
        case _:
            pytest.fail(f"uncovered order file format {fmt!r}")

    assert got == expected


def test_emits_error_for_invalid_order_format(runner: CliRunner) -> None:
    result = runner.invoke(main, ["gen", "order", "--format", "bogus"])
    assert result.exit_code != 0
    assert "'bogus' is not one of" in result.output
