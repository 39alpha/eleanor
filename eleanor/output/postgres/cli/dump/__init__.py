import click

from eleanor.output.postgres.cli.dump.order import dump_order


@click.group()
def dump() -> None:
    """Dump data from the postgres database in various formats"""


dump.add_command(dump_order)

__all__ = ["dump"]
