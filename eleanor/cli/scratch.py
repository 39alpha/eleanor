import argparse
import io
import os
import sys
from zipfile import ZipFile
from sqlalchemy import select

from eleanor.cli.util import ConfigArgs, add_config_args, config_from_args, typed_args
from eleanor.variable_space import Point
from eleanor.yeoman import Yeoman


class ScratchArgs(ConfigArgs):
    """Argparse fields accepted by the ``scratch`` command."""
    vs_id: int
    outdir: str


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump scratch results to a directory'

    _ = parser.add_argument('vs_id', type=int, help='the variable space id for the scratch entry')
    _ = parser.add_argument(
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


def execute(parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    args = typed_args(ScratchArgs, ns)

    variable_space_id = args['vs_id']
    directory = args['outdir']

    print(f"Loading {args['config']}")
    config = config_from_args(parser, args)

    try:
        with Yeoman(config.database) as yeoman:
            result = yeoman.scalar(select(Point).where(Point.__table__.c.id == variable_space_id))
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
