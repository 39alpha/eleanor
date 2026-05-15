"""Click commands contributed by the postgres output sink.

Wired into the top-level CLI as ``eleanor postgres <subcommand>`` via the
:class:`~eleanor.cli.registry.CliCommandSpec` registered by
:mod:`eleanor.output`.
"""

import io
import os
from typing import TextIO
from zipfile import ZipFile

import click

from eleanor.cli.util import config_from_args, config_options

from .config import database_config_from_config
from .persistence.repositories import drop_indexes, recreate_indexes
from .tools import dump_schema, load_scratch_entry


@click.command()
@click.option("-o", "--output", type=click.File("w"), default="-", help="Output file (default: stdout).")
@config_options()
def schema(output: TextIO, config: str, database: str | None) -> None:
    """Dump an Eleanor database schema."""
    cfg = config_from_args(config, database)
    database_config = database_config_from_config(cfg)
    if database_config.database is None:
        raise click.ClickException("no database provided")
    dump_schema(database_config, output)


@click.command()
@click.argument("vs_id", type=click.INT)
@click.option("-o", "--outdir", type=click.Path(file_okay=False), default=".", help="Output directory.")
@config_options()
def scratch(vs_id: int, outdir: str, config: str, database: str | None) -> None:
    """Dump scratch results to a directory."""
    variable_space_id = vs_id
    directory = outdir

    print(f"Loading {config}")
    cfg = config_from_args(config, database)
    database_config = database_config_from_config(cfg)
    if database_config.database is None:
        raise click.ClickException("no database provided")

    try:
        try:
            result = load_scratch_entry(database_config, variable_space_id)
        except LookupError as missing:
            if str(missing) == "scratch":
                raise click.ClickException("no scratch found for variable space point") from missing
            raise
        if result is None:
            raise click.ClickException(f"no variable space point found with id {variable_space_id}")

        print("Database:           ", database_config.database)
        print("Variable Space ID:  ", result.variable_space_id)
        print("Exit Code:          ", result.exit_code)

        if len(result.zip) == 0:
            raise click.ClickException("no data in scratch zip")

        os.makedirs(directory, exist_ok=True)
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
