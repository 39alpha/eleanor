import json
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner
from eleanor.cli import main
from eleanor.cli.gen import FORMATS, _load_template
from eleanor.order import Order
from pytest_mock import MockerFixture

DEMO = Path(__file__).parents[3] / "demo"


def _raw_order(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "o",
        "creator": "u",
        "kernel": {"kind": "eq36", "model": "b-dot", "charge_balance": "H+"},
        "temperature": 25.0,
        "pressure": 1.0,
        "elements": {"Na": 1.0},
    }
    base.update(overrides)
    return base


def _write_order(path: Path, **overrides: object) -> Path:
    _ = path.write_text(json.dumps(_raw_order(**overrides)), encoding="utf-8")
    return path


def _invoke_volume(runner: CliRunner, path: Path, *args: str):
    return runner.invoke(main, ["order", "volume", *args, str(path)])


def _mock_volume(mocker: MockerFixture, volume: float):
    order = mocker.create_autospec(Order, instance=True)
    order.volume.return_value = np.float64(volume)
    return mocker.patch("eleanor.cli.order.load_order", return_value=order)


def test_order_group_is_registered(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "order" in result.output


def test_order_group_lists_volume(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "--help"])
    assert result.exit_code == 0
    assert "volume" in result.output


@pytest.mark.parametrize("flag", ["--precision", "--format", "--verbose"])
def test_order_volume_help_lists_flags(runner: CliRunner, flag: str) -> None:
    result = runner.invoke(main, ["order", "volume", "--help"])
    assert result.exit_code == 0
    assert flag in result.output


def test_order_volume_help_explains_precision(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "--help"], terminal_width=1000)
    assert result.exit_code == 0
    assert "significant figures for adaptive" in result.output
    assert "decimal places otherwise" in result.output


def test_order_volume_help_shows_defaults(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "--help"], terminal_width=1000)
    assert result.exit_code == 0
    assert "[default: 3; x>=0]" in result.output
    assert "[default: adaptive]" in result.output


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        pytest.param({}, "0", id="all-scalar"),
        pytest.param({"temperature": {"min": 20.0, "max": 30.0}}, "10", id="range"),
        pytest.param({"pressure": [1.0, 2.0, 3.0]}, "3", id="list"),
        pytest.param(
            {"temperature": {"min": 0.0, "max": 10.0}, "elements": {"Na": {"min": 0.5, "max": 2.5}}},
            "20",
            id="ranges-multiply",
        ),
        pytest.param(
            {"temperature": {"min": 0.0, "max": 10.0}, "pressure": [1.0, 2.0]},
            "20",
            id="range-and-list",
        ),
    ],
)
def test_order_volume_prints_volume(
    runner: CliRunner, tmp_path: Path, overrides: dict[str, object], expected: str
) -> None:
    path = _write_order(tmp_path / "order.json", **overrides)
    result = _invoke_volume(runner, path)
    assert result.exit_code == 0
    assert result.output == f"{expected}\n"


