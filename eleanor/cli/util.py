import argparse
import os.path
import sys
from typing import TypedDict

from xdg_base_dirs import xdg_config_home

from eleanor.config import Config, DatabaseConfig, DatabaseRaw, load_config
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
        config_path = str(xdg_config_home().joinpath('eleanor', 'config.yaml'))
        _ = load_config(config_path)
    except Exception:
        config_path = None
    _ = parser.add_argument(
        '-c',
        '--config',
        required=config_path is None,
        type=str,
        default=config_path,
        help='the database configuration file to use (default: "%(default)s")',
    )
    _ = parser.add_argument(
        '-d',
        '--database',
        required=False,
        type=str,
        help='override the database from the configuration file (required if missing from config)',
    )


def config_from_args(parser: argparse.ArgumentParser, args: ConfigArgs) -> Config:
    config_path = os.path.expanduser(args['config'])
    database = args['database']

    config = load_config(config_path)
    if database is not None:
        raw_database = config.raw.get('database', DatabaseRaw())
        raw_database['database'] = database
        config.raw['database'] = raw_database
        config.database = DatabaseConfig.from_raw(raw_database)
    elif config.database.database is None:
        print('error: no database provided\n', file=sys.stdout)
        parser.print_help()
        sys.exit(1)

    return config
