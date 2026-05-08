import argparse
from typing import Callable, Protocol, cast

import eleanor.cli.postgres as postgres
import eleanor.cli.run as run


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
    _ = postgres.init(subparsers.add_parser("postgres"))

    args_ns = parser.parse_args()
    args = cast(CLIArgs, cast(object, args_ns))
    # Nested subcommands (e.g. ``eleanor postgres schema``) stash their
    # own parser in ``_command_parser`` so error-path ``print_help()``
    # shows the leaf command's usage, not the group's.
    _override = getattr(args_ns, "_command_parser", None)
    command_parser = (
        cast(argparse.ArgumentParser, cast(object, _override))
        if _override is not None
        else subparsers.choices[args.command]
    )
    return args.func(command_parser, args_ns)
