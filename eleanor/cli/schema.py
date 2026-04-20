import argparse
import sys
from typing import Protocol

from sqlalchemy import create_mock_engine

from eleanor.cli.util import ConfigArgs, add_config_args, config_from_args, typed_args
from eleanor.kernel.discover import import_all_kernels
from eleanor.yeoman import yeoman_registry


class SchemaArgs(ConfigArgs):
    """Argparse fields accepted by the ``schema`` command."""
    output: str | None


class _Compilable(Protocol):
    def compile(self) -> object:
        ...


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump an Eleanor database schema'

    _ = parser.add_argument(
        "-o",
        "--output",
        required=False,
        type=str,
        help='file to which to write the schema (default: STDOUT)',
    )

    add_config_args(parser)

    parser.set_defaults(func=execute)

    return parser


def execute(parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    args = typed_args(SchemaArgs, ns)

    _ = import_all_kernels()

    config = config_from_args(parser, args)

    output = args['output']
    if output is None:
        stream = sys.stdout
    else:
        stream = open(output, 'w')

    def dump(sql: _Compilable, *_multiparams: object, **_params: object) -> None:
        print(sql.compile(), file=stream)

    with stream:
        engine = create_mock_engine(str(config.database), dump)
        yeoman_registry.metadata.create_all(engine)
