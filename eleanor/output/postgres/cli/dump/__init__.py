import click

from eleanor.output.postgres.cli.dump.order import dump_order
from eleanor.output.postgres.cli.dump.scratch import dump_scratch


@click.group()
def dump() -> None:
    """Dump data from the postgres database in various formats"""


dump.add_command(dump_order)
dump.add_command(dump_scratch)

__all__ = ["dump"]
