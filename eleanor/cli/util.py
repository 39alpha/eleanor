import argparse
import os.path

from xdg_base_dirs import xdg_config_home

from eleanor.config import Config, DatabaseConfig, load_config
from eleanor.typing import Any


def add_config_args(parser: argparse.ArgumentParser):
    try:
        config_path = str(xdg_config_home().joinpath('eleanor', 'config.yaml'))
        config = load_config(config_path)
        database = config.database.database
    except Exception:
        config_path = None
        database = None

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
        required=database is None,
        type=str,
        default=database,
        help='override the database from the configuration file (default: "%(default)s")',
    )


def config_from_args(args: dict[str, Any]) -> Config:
    config_path = os.path.expanduser(str(args['config']))
    database = args['database']

    config = load_config(config_path)
    if database is not None:
        config.raw['database'].update({'database': database})
        config.database = DatabaseConfig(**config.raw['database'])

    return config
