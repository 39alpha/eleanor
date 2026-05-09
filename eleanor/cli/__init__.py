import click

import eleanor
from eleanor.cli.bulkload import bulkload
from eleanor.cli.doctor import doctor
from eleanor.cli.gen import gen
from eleanor.cli.run import run
from eleanor.cli.schema import schema
from eleanor.cli.scratch import scratch


@click.group()
@click.version_option(version=eleanor.__version__, prog_name="eleanor")
def main() -> None:
    """Run eleanor or interact with a generated dataset."""


main.add_command(run)
main.add_command(schema)
main.add_command(bulkload)
main.add_command(doctor)
main.add_command(gen)
main.add_command(scratch)
