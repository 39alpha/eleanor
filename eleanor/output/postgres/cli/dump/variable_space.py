from pathlib import Path
from typing import TextIO

import click

from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.tools.order import DumpFormat, dump_order
from eleanor.output.postgres.tools.variable_space import get_vs_as_order
from eleanor.util import require_uuid_id


@click.command(name="vs")
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

    settings = sole_postgres_settings(
        config_from_args(config, database, assume_default_postgres=True),
        "dump vs",
    )

    try:
        vsid = require_uuid_id(vs_id, "variable space")
    except EleanorError as e:
        raise click.ClickException(str(e)) from None

    try:
        order = get_vs_as_order(settings.database, vsid)
    except Exception as e:
        msg = f"failed to dump variable space point - {e}"
        raise click.ClickException(msg) from e

    if order is None:
        msg = f"no variable space point found with id {vsid}"
        raise click.ClickException(msg)

    dump_order(output, order, format=to, keep_empty=keep_empty)


__all__ = ["dump_variable_space"]
