#!/usr/bin/env python3

import argparse
import io
import os
import sys
from dataclasses import asdict
from zipfile import ZipFile

from eleanor.config import DatabaseConfig, load_config
from eleanor.variable_space import Point
from eleanor.yeoman import Yeoman, select


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump huffer results to a directory'

    parser.add_argument(
        '-c',
        '--config',
        required=False,
        type=str,
        default=os.path.expanduser('~/.config/eleanor/local.yaml'),
        help='the database configuration file to use',
    )
    parser.add_argument(
        '-d',
        '--database',
        required=False,
        type=str,
        help='override the database from the configuration file',
    )
    parser.add_argument(
        'vs_id',
        type=int,
        help='the variable space id for the huffer entry',
    )
    parser.add_argument(
        'outdir',
        type=str,
        nargs='?',
        help='path to the directory in which to extract the scratch files',
    )
    parser.set_defaults(func=execute)

    return parser


def execute(ns: argparse.Namespace):
    args = vars(ns)

    config_path = os.path.expanduser(args['config'])
    variable_space_id = args['vs_id']
    directory = args['outdir'] if args['outdir'] else '.'
    database = args['database']

    print(f'Loading {args["config"]}')
    config = load_config(config_path).database

    if database is not None:
        kwargs = asdict(config)
        kwargs.update({'database': database})
        config = DatabaseConfig(**kwargs)

    try:
        with Yeoman(config) as yeoman:
            result = yeoman.scalar(select(Point).where(Point.id == variable_space_id))
            if result is None:
                raise Exception(f'no variable space point found with id {variable_space_id}')

            print('Database:           ', config.database)
            print('Variable Space ID:  ', result.id)
            print('Exit Code:          ', result.exit_code)

            if result.scratch is None:
                raise Exception(f'no scratch found for variable space point')
            elif len(result.scratch.zip) == 0:
                raise Exception(f'no data in scratch zip')

            os.makedirs(directory, exist_ok=True)
            ZipFile(io.BytesIO(result.scratch.zip)).extractall(path=directory)
    except Exception as err:
        print(f'Failed to fetch the variable space scratch: {err}', file=sys.stderr)
        sys.exit(1)
