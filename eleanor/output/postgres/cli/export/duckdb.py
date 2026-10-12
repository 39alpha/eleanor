from pathlib import Path

import click

from eleanor.cli.command import command
from eleanor.cli.util import (
    config_from_args,
    config_options,
    show_verbose_output,
    sole_postgres_settings,
)
from eleanor.output.postgres.tools.duckdb import ExportFormat, ExportOptions, export_duckdb


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":  # noqa: PLR2004
        return value[1:-1]
    return value


def _parse_options(tokens: tuple[str, ...]) -> ExportOptions | None:
    if not tokens:
        return None

    parsed: ExportOptions = {}
    for token in tokens:
        name, separator, value = token.partition("=")
        if not name:
            msg = f"--export-option {token!r} must be given as KEY or KEY=value"
            raise click.ClickException(msg)

        name = name.upper()
        if not separator:
            parsed[name] = True
            continue

        value = value.strip()
        if value.lower() == "true":
            parsed[name] = True
        elif value.lower() == "false":
            parsed[name] = False
        else:
            try:
                parsed[name] = int(value)
            except ValueError:
                parsed[name] = _unquote(value)
    return parsed


@command(error_message="failed to export database")
@click.option(
    "-o",
    "--output",
    type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True),
    help="Save DuckDB database as file.",
)
@click.option(
    "-H",
    "--hive",
    type=click.Path(exists=False, file_okay=False, dir_okay=True, writable=True),
    help="Export DuckDB database to a hive",
)
@click.option(
    "-t",
    "--hive-type",
    type=click.Choice(ExportFormat, case_sensitive=False),
    default=ExportFormat.PARQUET,
    help="Export DuckDB database to a hive",
)
@click.option(
    "-e",
    "--export-option",
    type=str,
    multiple=True,
    help="Provide one or more hive export options in key=value format",
)
@click.option(
    "-n",
    "--no-export-empty",
    is_flag=True,
    help="Do not export empty tables",
)
@config_options(required=False)
def duckdb(
    output: Path | None,
    hive: Path | None,
    hive_type: ExportFormat,
    export_option: tuple[str, ...],
    no_export_empty: bool = False,
    *,
    config: Path | None,
    database: str | None,
) -> None:
    """Export an Eleanor PostgreSQL database for DuckDB."""
    verbose = show_verbose_output()

    if output is None and hive is None:
        msg = "at least one of --output= and --hive= must be provided"
        raise click.UsageError(msg)

    output = Path(output).expanduser().resolve() if output is not None else None
    if output is not None and output.exists():
        msg = f"cannot export to existing DuckDB database '{output!s}'"
        raise click.ClickException(msg)

    hive = Path(hive).expanduser().resolve() if hive is not None else None

    settings = sole_postgres_settings(
        config_from_args(config, database, assume_default_postgres=True),
        "export duckdb",
    )

    options = _parse_options(export_option)

    export_duckdb(
        settings.database,
        db_file=output,
        hive=hive,
        format=hive_type,
        no_export_empty=no_export_empty,
        verbose=verbose,
        options=options,
    )


__all__ = ["duckdb"]
