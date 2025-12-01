#!/usr/bin/env python3

import argparse
import io
import os
import sys
from dataclasses import asdict
from zipfile import ZipFile

from eleanor.config import DatabaseConfig, load_config
from eleanor.order import HufferResult
from eleanor.yeoman import Yeoman, select


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump scratch results to a directory'

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
        'order_id',
        type=int,
        help='the order id for the huffer entry',
    )
    parser.add_argument(
        'outdir',
        type=str,
        nargs='?',
        help='path to the directory in which to extract the huffer files',
    )
    parser.set_defaults(func=execute)

    return parser


def execute(ns: argparse.Namespace):
    args = vars(ns)

    config_path = os.path.expanduser(args['config'])
    order_id = args['order_id']
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
            result = yeoman.scalar(select(HufferResult).where(HufferResult.id == order_id))
            if result is None:
                raise Exception('no huffer result found')

            print('Database:  ', config.database)
            print('Order ID:  ', result.id)
            print('Exit Code: ', result.exit_code)

            if len(result.zip) == 0:
                raise Exception(f'no data in huffer zip')

            os.makedirs(directory, exist_ok=True)
            ZipFile(io.BytesIO(result.zip)).extractall(path=directory)
    except Exception as err:
        print(f'Failed to fetch the huffer results: {err}', file=sys.stderr)
        sys.exit(1)
