import io
import os
from zipfile import ZipFile

import click

from eleanor.cli.util import config_from_args, config_options
from eleanor.output.postgres.config import database_config_from_config
from eleanor.output.postgres.tools import load_scratch_entry


@click.command()
@click.argument("vs_id", type=click.INT)
@click.option("-o", "--outdir", type=click.Path(file_okay=False), default=".", help="Output directory.")
@config_options
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
