import argparse
import io
import os
import sys
from dataclasses import asdict
from zipfile import ZipFile

from eleanor.cli.util import add_config_args, config_from_args
from eleanor.order import HufferResult
from eleanor.yeoman import Yeoman, select


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump scratch results to a directory'

    parser.add_argument(
        'order_id',
        type=int,
        help='the order id for the huffer entry',
    )
    parser.add_argument(
        '-o',
        '--outdir',
        required=False,
        type=str,
        default='.',
        help='path to the directory in which to extract the scratch files (default: "%(default)s")',
    )

    add_config_args(parser)

    parser.set_defaults(func=execute)

    return parser


def execute(parser: argparse.ArgumentParser, ns: argparse.Namespace):
    args = vars(ns)

    config_path = os.path.expanduser(str(args['config']))
    order_id = args['order_id']
    directory = args['outdir']
    database = args['database']

    print(f'Loading {args["config"]}')
    config = config_from_args(parser, args)

    try:
        with Yeoman(config.database) as yeoman:
            result = yeoman.scalar(select(HufferResult).where(HufferResult.id == order_id))
            if result is None:
                raise Exception('no huffer result found')

            print('Database:  ', config.database.database)
            print('Order ID:  ', result.id)
            print('Exit Code: ', result.exit_code)

            if len(result.zip) == 0:
                raise Exception(f'no data in huffer zip')

            os.makedirs(directory, exist_ok=True)
            ZipFile(io.BytesIO(result.zip)).extractall(path=directory)
    except Exception as err:
        print(f'Failed to fetch the huffer results: {err}', file=sys.stderr)
        sys.exit(1)