@pytest.mark.parametrize("suffix", [".yaml", ".yml", ".json", ".toml"])
def test_order_volume_accepts_each_order_format(runner: CliRunner, tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"order{suffix}"
    match suffix:
        case ".json":
            text = json.dumps(_raw_order(temperature={"min": 20.0, "max": 30.0}))
        case ".toml":
            text = """
                name = "o"
                creator = "u"
                pressure = 1.0
                temperature = { min = 20.0, max = 30.0 }
                kernel = { kind = "eq36", model = "b-dot", charge_balance = "H+" }
                elements = { Na = 1.0 }
            """
        case _:
            text = """
                name: o
                creator: u
                kernel: {kind: eq36, model: b-dot, charge_balance: H+}
                temperature: {min: 20.0, max: 30.0}
                pressure: 1.0
                elements: {Na: 1.0}
            """
    _ = path.write_text("\n".join(line.strip() for line in text.splitlines()), encoding="utf-8")

    result = _invoke_volume(runner, path)
    assert result.exit_code == 0
    assert result.output == "10\n"


@pytest.mark.parametrize("path", sorted(DEMO.glob("*.yaml")), ids=lambda p: p.stem)
def test_order_volume_matches_order_volume_for_demos(runner: CliRunner, path: Path) -> None:
    result = _invoke_volume(runner, path)
    assert result.exit_code == 0
    assert result.output == f"{Order.from_file(path).volume():.3g}\n"


def test_order_volume_loads_the_given_order(runner: CliRunner, tmp_path: Path, mocker: MockerFixture) -> None:
    load_order = _mock_volume(mocker, 42.5)
    path = _write_order(tmp_path / "order.json")

    result = _invoke_volume(runner, path)

    assert result.exit_code == 0
    assert result.output == "42.5\n"
    load_order.assert_called_once_with(str(path))
    load_order.return_value.volume.assert_called_once_with()


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        pytest.param([], "1.23e+03", id="default"),
        pytest.param(["-p", "6"], "1234.57", id="adaptive-precision"),
        pytest.param(["-f", "adaptive", "-p", "0"], "1e+03", id="adaptive-zero"),
        pytest.param(["-f", "floating"], "1234.568", id="floating"),
        pytest.param(["--format", "floating", "-p", "0"], "1235", id="floating-zero"),
        pytest.param(["-f", "floating", "--precision", "6"], "1234.567800", id="floating-pads"),
        pytest.param(["-f", "scientific"], "1.235e+03", id="scientific"),
        pytest.param(["-f", "scientific", "-p", "1"], "1.2e+03", id="scientific-precision"),
        pytest.param(["-f", "scientific", "-p", "0"], "1e+03", id="scientific-zero"),
        pytest.param(["-f", "SCIENTIFIC"], "1.235e+03", id="case-insensitive"),
    ],
)
def test_order_volume_formats_output(
    runner: CliRunner, tmp_path: Path, mocker: MockerFixture, args: list[str], expected: str
) -> None:
    _ = _mock_volume(mocker, 1234.5678)
    result = _invoke_volume(runner, _write_order(tmp_path / "order.json"), *args)
    assert result.exit_code == 0
    assert result.output == f"{expected}\n"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        pytest.param([], "1.5e-07", id="adaptive"),
        pytest.param(["-f", "scientific"], "1.500e-07", id="scientific"),
        pytest.param(["-f", "floating"], "0.000", id="floating"),
    ],
)
def test_order_volume_formats_small_volumes(
    runner: CliRunner, tmp_path: Path, mocker: MockerFixture, args: list[str], expected: str
) -> None:
    _ = _mock_volume(mocker, 1.5e-7)
    result = _invoke_volume(runner, _write_order(tmp_path / "order.json"), *args)
    assert result.exit_code == 0
    assert result.output == f"{expected}\n"


def test_order_volume_rejects_an_unknown_format(runner: CliRunner, tmp_path: Path) -> None:
    result = _invoke_volume(runner, _write_order(tmp_path / "order.json"), "-f", "fixed")
    assert result.exit_code == 2
    assert "Invalid value for '-f' / '--format'" in result.output


@pytest.mark.parametrize("value", ["-1", "1.5", "three"])
def test_order_volume_rejects_invalid_precision(runner: CliRunner, tmp_path: Path, value: str) -> None:
    result = _invoke_volume(runner, _write_order(tmp_path / "order.json"), "-p", value)
    assert result.exit_code == 2
    assert "Invalid value for '-p' / '--precision'" in result.output


