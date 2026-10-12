"""Shared CLI utilities for built-in commands and CLI plugins."""

import functools
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from traceback import print_exception
from typing import Never, cast

import click
from xdg_base_dirs import xdg_config_home

from eleanor.config import Config, load_config
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorError
from eleanor.output.postgres.settings import PostgresDatabaseSettings, PostgresSinkSettings
from eleanor.typing import StrPath
from eleanor.util import first_line


def _default_config_path() -> Path:
    return xdg_config_home().joinpath("eleanor", "config.yaml")


def require_config(config: Path | None) -> Path:
    if config is None:
        msg = f"configuration is required; pass -c/--config or set up {_default_config_path()}"
        raise click.ClickException(msg)
    return config


def config_options[F: Callable[..., object]](*, required: bool = True) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        default_path = _default_config_path()

        @click.option(
            "-c",
            "--config",
            default=default_path if default_path.is_file() else None,
            envvar="ELEANOR_CONFIG",
            type=click.Path(dir_okay=False, path_type=Path),
            show_default=True,
            help="Configuration file.",
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
            if required:
                kwargs["config"] = require_config(cast(Path | None, kwargs["config"]))
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
    config_file: StrPath | None,
    database: str | None,
    *,
    assume_default_postgres: bool = False,
    require_database: bool = True,
) -> Config:
    """Load a config file and apply the shared ``--database`` override.

    ``--database`` names one database, so it is only meaningful when exactly
    one Postgres sink is configured; with two it would be ambiguous which one
    the caller meant to redirect. ``require_database`` likewise checks every
    Postgres sink, so a run cannot get halfway in before the second sink turns
    out to have no database to write to.
    """
    if config_file is None:
        config = Config()
    else:
        config_path = Path(config_file).expanduser()
        config = load_config(config_path)

    candidates = postgres_sinks(config)

    if assume_default_postgres and not candidates:
        postgres_sink_config = OutputSinkConfig(
            kind="postgres",
            settings=PostgresSinkSettings(database=PostgresDatabaseSettings()),
        )
        config.output.append(postgres_sink_config)
        candidates.append(postgres_sink_config)

    if database is not None:
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
            entry.name for entry in candidates if cast(PostgresSinkSettings, entry.settings).database.database is None
        ]
        if undatabased:
            msg = f"no database provided for output sink(s): {', '.join(undatabased)}; pass -d/--database or provide it via config"
            raise click.ClickException(msg)

    return config


def _record_verbose(ctx: click.Context, _param: click.Parameter, value: bool) -> bool:
    if value:
        ctx.meta["eleanor.verbose"] = True
    return value


def show_verbose_output() -> bool:
    ctx = click.get_current_context(silent=True)
    return ctx is not None and bool(ctx.meta.get("eleanor.verbose", False))


def handle_exception(exception: Exception, base_msg: str | None = None, *, verbose: bool | None = None) -> Never:
    if isinstance(exception, (click.Abort, click.ClickException, click.exceptions.Exit)):
        raise exception

    if verbose or (verbose is None and show_verbose_output()):
        print_exception(exception)
        sys.exit(1)

    detail = first_line(str(exception)) or type(exception).__name__
    msg = f"{base_msg} - {detail}" if base_msg else f"{detail}"
    raise click.ClickException(msg) from exception
