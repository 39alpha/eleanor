"""``eleanor bulkload`` -- drop or recreate constraints around a bulk-load window.

Two-phase workflow for callers running an out-of-band bulk-load (e.g.
ingesting a precomputed dataset, or a rerun that reuses a previously
populated database):

1. ``eleanor bulkload drop`` -- strip every secondary index + FK / CHECK
   constraint declared by the schema. Subsequent INSERTs / COPYs run
   without paying the per-row constraint-checking and index-maintenance
   cost.
2. ``eleanor bulkload recreate`` -- put everything back. Run this once
   the bulk-load workload finishes; if the data violates any
   constraint, the recreate transaction rolls back and the failure is
   reported.

Programmatic callers should prefer
:func:`~eleanor.output.postgres.persistence.repositories.bulk_load_window`
or :func:`~eleanor.output.postgres.persistence.schema.bulk_load_window`,
which package the same drop/recreate pair as a context manager so an
exception inside the workload still triggers the recreate.
"""

import argparse
import sys

from eleanor.cli.util import ConfigArgs, add_config_args, config_from_args, typed_args
from eleanor.output.postgres.config import database_config_from_config
from eleanor.output.postgres.persistence.repositories import drop_indexes, recreate_indexes


class BulkLoadArgs(ConfigArgs):
    """Argparse fields accepted by the ``bulkload`` command."""

    action: str  # 'drop' | 'recreate'


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = (
        "Drop or recreate the postgres sink's secondary indexes + FK / CHECK constraints around a bulk-load window"
    )

    _ = parser.add_argument(
        "action",
        choices=["drop", "recreate"],
        help=(
            '"drop" strips every secondary index + FK / CHECK constraint; '
            '"recreate" reattaches them from the static schema'
        ),
    )

    add_config_args(parser)

    parser.set_defaults(func=execute)

    return parser


def execute(parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    args = typed_args(BulkLoadArgs, ns)

    config = config_from_args(parser, args)
    database_config = database_config_from_config(config)
    if database_config.database is None:
        print("error: no database provided\n", file=sys.stdout)
        parser.print_help()
        sys.exit(1)

    action = args["action"]
    if action == "drop":
        drop_indexes(database_config)
    elif action == "recreate":
        recreate_indexes(database_config)
    else:
        # ``argparse`` ``choices=`` should keep us out of this branch; the
        # explicit raise pins it down so a future addition to ``choices``
        # without a matching dispatch arm fails loudly instead of silently
        # no-op'ing.
        raise ValueError(f"unknown bulkload action: {action!r}")