def test_order_volume_requires_an_argument(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume"])
    assert result.exit_code == 2
    assert "Missing argument 'ORDER'" in result.output


def test_order_volume_rejects_a_missing_file(runner: CliRunner, tmp_path: Path) -> None:
    result = _invoke_volume(runner, tmp_path / "missing.yaml")
    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_order_volume_rejects_a_directory(runner: CliRunner, tmp_path: Path) -> None:
    result = _invoke_volume(runner, tmp_path)
    assert result.exit_code == 2
    assert "is a directory" in result.output


def test_order_volume_detects_the_format_of_an_unrecognized_extension(runner: CliRunner, tmp_path: Path) -> None:
    path = _write_order(tmp_path / "order.txt", temperature={"min": 20.0, "max": 30.0})
    result = _invoke_volume(runner, path)
    assert result.exit_code == 0, result.output
    assert result.output == "10\n"


def test_order_volume_reports_unparseable_content_with_an_unrecognized_extension(
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    path = tmp_path / "order.txt"
    _ = path.write_text("[kernel]\nkind = \n", encoding="utf-8")
    result = _invoke_volume(runner, path)
    assert result.exit_code == 1
    assert f"Error: failed to load the order" in result.stderr
    assert "Traceback" not in result.stderr


def test_order_volume_reports_failure_to_load_the_order(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "order.json"
    _ = path.write_text(json.dumps({"name": "o"}), encoding="utf-8")
    result = _invoke_volume(runner, path)
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: ")
    assert "creator must be a string" in result.stderr
    assert "Traceback" not in result.stderr


def test_order_volume_reports_failure_to_compute_volume(
    runner: CliRunner, tmp_path: Path, mocker: MockerFixture
) -> None:
    load_order = _mock_volume(mocker, 0.0)
    load_order.return_value.volume.side_effect = RuntimeError("boom")
    result = _invoke_volume(runner, _write_order(tmp_path / "order.json"))
    assert result.exit_code == 1
    assert result.stderr == "Error: failed to compute the order volume - boom\n"


@pytest.mark.parametrize("flag", ["-v", "--verbose"])
def test_order_volume_verbose_prints_traceback(runner: CliRunner, tmp_path: Path, flag: str) -> None:
    path = tmp_path / "order.json"
    _ = path.write_text(json.dumps({"name": "o"}), encoding="utf-8")
    result = _invoke_volume(runner, path, flag)
    assert result.exit_code == 1
    assert "Traceback" in result.stderr
    assert "EleanorError: creator must be a string" in result.stderr
    assert "EleanorError: failed to load the order - creator must be a string" in result.stderr
    assert result.stdout == ""


def test_order_volume_verbose_has_no_effect_on_success(runner: CliRunner, tmp_path: Path) -> None:
    path = _write_order(tmp_path / "order.json", temperature={"min": 20.0, "max": 30.0})
    result = _invoke_volume(runner, path, "-v")
    assert result.exit_code == 0
    assert result.output == "10\n"


def _template(fmt: str) -> str:
    content = _load_template("order", fmt)
    assert content is not None
    return content


@pytest.mark.parametrize("fmt", FORMATS)
def test_order_volume_reads_each_format_from_stdin(runner: CliRunner, fmt: str) -> None:
    result = runner.invoke(main, ["order", "volume", "-"], input=_template(fmt))
    assert result.exit_code == 0, result.output
    assert result.output == "750\n"


def test_order_volume_reads_bytes_from_stdin(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "-"], input=_template("toml").encode())
    assert result.exit_code == 0, result.output
    assert result.output == "750\n"


def test_order_volume_names_stdin_in_parse_errors(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "-"], input="[kernel]\nkind = \n")
    assert result.exit_code == 1
    assert "failed to load the order" in result.stderr
    assert "Traceback" not in result.stderr


def test_order_volume_reports_validation_errors_from_stdin(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "-"], input="name: o\n")
    assert result.exit_code == 1
    assert "creator must be a string" in result.stderr


def test_order_volume_reports_empty_stdin_as_an_empty_order(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "-"], input="")
    assert result.exit_code == 1
    assert "order is empty" in result.stderr


def test_order_volume_help_documents_stdin(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "--help"], terminal_width=1000)
    assert result.exit_code == 0
    assert "pass - to read" in result.output


def test_order_volume_help_does_not_limit_stdin_to_yaml(runner: CliRunner) -> None:
    result = runner.invoke(main, ["order", "volume", "--help"], terminal_width=1000)
    assert result.exit_code == 0
    assert "YAML" not in result.output
