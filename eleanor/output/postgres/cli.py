import io
from pathlib import Path
from typing import LiteralString, TextIO, cast
from zipfile import ZipFile

import click
import psycopg

import eleanor as _eleanor
from eleanor.cli.util import config_from_args, config_options
from eleanor.exceptions import EleanorException
from eleanor.output.postgres.persistence import connection as _connection
from eleanor.output.postgres.persistence import migrations as _migrations
from eleanor.output.postgres.persistence import repositories
from eleanor.output.postgres.persistence import schema as _schema
from eleanor.output.postgres.persistence.repositories import drop_indexes, recreate_indexes
from eleanor.output.postgres.settings import PostgresSinkSettings
from eleanor.output.postgres.tools import dump_schema, load_scratch_entry


@click.command()
@click.option("-o", "--output", type=click.File("w"), default="-", help="Output file (default: stdout).")
@config_options()
def schema(output: TextIO, config: str, database: str | None) -> None:
    """Dump an Eleanor database schema.

    Dumps the cumulative target schema. **Do not pipe this into psql to
    bootstrap a new database** — use ``eleanor postgres migrate``
    instead, so the tracking table is populated. Use this command for
    documentation or for capturing the body of a new migration file.
    """

    cfg = config_from_args(config, database).output
    if cfg is None:
        msg = "no output sink configured"
        raise EleanorException(msg)

    settings = cfg.settings
    if not isinstance(settings, PostgresSinkSettings):
        msg = "cannot dump postgres schema for a non-postgres output sink"
        raise EleanorException(msg)

    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    dump_schema(settings.database, output)


@click.command()
@click.argument("vs_id", type=click.INT)
@click.option("-o", "--outdir", type=click.Path(file_okay=False), default=".", help="Output directory.")
@config_options()
def scratch(vs_id: int, outdir: str, config: str, database: str | None) -> None:
    """Dump scratch results to a directory."""

    variable_space_id = vs_id
    directory = Path(outdir)

    print(f"Loading {config}")
    cfg = config_from_args(config, database).output
    if cfg is None:
        msg = "no output sink configured"
        raise EleanorException(msg)

    settings = cfg.settings

    if not isinstance(settings, PostgresSinkSettings):
        msg = "cannot dump scratch from a non-postgres output sink"
        raise EleanorException(msg)

    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    try:
        try:
            result = load_scratch_entry(settings.database, variable_space_id)
        except LookupError as missing:
            if str(missing) == "scratch":
                msg = "no scratch found for variable space point"
                raise click.ClickException(msg) from missing
            raise
        if result is None:
            msg = f"no variable space point found with id {variable_space_id}"
            raise click.ClickException(msg)

        print("Database:           ", settings.database.database)
        print("Variable Space ID:  ", result.variable_space_id)
        print("Exit Code:          ", result.exit_code)

        if len(result.zip) == 0:
            msg = "no data in scratch zip"
            raise click.ClickException(msg)

        directory.mkdir(parents=True, exist_ok=True)
        ZipFile(io.BytesIO(result.zip)).extractall(path=directory)
    except click.ClickException:
        raise
    except Exception as err:
        click.echo(f"Failed to fetch the variable space scratch: {err}", err=True)
        raise SystemExit(1) from err


@click.command()
@click.argument("action", type=click.Choice(["drop", "recreate"]))
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt for destructive actions.")
@config_options()
def bulkload(action: str, yes: bool, config: str, database: str | None) -> None:
    """Drop or recreate secondary indexes + constraints around a bulk-load window."""
    cfg = config_from_args(config, database).output
    if cfg is None:
        msg = "no output sink configured"
        raise EleanorException(msg)

    settings = cfg.settings

    if not isinstance(settings, PostgresSinkSettings):
        msg = f"cannot {action} secondary indexes and constraints on a non-postgres output sink"
        raise EleanorException(msg)

    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    if action == "drop":
        if not yes:
            _ = click.confirm(
                f'This will drop all secondary indexes and constraints on "{settings.database.database}". Continue?',
                abort=True,
            )
        drop_indexes(settings.database)
    elif action == "recreate":
        recreate_indexes(settings.database)
    else:
        msg = f"unknown bulkload action: {action!r}"
        raise EleanorException(msg)


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
    cfg = config_from_args(config, database).output
    if cfg is None:
        msg = "no output sink configured"
        raise EleanorException(msg)
    settings = cfg.settings
    if not isinstance(settings, PostgresSinkSettings):
        msg = "cannot migrate a non-postgres output sink"
        raise EleanorException(msg)
    if settings.database.database is None:
        msg = "no database provided"
        raise click.ClickException(msg)

    exclusive_count = sum(bool(x) for x in (verify, dry_run, list_all, stamp is not None))
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
    except EleanorException as exc:
        raise click.ClickException(str(exc)) from exc


def _read_applied_versions(settings: PostgresSinkSettings) -> set[int]:
    conn = _connection.connect(settings.database)
    try:
        with conn.transaction(), conn.cursor() as cur:
            _ = cur.execute("SELECT version FROM schema_migrations")
            return {cast(int, row[0]) for row in cur.fetchall()}
    except psycopg.errors.UndefinedTable:
        return set()


__all__ = ["bulkload", "migrate", "schema", "scratch"]
