from typing import TextIO

import click

from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.persistence.repositories import get_order
from eleanor.output.postgres.tools.order import DumpFormat, dump_order
from eleanor.util import require_uuid_id

_PROPERTIES: tuple[str, ...] = (
    "name",
    "creator",
    "create_date",
    "tags",
    "notes",
    "eleanor_version",
    "seed",
    "kernel",
    "navigator",
    "water_mass",
    "temperature",
    "pressure",
    "elements",
    "species",
    "reactants",
    "suppressions",
    "constraints",
)


_OPTIONAL_PROPERTIES: frozenset[str] = frozenset(
    {
        "tags",
        "notes",
        "species",
        "reactants",
        "suppressions",
        "constraints",
    }
)


@click.command()
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
@click.argument("order_id", type=click.STRING)
@config_options()
def order(
    output: TextIO,
    to: DumpFormat,
    keep_empty: bool,
    order_id: str,
    config: str,
    database: str | None,
) -> None:
    """Dump an order suitable for rerunning Eleanor."""

    settings = sole_postgres_settings(
        config_from_args(config, database, assume_default_postgres=True),
        "dump order",
    )
    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    try:
        oid = require_uuid_id(order_id, "order")
    except EleanorError as e:
        raise click.ClickException(str(e)) from None

    row = get_order(settings.database, oid)
    if row is None:
        msg = f"no order found with id {oid}"
        raise click.ClickException(msg)

    dump_order(output, row.raw, format=to, keep_empty=keep_empty)


__all__ = ["order"]
