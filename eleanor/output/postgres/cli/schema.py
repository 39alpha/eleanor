from typing import TextIO

import click

from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.output.postgres.tools import dump_schema


@click.command()
@click.option("-o", "--output", type=click.File("w"), default="-", help="Output file (default: stdout).")
@config_options()
def schema(output: TextIO, config: str, database: str | None) -> None:
    """Dump an Eleanor database schema.

    Dumps the cumulative target schema. **Do not pipe this into psql to
    bootstrap a new database** — use ``eleanor postgres migrate``
    instead, so the tracking table is populated. Use this command for
    documentation or for capturing the body of a new migration file.
    """

    settings = sole_postgres_settings(config_from_args(config, database), "dump postgres schema")

    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    dump_schema(settings.database, output)


__all__ = ["schema"]
