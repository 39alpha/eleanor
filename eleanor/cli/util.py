import argparse
import os.path
import sys

from xdg_base_dirs import xdg_config_home

from eleanor.config import Config, DatabaseConfig, load_config
from eleanor.typing import Any


def add_config_args(parser: argparse.ArgumentParser):
    try:
        config_path = str(xdg_config_home().joinpath('eleanor', 'config.yaml'))
        config = load_config(config_path)
    except Exception:
        config_path = None

    parser.add_argument(
        '-c',
        '--config',
        required=config_path is None,
        type=str,
        default=config_path,
        help='the database configuration file to use (default: "%(default)s")',
    )
    parser.add_argument(
        '-d',
        '--database',
        required=False,
        type=str,
        help='override the database from the configuration file (required if missing from config)',
    )


def config_from_args(parser: argparse.ArgumentParser, args: dict[str, Any]) -> Config:
    config_path = os.path.expanduser(str(args['config']))
    database = args['database']

    config = load_config(config_path)
    if database is not None:
        config.raw['database'].update({'database': database})
        config.database = DatabaseConfig(**config.raw['database'])
    elif config.database.database is None:
        print('error: no database provided\n', file=sys.stdout)
        parser.print_help()
        sys.exit(1)

    return config
