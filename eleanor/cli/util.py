"""Shared CLI utilities for built-in commands and CLI plugins.

This module is part of the supported CLI-plugin contract: third-party
plugins registered through ``eleanor.cli_commands`` may import
:func:`config_options` and :func:`config_from_args` to inherit the
``--config`` / ``--database`` flags and the standard config-resolution
behaviour. The names exported here are covered by the same plugin-API
versioning policy as the ``eleanor.cli_commands`` entry-point group.
"""

import functools
import os.path
from collections.abc import Callable

import click
from xdg_base_dirs import xdg_config_home

from eleanor.config import Config, load_config
from eleanor.exceptions import EleanorConfigurationException
from eleanor.output.config import ConfigRaw as OutputRaw
from eleanor.output.postgres.config import DatabaseRaw, database_config_from_config
from eleanor.typing import cast


def _default_config_path() -> str | None:
    try:
        path = str(xdg_config_home().joinpath("eleanor", "config.yaml"))
        _ = load_config(path)
        return path
    except Exception:
        return None


def config_options[F: Callable[..., object]](*, required: bool = True) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        default_path = _default_config_path()

        @click.option(
            "-c",
            "--config",
            required=required and default_path is None,
            default=default_path,
            envvar="ELEANOR_CONFIG",
            type=click.Path(dir_okay=False),
            help=f"Configuration file (default: {default_path or 'required'}).",
        )
        @click.option(
            "-d",
            "--database",
            required=False,
            default=None,
            envvar="ELEANOR_DATABASE",
            help="Override the database from the configuration file.",
        )
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            return fn(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


def config_from_args(
    config_file: str,
    database: str | None,
    *,
    require_database: bool = True,
) -> Config:
    config_path = os.path.expanduser(config_file)

    config = load_config(config_path)
    if database is not None:
        if config.output.kind != "postgres":
            cause = f'got "{config.output.kind}"' if config.output.kind is not None else "no output sink provided"
            raise EleanorConfigurationException(
                f'--database is only supported when output.kind == "postgres" ({cause})'
            )
        output_raw = config.raw.get("output", OutputRaw())
        args_raw_obj = output_raw.get("args")
        args_raw: dict[str, object] = (
            cast(dict[str, object], cast(object, args_raw_obj)) if isinstance(args_raw_obj, dict) else {}
        )
        database_raw_obj = args_raw.get("database")
        database_raw: DatabaseRaw = (
            cast(DatabaseRaw, cast(object, database_raw_obj)) if isinstance(database_raw_obj, dict) else DatabaseRaw()
        )
        database_raw["database"] = database
        args_raw["database"] = database_raw
        output_raw["args"] = args_raw
        config.raw["output"] = output_raw
        # Keep the parsed snapshot consistent so the registry's **args splat
        # sees the override.
        config.output.args = args_raw
    elif require_database and config.output.kind == "postgres" and database_config_from_config(config).database is None:
        raise click.ClickException("no database provided")

    return config
