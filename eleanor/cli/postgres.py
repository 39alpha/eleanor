"""``eleanor postgres`` -- Postgres-specific CLI commands.

Groups the schema, scratch, and bulkload subcommands under a single
``postgres`` namespace so they are clearly scoped to the Postgres output
sink rather than appearing as top-level Eleanor commands.
"""

import argparse

import eleanor.cli.bulkload as bulkload
import eleanor.cli.schema as schema
import eleanor.cli.scratch as scratch


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = "Postgres database commands"

    subparsers = parser.add_subparsers(required=True, dest="postgres_command")

    _ = schema.init(subparsers.add_parser("schema"))
    _ = scratch.init(subparsers.add_parser("scratch"))
    _ = bulkload.init(subparsers.add_parser("bulkload"))

    return parser
