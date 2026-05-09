"""``eleanor bulkload`` -- drop or recreate constraints around a bulk-load window.

Two-phase workflow for callers running an out-of-band bulk-load (e.g.
ingesting a precomputed dataset, or a rerun that reuses a previously
populated database):

1. ``eleanor bulkload drop`` -- strip every secondary index + FK / CHECK
   constraint declared by the schema. Subsequent INSERTs / COPYs run
   without paying the per-row constraint-checking and index-maintenance
   cost.
2. ``eleanor bulkload recreate`` -- put everything back. Run this once
   the bulk-load workload finishes; if the data violates any
   constraint, the recreate transaction rolls back and the failure is
   reported.

Programmatic callers should prefer
:func:`~eleanor.output.postgres.persistence.repositories.bulk_load_window`
or :func:`~eleanor.output.postgres.persistence.schema.bulk_load_window`,
which package the same drop/recreate pair as a context manager so an
exception inside the workload still triggers the recreate.
"""

import click

from eleanor.cli.util import config_from_args, config_options
from eleanor.output.postgres.config import database_config_from_config
from eleanor.output.postgres.persistence.repositories import drop_indexes, recreate_indexes


@click.command()
@click.argument("action", type=click.Choice(["drop", "recreate"]))
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt for destructive actions.")
@config_options
def bulkload(action: str, yes: bool, config: str, database: str | None) -> None:
    """Drop or recreate secondary indexes + constraints around a bulk-load window."""
    cfg = config_from_args(config, database)
    database_config = database_config_from_config(cfg)
    if database_config.database is None:
        raise click.ClickException("no database provided")

    if action == "drop":
        if not yes:
            _ = click.confirm(
                f'This will drop all secondary indexes and constraints on "{database_config.database}". Continue?',
                abort=True,
            )
        drop_indexes(database_config)
    elif action == "recreate":
        recreate_indexes(database_config)
    else:
        raise ValueError(f"unknown bulkload action: {action!r}")
