import io
from pathlib import Path
from zipfile import ZipFile

import click

from eleanor.cli.util import config_from_args, config_options, sole_postgres_settings
from eleanor.output.postgres.tools import load_scratch_entry
from eleanor.util import require_uuid_id


@click.command(name="scratch")
@click.argument("vs_id", type=click.STRING)
@click.option("-o", "--outdir", type=click.Path(file_okay=False), default=".", help="Output directory.")
@config_options(required=False)
def dump_scratch(vs_id: str, outdir: str, config: Path | None, database: str | None) -> None:
    """Dump scratch results to a directory."""

    variable_space_id = require_uuid_id(vs_id, "postgres sink")
    directory = Path(outdir)

    if config is not None:
        click.echo(f"Loading {config}")

    settings = sole_postgres_settings(
        config_from_args(config, database, assume_default_postgres=True),
        "dump scratch",
    )

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

        click.echo(f"Database:           {settings.database.database}")
        click.echo(f"Variable Space ID:  {result.variable_space_id}")
        click.echo(f"Exit Code:          {result.exit_code}")

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


__all__ = ["dump_scratch"]
