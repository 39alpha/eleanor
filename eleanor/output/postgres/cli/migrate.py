from typing import LiteralString, cast

import click
import psycopg

import eleanor as _eleanor
from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.persistence import connection as _connection
from eleanor.output.postgres.persistence import migrations as _migrations
from eleanor.output.postgres.persistence import repositories
from eleanor.output.postgres.persistence import schema as _schema
from eleanor.output.postgres.settings import PostgresSinkSettings


@click.command()
@click.option("--dry-run", is_flag=True, help="List pending migrations; apply none.")
@click.option("--list", "list_all", is_flag=True, help="List every migration and its applied status.")
@click.option(
    "--stamp",
    type=click.INT,
    default=None,
    is_flag=False,
    flag_value=-1,
    help=(
        "Mark migrations as applied without running them. "
        "Bare flag stamps every declared migration; pass a version to stamp through that version."
    ),
)
@click.option("--verify", is_flag=True, help="Run the drift check; apply no migrations.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompts.")
@config_options()
def migrate(
    dry_run: bool,
    list_all: bool,
    stamp: int | None,
    verify: bool,
    yes: bool,
    config: str,
    database: str | None,
) -> None:
    """Apply pending postgres migrations."""
    settings = sole_postgres_settings(config_from_args(config, database), "migrate")
    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    exclusive_count = sum(int(x) for x in (verify, dry_run, list_all, stamp is not None))
    if exclusive_count > 1:
        msg = "--verify, --dry-run, --list, and --stamp are mutually exclusive"
        raise click.UsageError(msg)

    if verify:
        _cmd_verify(settings)
    elif list_all:
        _cmd_list(settings)
    elif dry_run:
        _cmd_dry_run(settings)
    elif stamp is not None:
        _cmd_stamp(settings, stamp, yes)
    else:
        _cmd_apply(settings)


def _cmd_verify(settings: PostgresSinkSettings) -> None:
    conn = _connection.connect(settings.database)
    problems = _schema.verify_against_tables(conn)
    if problems:
        for p in problems:
            click.echo(p)
        raise SystemExit(1)
    click.echo("schema is in sync")


def _cmd_list(settings: PostgresSinkSettings) -> None:
    declared = _migrations.discover()
    applied = _read_applied_versions(settings)
    for mig in declared:
        status = "applied" if mig.version in applied else "pending"
        click.echo(f"{mig.version:>4}  {mig.slug:<50}  {status}")


def _cmd_dry_run(settings: PostgresSinkSettings) -> None:
    declared = _migrations.discover()
    applied = _read_applied_versions(settings)
    pending = [m for m in declared if m.version not in applied]
    if not pending:
        click.echo("no pending migrations")
        return
    for mig in pending:
        click.echo(f"{mig.version:>4}  {mig.slug}")


_STAMP_SQL: LiteralString = _migrations.RECORD_SQL + " ON CONFLICT (version) DO NOTHING"


def _cmd_stamp(settings: PostgresSinkSettings, target: int, yes: bool) -> None:
    conn = _connection.connect(settings.database)
    problems = _schema.verify_against_tables(conn)
    if problems and not yes:
        for p in problems:
            click.echo(p)
        click.echo("Schema has drift. Pass --yes to stamp anyway.")
        raise SystemExit(1)

    declared = _migrations.discover()
    to_stamp = declared if target == -1 else tuple(m for m in declared if m.version <= target)

    _ensure_sql: LiteralString = cast(LiteralString, _schema.to_create_table_sql(_schema.SCHEMA_MIGRATIONS))
    with conn.transaction(), conn.cursor() as cur:
        _ = cur.execute(_ensure_sql)
        for mig in to_stamp:
            _ = cur.execute(_STAMP_SQL, (mig.version, mig.slug, _eleanor.__version__))
    click.echo(f"Stamped {len(to_stamp)} migration(s).")


def _cmd_apply(settings: PostgresSinkSettings) -> None:
    try:
        repositories.apply_pending_migrations(settings.database)
    except EleanorError as exc:
        raise click.ClickException(str(exc)) from exc


def _read_applied_versions(settings: PostgresSinkSettings) -> set[int]:
    conn = _connection.connect(settings.database)
    try:
        with conn.transaction(), conn.cursor() as cur:
            _ = cur.execute("SELECT version FROM schema_migrations")
            return {cast(int, row[0]) for row in cur.fetchall()}
    except psycopg.errors.UndefinedTable:
        return set()


__all__ = ["migrate"]
