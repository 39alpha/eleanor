"""Unit tests for the ``eleanor postgres export duckdb`` CLI command."""

from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner, Result
from pytest_mock import MockerFixture

from eleanor.cli import main
from eleanor.config import Config
from eleanor.output.postgres.cli.export.duckdb import _parse_options, _unquote
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.output.postgres.tools.duckdb import ExportFormat, ExportOptions

_MODULE = "eleanor.output.postgres.cli.export.duckdb"


def _postgres_config(database: str | None = "demo") -> Config:
    raw: dict[str, object] = {"kind": "postgres"}
    if database is not None:
        raw["database"] = {"database": database, "username": "alice", "password": "hunter2"}
    return Config.from_dict({"output": raw})


@pytest.fixture
def export(mocker: MockerFixture) -> MagicMock:
    _ = mocker.patch(f"{_MODULE}.config_from_args", return_value=_postgres_config())
    return mocker.patch(f"{_MODULE}.export_duckdb")


def _invoke(runner: CliRunner, *args: str) -> Result:
    return runner.invoke(main, ["postgres", "export", "duckdb", "-c", "/fake.yaml", *args])


def test_export_help_lists_duckdb(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "export", "--help"])
    assert result.exit_code == 0
    assert "duckdb" in result.output


def test_export_duckdb_help_lists_options(runner: CliRunner) -> None:
    result = runner.invoke(main, ["postgres", "export", "duckdb", "--help"])
    assert result.exit_code == 0
    for flag in ("--output", "--hive", "--hive-type", "--export-option", "--no-export-empty", "--verbose"):
        assert flag in result.output


def test_requires_output_or_hive(runner: CliRunner, export: MagicMock) -> None:
    result = _invoke(runner)
    assert result.exit_code != 0
    assert "at least one of --output= and --hive= must be provided" in result.output
    export.assert_not_called()


