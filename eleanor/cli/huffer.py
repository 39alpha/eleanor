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

def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        '-c',
        '--config',
        required=False,
        type=str,
        default=os.path.expanduser('~/.config/eleanor/local.yaml'),
        help='the database configuration file to use',
    )
    arg_parser.add_argument(
        '-d',
        '--database',
        required=False,
        type=str,
        help='override the database from the configuration file',
    )
    arg_parser.add_argument(
        'order id',
        type=int,
        help='the order id for the huffer entry',
    )
    arg_parser.add_argument(
        'output dir',
        type=str,
        nargs='?',
        help='path to the directory in which to extract the huffer files',
    )

    args = vars(arg_parser.parse_args())

    config_path = os.path.expanduser(args['config'])
    order_id = args['order id']
    directory = args['output dir'] if args['output dir'] else '.'
    database = args['database']

    print(f'Loading {args["config"]}')
    config = load_config(config_path).database

    if database is not None:
        kwargs = asdict(config)
        kwargs.update({'database': database})
        config = DatabaseConfig(**kwargs)

    try:
        with Yeoman(config) as yeoman:
            result = yeoman.scalar(
                select(HufferResult).where(HufferResult.id == order_id)
            )
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


if __name__ == '__main__':
    main()