import click

from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.output.postgres.tools.duckdb import export_duckdb


@click.command()
@config_options()
def duckdb(config: str, database: str | None) -> None:
    """Export an Eleanor PostgreSQL database for DuckDB."""

    settings = sole_postgres_settings(
        config_from_args(config, database, assume_default_postgres=True),
        "export duckdb",
    )
    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    export_duckdb(settings.database)


__all__ = ["duckdb"]
