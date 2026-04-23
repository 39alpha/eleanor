import argparse
import sys

from eleanor.cli.util import ConfigArgs, add_config_args, config_from_args, typed_args
from eleanor.output.postgres.tools import dump_schema


class SchemaArgs(ConfigArgs):
    """Argparse fields accepted by the ``schema`` command."""
    output: str | None


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump an Eleanor database schema'

    _ = parser.add_argument(
        '-o',
        '--output',
        required=False,
        type=str,
        help='file to which to write the schema (default: STDOUT)',
    )

    add_config_args(parser)

    parser.set_defaults(func=execute)

    return parser


def execute(parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    args = typed_args(SchemaArgs, ns)

    config = config_from_args(parser, args)
    if config.database.database is None:
        print('error: no database provided\n', file=sys.stdout)
        parser.print_help()
        sys.exit(1)

    output = args['output']
    if output is None:
        stream = sys.stdout
    else:
        stream = open(output, 'w')

    with stream:
        dump_schema(config.database, stream)
