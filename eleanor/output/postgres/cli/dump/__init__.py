import click

from eleanor.output.postgres.cli.dump.order import order as dump_order
from eleanor.output.postgres.cli.dump.scratch import dump_scratch
from eleanor.output.postgres.cli.dump.variable_space import dump_variable_space


@click.group()
def dump() -> None:
    """Dump data from the postgres database in various formats"""


dump.add_command(dump_order)
dump.add_command(dump_scratch)
dump.add_command(dump_variable_space)

__all__ = ["dump"]
