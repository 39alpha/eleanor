import argparse
from typing import Callable, Protocol, cast

import eleanor.cli.huffer as huffer
import eleanor.cli.run as run
import eleanor.cli.schema as schema
import eleanor.cli.scratch as scratch


class CLIArgs(Protocol):
    command: str
    func: Callable[[argparse.ArgumentParser, argparse.Namespace], object]


def main() -> object:
    parser = argparse.ArgumentParser(
        prog='eleanor',
        description='Run eleanor or interact with a generated dataset',
        allow_abbrev=True,
    )

    subparsers = parser.add_subparsers(required=True, dest='command')

    _ = huffer.init(subparsers.add_parser('huffer'))
    _ = run.init(subparsers.add_parser('run'))
    _ = schema.init(subparsers.add_parser('schema'))
    _ = scratch.init(subparsers.add_parser('scratch'))

    args_ns = parser.parse_args()
    args = cast(CLIArgs, cast(object, args_ns))
    command_parser = subparsers.choices[args.command]
    return args.func(command_parser, args_ns)
