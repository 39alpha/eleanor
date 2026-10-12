from pathlib import Path
from typing import TextIO

import click

from eleanor.cli.command import command
from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.tools.order import DumpFormat, dump_order
from eleanor.output.postgres.tools.variable_space import get_vs_as_order
from eleanor.util import first_line, require_uuid_id


@command(name="vs")
@click.option("-o", "--output", type=click.File("w"), default="-", help="Output file (default: stdout).")
@click.option(
    "-t",
    "--to",
    type=click.Choice(DumpFormat, case_sensitive=False),
    help="Output file format (default: yaml, overridden by file extension)",
)
@click.option(
    "-e",
    "--keep-empty",
    is_flag=True,
    help="Output optional properties even if they are empty (e.g. None, {}, [], etc...)",
)
@click.argument("vs_id", type=click.STRING)
@config_options(required=False)
def dump_variable_space(
    output: TextIO,
    to: DumpFormat,
    keep_empty: bool,
    vs_id: str,
    config: Path | None,
    database: str | None,
) -> None:
    """Dump a variable space point as an order suitable for rerunning Eleanor."""
    vsid = require_uuid_id(vs_id, "variable space")

    settings = sole_postgres_settings(
        config_from_args(config, database, assume_default_postgres=True),
        "dump vs",
    )

    try:
        order = get_vs_as_order(settings.database, vsid)
    except Exception as e:
        msg = f"failed to fetch variable space point {vsid} - {first_line(str(e) or type(e).__name__)}"
        raise EleanorError(msg) from e

    if order is None:
        msg = f"no variable space point found with id {vsid}"
        raise EleanorError(msg)

    dump_order(output, order, format=to, keep_empty=keep_empty)


__all__ = ["dump_variable_space"]
