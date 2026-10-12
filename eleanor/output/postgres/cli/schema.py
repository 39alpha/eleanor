from typing import TextIO

import click

from eleanor.cli.command import command
from eleanor.output.postgres.tools import dump_schema


@command()
@click.option("-o", "--output", type=click.File("w"), default="-", help="Output file (default: stdout).")
def schema(output: TextIO) -> None:
    """Dump an Eleanor database schema.

    Dumps the cumulative target schema. **Do not pipe this into psql to
    bootstrap a new database** — use ``eleanor postgres migrate``
    instead, so the tracking table is populated. Use this command for
    documentation or for capturing the body of a new migration file.
    """
    dump_schema(output)


__all__ = ["schema"]
