import argparse
import io
import os
import sys
from dataclasses import asdict
from zipfile import ZipFile

from eleanor.cli.util import add_config_args, config_from_args
from eleanor.variable_space import Point
from eleanor.yeoman import Yeoman, select


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump huffer results to a directory'

    parser.add_argument('vs_id', type=int, help='the variable space id for the huffer entry')
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


def execute(ns: argparse.Namespace):
    args = vars(ns)

    variable_space_id = args['vs_id']
    directory = args['outdir']
    database = args['database']

    print(f'Loading {args["config"]}')
    config = config_from_args(args)

    try:
        with Yeoman(config.database) as yeoman:
            result = yeoman.scalar(select(Point).where(Point.id == variable_space_id))
            if result is None:
                raise Exception(f'no variable space point found with id {variable_space_id}')

            print('Database:           ', config.database.database)
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
