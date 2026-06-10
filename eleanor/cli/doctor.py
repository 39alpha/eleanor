import sys
from typing import TYPE_CHECKING, cast

import click

import eleanor
from eleanor.cli.registry import available_cli_commands
from eleanor.cli.util import config_from_args, config_options
from eleanor.exceptions import EleanorError
from eleanor.executor.registry import available_executors
from eleanor.kernel.registry import available_kernels
from eleanor.navigator.registry import available_navigators
from eleanor.output.registry import available_output_sinks
from eleanor.plugin import PLUGIN_API_VERSIONS

if TYPE_CHECKING:
    from eleanor.output.postgres.settings import PostgresSinkSettings


@click.command()
@config_options(required=False)
def doctor(config: str | None, database: str | None) -> None:
    """Print diagnostic information about this eleanor installation."""
    click.echo()
    click.echo(f"  {click.style('eleanor', bold=True)} {click.style(eleanor.__version__, fg='green')}")
    click.echo(f"  {click.style('Python', dim=True)}  {click.style(sys.version.split(chr(10))[0], dim=True)}")
    click.echo()

    click.echo(f"  {click.style('Plugin API versions', bold=True)}")
    for kind in sorted(PLUGIN_API_VERSIONS):
        current, floor = PLUGIN_API_VERSIONS[kind]
        label = f"  {kind:12s}"
        versions = f"v{current} {click.style('(min v' + str(floor) + ')', dim=True)}"
        click.echo(f"  {label}  {versions}")
    click.echo()

    sections = [
        ("Executors", sorted(available_executors())),
        ("Kernels", sorted(available_kernels())),
        ("Navigators", sorted(available_navigators())),
        ("Outputs", sorted(available_output_sinks())),
        ("CLI commands", sorted(available_cli_commands())),
    ]
    for heading, names in sections:
        click.echo(f"  {click.style(heading, bold=True)}")
        for name in names:
            click.echo(f"    {click.style('•', fg='green')} {name}")
        if not names:
            click.echo(f"    {click.style('(none)', dim=True)}")
    click.echo()

    cfg_obj = None
    try:
        cfg_obj = config_from_args(config, database, require_database=False) if config else None
    except EleanorError:
        cfg_obj = None

    if cfg_obj is not None and cfg_obj.output is not None:
        from eleanor.output.postgres.settings import PostgresSinkSettings

        settings = cfg_obj.output.settings
        if isinstance(settings, PostgresSinkSettings) and settings.database.database is not None:
            _print_postgres_health(settings)


def _print_postgres_health(settings: PostgresSinkSettings) -> None:
    from eleanor.output.postgres.persistence import connection, migrations, schema

    try:
        conn = connection.connect(settings.database)
    except Exception as exc:
        click.echo(f"  {click.style('postgres', bold=True)}")
        click.echo(f"    {click.style('connection failed:', fg='red')} {exc}")
        return

    click.echo(f"  {click.style('postgres', bold=True)}")
    click.echo(f"    database: {click.style(settings.database.database or '(none)', fg='green')}")

    with conn.cursor() as cur:
        _ = cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
        row = cur.fetchone()
    tracking_exists = cast(bool, row[0]) if row is not None else False

    if not tracking_exists:
        msg = f"    {click.style('tracking table missing', fg='yellow')} (database has not been migrated)"
        click.echo(msg)
        with conn.cursor() as cur:
            _ = cur.execute("SELECT to_regclass('public.orders') IS NOT NULL")
            row = cur.fetchone()
        orders_exist = cast(bool, row[0]) if row is not None else False
        if orders_exist:
            warning = f"    {click.style('warning:', fg='yellow')} untracked database — run `eleanor postgres migrate --stamp` if the schema matches the current target, otherwise recreate it (in-place upgrade from older schemas is unsupported)"
            click.echo(warning)
        return

    with conn.cursor() as cur:
        _ = cur.execute("SELECT MAX(version) FROM schema_migrations")
        row = cur.fetchone()
    max_applied: int | None = cast("int | None", row[0]) if row is not None else None

    declared = migrations.discover()
    if declared:
        latest_declared = declared[-1].version
        if max_applied is None:
            click.echo(f"    {click.style('applied:', dim=True)} none")
        else:
            click.echo(f"    {click.style('applied:', dim=True)} v{max_applied}")
        pending_count = sum(1 for m in declared if max_applied is None or m.version > max_applied)
        if pending_count > 0:
            pending_versions = [str(m.version) for m in declared if max_applied is None or m.version > max_applied]
            click.echo(
                f"    {click.style('pending:', fg='yellow')} {pending_count} migration(s): {', '.join(pending_versions)}",
            )
        else:
            click.echo(f"    {click.style('migrations up to date', fg='green')} (v{latest_declared})")

        if max_applied is None and declared:
            with conn.cursor() as cur:
                _ = cur.execute("SELECT to_regclass('public.orders') IS NOT NULL")
                row = cur.fetchone()
            orders_exist = cast(bool, row[0]) if row is not None else False
            if orders_exist:
                warning = f"    {click.style('warning:', fg='yellow')} untracked database — run `eleanor postgres migrate --stamp` if the schema matches the current target, otherwise recreate it (in-place upgrade from older schemas is unsupported)"
                click.echo(warning)

    problems = schema.verify_against_tables(conn)
    if problems:
        for p in problems:
            click.echo(f"    {click.style('drift:', fg='yellow')} {p}")
    else:
        click.echo(f"    {click.style('schema matches TABLES', fg='green')}")