def test_rejects_existing_output_file(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    output = tmp_path / "out.db"
    _ = output.write_bytes(b"keep me")

    result = _invoke(runner, "-o", str(output))

    assert result.exit_code != 0
    assert "cannot export to existing DuckDB database" in result.output
    export.assert_not_called()
    assert output.read_bytes() == b"keep me"


def test_rejects_existing_output_file_after_expanding_user(
    runner: CliRunner,
    export: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    output = tmp_path / "out.db"
    _ = output.write_bytes(b"keep me")

    result = _invoke(runner, "-o", "~/out.db")

    assert result.exit_code != 0
    assert "cannot export to existing DuckDB database" in result.output
    assert "failed to export database" not in result.output
    export.assert_not_called()
    assert output.read_bytes() == b"keep me"


def test_allows_existing_hive_directory(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    result = _invoke(runner, "-H", str(tmp_path))
    assert result.exit_code == 0, result.output
    export.assert_called_once()


def test_forwards_defaults_to_export(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    output = tmp_path / "out.db"

    result = _invoke(runner, "-o", str(output))

    assert result.exit_code == 0, result.output
    export.assert_called_once_with(
        PostgresDatabaseSettings(database="demo", username="alice", password="hunter2"),
        db_file=output,
        hive=None,
        format=ExportFormat.PARQUET,
        no_export_empty=False,
        verbose=False,
        options=None,
    )


def test_forwards_every_option_to_export(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    output = tmp_path / "out.db"
    hive = tmp_path / "hive"

    result = _invoke(
        runner,
        "-o",
        str(output),
        "-H",
        str(hive),
        "-t",
        "CSV",
        "-e",
        "delimiter=|",
        "-e",
        "header",
        "-n",
        "-v",
    )

    assert result.exit_code == 0, result.output
    export.assert_called_once_with(
        PostgresDatabaseSettings(database="demo", username="alice", password="hunter2"),
        db_file=output,
        hive=hive,
        format=ExportFormat.CSV,
        no_export_empty=True,
        verbose=True,
        options={"DELIMITER": "|", "HEADER": True},
    )


def test_rejects_unknown_hive_type(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    result = _invoke(runner, "-H", str(tmp_path), "-t", "xlsx")
    assert result.exit_code != 0
    export.assert_not_called()


def test_rejects_malformed_export_option(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    result = _invoke(runner, "-H", str(tmp_path), "-e", "=value")
    assert result.exit_code != 0
    assert "must be given as KEY or KEY=value" in result.output
    export.assert_not_called()


def test_wraps_export_failure(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    export.side_effect = RuntimeError("boom")

    result = _invoke(runner, "-o", str(tmp_path / "out.db"))

    assert result.exit_code != 0
    assert "failed to export database - boom" in result.output


def test_requires_a_database(runner: CliRunner, mocker: MockerFixture, tmp_path: Path) -> None:
    _ = mocker.patch(f"{_MODULE}.config_from_args", return_value=_postgres_config(database=None))
    export = mocker.patch(f"{_MODULE}.export_duckdb")

    result = _invoke(runner, "-o", str(tmp_path / "out.db"))

    assert result.exit_code != 0
    assert "no database provided" in result.output
    export.assert_not_called()


def test_assumes_default_postgres_sink(runner: CliRunner, mocker: MockerFixture, tmp_path: Path) -> None:
    config_from_args = mocker.patch(f"{_MODULE}.config_from_args", return_value=_postgres_config())
    _ = mocker.patch(f"{_MODULE}.export_duckdb")

    result = _invoke(runner, "-d", "other", "-o", str(tmp_path / "out.db"))

    assert result.exit_code == 0, result.output
    config_from_args.assert_called_once_with("/fake.yaml", "other", assume_default_postgres=True)


def test_parse_options_returns_none_without_tokens() -> None:
    assert _parse_options(()) is None


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("header", {"HEADER": True}),
        ("HEADER=true", {"HEADER": True}),
        ("header=True", {"HEADER": True}),
        ("append=false", {"APPEND": False}),
        ("append=FALSE", {"APPEND": False}),
        ("row_groups_per_file=10", {"ROW_GROUPS_PER_FILE": 10}),
        ("row_groups_per_file=-1", {"ROW_GROUPS_PER_FILE": -1}),
        ("compression=snappy", {"COMPRESSION": "snappy"}),
        ("delimiter=|", {"DELIMITER": "|"}),
        ("dateformat=%Y-%m-%d", {"DATEFORMAT": "%Y-%m-%d"}),
        ("filename_pattern=a=b", {"FILENAME_PATTERN": "a=b"}),
        ("compression= zstd ", {"COMPRESSION": "zstd"}),
        ("nullstr=", {"NULLSTR": ""}),
    ],
)
def test_parse_options_coerces_values(token: str, expected: ExportOptions) -> None:
    assert _parse_options((token,)) == expected


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("dateformat='007'", {"DATEFORMAT": "007"}),
        ('dateformat="007"', {"DATEFORMAT": "007"}),
        ("nullstr='true'", {"NULLSTR": "true"}),
        ('nullstr="False"', {"NULLSTR": "False"}),
        ("delimiter='|'", {"DELIMITER": "|"}),
        ("nullstr=''", {"NULLSTR": ""}),
        ("nullstr=' padded '", {"NULLSTR": " padded "}),
    ],
)
def test_parse_options_keeps_quoted_values_as_strings(token: str, expected: ExportOptions) -> None:
    assert _parse_options((token,)) == expected


def test_forwards_quoted_option_as_string(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    result = _invoke(runner, "-H", str(tmp_path), "-e", "row_groups_per_file='10'")

    assert result.exit_code == 0, result.output
    assert export.call_args.kwargs["options"] == {"ROW_GROUPS_PER_FILE": "10"}


def test_parse_options_later_tokens_win() -> None:
    assert _parse_options(("compression=zstd", "COMPRESSION=gzip")) == {"COMPRESSION": "gzip"}


def test_parse_options_rejects_missing_key() -> None:
    with pytest.raises(click.ClickException, match="must be given as KEY or KEY=value"):
        _ = _parse_options(("=zstd",))


def test_forwards_relative_output_as_absolute_path(
    runner: CliRunner,
    export: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = _invoke(runner, "-o", "out.db", "-H", "hive")

    assert result.exit_code == 0, result.output
    assert export.call_args.kwargs["db_file"] == tmp_path.resolve() / "out.db"
    assert export.call_args.kwargs["hive"] == tmp_path.resolve() / "hive"


def test_forwards_user_expanded_paths(
    runner: CliRunner,
    export: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    result = _invoke(runner, "-o", "~/out.db", "-H", "~/hive")

    assert result.exit_code == 0, result.output
    assert export.call_args.kwargs["db_file"] == tmp_path.resolve() / "out.db"
    assert export.call_args.kwargs["hive"] == tmp_path.resolve() / "hive"


def test_forwards_paths_with_symlinks_resolved(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)

    result = _invoke(runner, "-o", str(tmp_path / "link" / "out.db"), "-H", str(tmp_path / "link" / "hive"))

    assert result.exit_code == 0, result.output
    assert export.call_args.kwargs["db_file"] == real.resolve() / "out.db"
    assert export.call_args.kwargs["hive"] == real.resolve() / "hive"


def test_rejects_relative_existing_output_with_absolute_path(
    runner: CliRunner,
    export: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / "out.db").write_bytes(b"keep me")

    result = _invoke(runner, "-o", "out.db")

    assert result.exit_code != 0
    assert f"cannot export to existing DuckDB database '{tmp_path.resolve() / 'out.db'}'" in result.output
    export.assert_not_called()


def test_rejects_directory_as_output(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    result = _invoke(runner, "-o", str(tmp_path))

    assert result.exit_code != 0
    assert "is a directory" in result.output
    export.assert_not_called()


def test_rejects_file_as_hive(runner: CliRunner, export: MagicMock, tmp_path: Path) -> None:
    hive = tmp_path / "hive"
    _ = hive.write_text("")

    result = _invoke(runner, "-H", str(hive))

    assert result.exit_code != 0
    assert "is a file" in result.output
    export.assert_not_called()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("'abc'", "abc"),
        ('"abc"', "abc"),
        ("''", ""),
        ('""', ""),
        ("abc", "abc"),
        ("", ""),
        ("'", "'"),
        ('"', '"'),
        ("'abc", "'abc"),
        ("abc'", "abc'"),
        ("'abc\"", "'abc\""),
        ("\"abc'", "\"abc'"),
        ('""""', '""'),
        ("'\"'", '"'),
        ('"\'"', "'"),
        ("'it's'", "it's"),
        ("a'b'c", "a'b'c"),
    ],
)
def test_unquote_strips_one_matching_pair(value: str, expected: str) -> None:
    assert _unquote(value) == expected


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("delimiter='abc", {"DELIMITER": "'abc"}),
        ("quote='\"'", {"QUOTE": '"'}),
        ('escape="\'"', {"ESCAPE": "'"}),
        ("x='10", {"X": "'10"}),
    ],
)
def test_parse_options_handles_unbalanced_and_nested_quotes(token: str, expected: ExportOptions) -> None:
    assert _parse_options((token,)) == expected
