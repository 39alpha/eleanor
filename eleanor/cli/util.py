import argparse
import os.path
import sys
from typing import TypedDict

from xdg_base_dirs import xdg_config_home

from eleanor.config import Config, OutputRaw, load_config
from eleanor.exceptions import EleanorConfigurationException
from eleanor.output.postgres.config import DatabaseRaw, database_config_from_config
from eleanor.typing import cast


class ConfigArgs(TypedDict):
    """Argparse fields contributed by :func:`add_config_args`."""

    config: str
    database: str | None


def typed_args[T](schema: type[T], ns: argparse.Namespace) -> T:
    """Coerce an :class:`argparse.Namespace` to a ``TypedDict`` schema.

    pyright rejects a direct ``cast(schema, vars(ns))`` because
    ``dict[str, Any]`` doesn't structurally overlap a ``TypedDict``. Routing
    through ``object`` once here lets each CLI command describe its argparse
    namespace with a ``TypedDict`` subclass without repeating the widening
    cast at every call site.
    """
    _ = schema
    return cast(T, cast(object, vars(ns)))


def add_config_args(parser: argparse.ArgumentParser) -> None:
    try:
        config_path = str(xdg_config_home().joinpath("eleanor", "config.yaml"))
        _ = load_config(config_path)
    except Exception:
        config_path = None
    _ = parser.add_argument(
        "-c",
        "--config",
        required=config_path is None,
        type=str,
        default=config_path,
        help='the database configuration file to use (default: "%(default)s")',
    )
    _ = parser.add_argument(
        "-d",
        "--database",
        required=False,
        type=str,
        help="override the database from the configuration file (required if missing from config)",
    )


def config_from_args(
    parser: argparse.ArgumentParser,
    args: ConfigArgs,
    *,
    require_database: bool = True,
) -> Config:
    config_path = os.path.expanduser(args["config"])
    database = args["database"]

    config = load_config(config_path)
    if database is not None:
        if config.output.type != "postgres":
            raise EleanorConfigurationException(
                '--database is only supported when output.type == "postgres" ' + f'(got "{config.output.type}")'
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
    elif require_database and config.output.type == "postgres" and database_config_from_config(config).database is None:
        print("error: no database provided\n", file=sys.stdout)
        parser.print_help()
        sys.exit(1)

    return config
