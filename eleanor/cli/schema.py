import argparse
import sys

from sqlalchemy import create_mock_engine

from eleanor.config import load_config
from eleanor.kernel.discover import import_all_kernels
from eleanor.yeoman import yeoman_registry


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = 'Dump an Eleanor database schema'

    parser.add_argument("-c", "--config", required=True, type=str, help="path to the configuration file")
    parser.add_argument("-o", "--output", required=False, type=str, help="file to which to write the schema")
    parser.set_defaults(func=execute)

    return parser


def execute(ns: argparse.Namespace):
    args = vars(ns)

    import_all_kernels()

    config = load_config(args["config"])
    if args['output'] is None:
        file = sys.stdout
    else:
        file = open(args["output"], 'w')

    def dump(sql, *multiparams, **params):
        print(sql.compile(dialect=engine.dialect), file=file)

    with file:
        engine = create_mock_engine(str(config.database), dump)
        yeoman_registry.metadata.create_all(engine)
