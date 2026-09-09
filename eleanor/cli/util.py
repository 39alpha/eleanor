"""Shared CLI utilities for built-in commands and CLI plugins.

This module is part of the supported CLI-plugin contract: third-party
plugins registered through ``eleanor.cli_commands`` may import
:func:`config_options` and :func:`config_from_args` to inherit the
``--config`` / ``--database`` flags and the standard config-resolution
behaviour. The names exported here are covered by the same plugin-API
versioning policy as the ``eleanor.cli_commands`` entry-point group.
"""

import functools
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import click
from xdg_base_dirs import xdg_config_home

from eleanor.config import Config, load_config
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.settings import PostgresSinkSettings
from eleanor.typing import StrPath


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


def postgres_sinks(config: Config) -> list[OutputSinkConfig]:
    """Return every configured Postgres sink entry, in configuration order.

    A run may drive several sinks of mixed kinds, so a command that only makes
    sense against PostgreSQL has to pick its own out rather than assume the
    sole configured sink is one.
    """
    return [entry for entry in config.output if isinstance(entry.settings, PostgresSinkSettings)]


def sole_postgres_settings(config: Config, action: str) -> PostgresSinkSettings:
    """Return the only configured Postgres sink's settings, or explain why not.

    Commands that act on a database as a whole -- dumping its schema,
    migrating it, recreating its bulk-load objects -- have no defensible
    behaviour when two are configured, so ambiguity is an error naming the
    candidates rather than a silent pick of the first.

    :param action: What the caller is trying to do, used in the error message.
    """
    candidates = postgres_sinks(config)
    if not candidates:
        if not config.output:
            msg = "no output sink configured"
        else:
            kinds = ", ".join(sorted({entry.kind for entry in config.output}))
            msg = f"cannot {action} for a non-postgres output sink (configured: {kinds})"
        raise EleanorError(msg)

    if len(candidates) > 1:
        names = ", ".join(entry.name for entry in candidates)
        msg = f"cannot {action}: several postgres output sinks are configured ({names})"
        raise EleanorError(msg)

    settings = candidates[0].settings
    if not isinstance(settings, PostgresSinkSettings):  # pragma: no cover - filtered above
        msg = f"cannot {action} for a non-postgres output sink"
        raise EleanorError(msg)
    return settings


def config_from_args(
    config_file: StrPath,
    database: str | None,
    *,
    require_database: bool = True,
) -> Config:
    """Load a config file and apply the shared ``--database`` override.

    ``--database`` names one database, so it is only meaningful when exactly
    one Postgres sink is configured; with two it would be ambiguous which one
    the caller meant to redirect. ``require_database`` likewise checks every
    Postgres sink, so a run cannot get halfway in before the second sink turns
    out to have no database to write to.
    """
    config_path = Path(config_file).expanduser()

    config = load_config(config_path)
    if database is not None:
        candidates = postgres_sinks(config)
        if not candidates:
            if not config.output:
                msg = "no output sink configuration provided"
            else:
                kinds = ", ".join(sorted({entry.kind for entry in config.output}))
                msg = f"--database is only supported by the postgres output sink, got {kinds}"
            raise EleanorError(msg)
        if len(candidates) > 1:
            names = ", ".join(entry.name for entry in candidates)
            msg = f"--database is ambiguous: several postgres output sinks are configured ({names})"
            raise EleanorError(msg)

        entry = candidates[0]
        settings = entry.settings
        assert isinstance(settings, PostgresSinkSettings)
        entry.settings = replace(
            settings,
            database=replace(settings.database, database=database),
        )
    elif require_database:
        undatabased = [
            entry.name
            for entry in postgres_sinks(config)
            if cast(PostgresSinkSettings, entry.settings).database.database is None
        ]
        if undatabased:
            msg = f"no database provided for output sink(s): {', '.join(undatabased)}"
            raise click.ClickException(msg)

    return config
