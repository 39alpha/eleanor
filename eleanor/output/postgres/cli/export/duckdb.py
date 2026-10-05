from pathlib import Path

import click

from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.output.postgres.tools.duckdb import export_duckdb


@click.command()
@click.option(
    "-o",
    "--output",
    type=click.Path(exists=False, file_okay=True, dir_okay=False, writable=True),
    help="Save DuckDB database as file.",
)
@click.option(
    "-p",
    "--parquet",
    type=click.Path(exists=False, file_okay=False, dir_okay=True, writable=True),
    help="Export DuckDB database to parquet-based hive",
)
@config_options()
def duckdb(output: Path | None, parquet: Path | None, config: str, database: str | None) -> None:
    """Export an Eleanor PostgreSQL database for DuckDB."""

    if output is None and parquet is None:
        msg = "at least one of --output= and --parquet= must be provided"
        raise click.ClickException(msg)

    settings = sole_postgres_settings(
        config_from_args(config, database, assume_default_postgres=True),
        "export duckdb",
    )
    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    export_duckdb(settings.database, db_file=output)


__all__ = ["duckdb"]
