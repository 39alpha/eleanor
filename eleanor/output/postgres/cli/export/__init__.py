import click

from eleanor.output.postgres.cli.export.duckdb import duckdb


@click.group()
def export() -> None:
    """Export data from the postgres database in various formats"""


export.add_command(duckdb)

__all__ = ["export"]
