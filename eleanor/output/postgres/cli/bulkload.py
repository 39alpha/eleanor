import click

from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.persistence import schema as _schema
from eleanor.output.postgres.persistence.repositories import drop_bulk_load_objects, recreate_bulk_load_objects


@click.command()
@click.argument("action", type=click.Choice(["drop", "recreate"]))
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt for destructive actions.")
@click.option("--indexes/--no-indexes", default=True, help="Include secondary indexes (default: on).")
@click.option("--fks/--no-fks", "foreign_keys", default=True, help="Include foreign-key constraints (default: on).")
@click.option("--checks/--no-checks", default=True, help="Include CHECK constraints (default: on).")
@config_options()
def bulkload(
    action: str,
    yes: bool,
    indexes: bool,
    foreign_keys: bool,
    checks: bool,
    config: str,
    database: str | None,
) -> None:
    """Drop or recreate secondary indexes / FK / CHECK constraints around a bulk-load window.

    By default all three object classes are affected. Restrict the operation with
    --no-indexes / --no-fks / --no-checks; give ``drop`` and ``recreate`` the same
    selection so the round-trip is symmetric.
    """
    settings = sole_postgres_settings(
        config_from_args(config, database),
        f"{action} secondary indexes and constraints",
    )

    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    targets = _schema.BulkLoadTargets(indexes=indexes, checks=checks, foreign_keys=foreign_keys)
    if not targets:
        msg = "nothing selected: pass at least one of --indexes / --fks / --checks"
        raise click.UsageError(msg)

    selected = ", ".join(
        label
        for label, on in (("indexes", indexes), ("foreign keys", foreign_keys), ("CHECK constraints", checks))
        if on
    )

    if action == "drop":
        if not yes:
            _ = click.confirm(
                f"This will drop the following on {settings.database.database!r}: {selected}. Continue?",
                abort=True,
            )
        drop_bulk_load_objects(settings.database, targets)
    elif action == "recreate":
        recreate_bulk_load_objects(settings.database, targets)
    else:
        msg = f"unknown bulkload action: {action!r}"
        raise EleanorError(msg)


__all__ = ["bulkload"]
