import argparse
from typing import Callable, Protocol, cast

import eleanor.cli.bulkload as bulkload
import eleanor.cli.doctor as doctor
import eleanor.cli.gen as gen
import eleanor.cli.run as run
import eleanor.cli.schema as schema
import eleanor.cli.scratch as scratch


class CLIArgs(Protocol):
    command: str
    func: Callable[[argparse.ArgumentParser, argparse.Namespace], object]


def main() -> object:
    parser = argparse.ArgumentParser(
        prog="eleanor",
        description="Run eleanor or interact with a generated dataset",
        allow_abbrev=True,
    )

    subparsers = parser.add_subparsers(required=True, dest="command")

    _ = run.init(subparsers.add_parser("run"))
    _ = schema.init(subparsers.add_parser("schema"))
    _ = scratch.init(subparsers.add_parser("scratch"))
    _ = bulkload.init(subparsers.add_parser("bulkload"))
    _ = doctor.init(subparsers.add_parser("doctor"))
    _ = gen.init(subparsers.add_parser("gen"))

    args_ns = parser.parse_args()
    args = cast(CLIArgs, cast(object, args_ns))
    command_parser = subparsers.choices[args.command]
    return args.func(command_parser, args_ns)
