from typing import TextIO

import click

from eleanor.cli.util import config_from_args, config_options
from eleanor.output.postgres.config import database_config_from_config
from eleanor.output.postgres.tools import dump_schema


@click.command()
@click.option("-o", "--output", type=click.File("w"), default="-", help="Output file (default: stdout).")
@config_options
def schema(output: TextIO, config: str, database: str | None) -> None:
    """Dump an Eleanor database schema."""
    cfg = config_from_args(config, database)
    database_config = database_config_from_config(cfg)
    if database_config.database is None:
        raise click.ClickException("no database provided")
    dump_schema(database_config, output)
