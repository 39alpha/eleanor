"""``-h`` is accepted as ``--help`` by every command in the ``eleanor`` tree."""

import click
import pytest
from click.testing import CliRunner

from eleanor.cli import main


def command_paths(command: click.Command, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Return the invocation path of ``command`` and of every command beneath it."""
    paths = [path]
    if isinstance(command, click.Group):
        ctx = click.Context(command)
        for name in command.list_commands(ctx):
            sub = command.get_command(ctx, name)
            if sub is not None:
                paths.extend(command_paths(sub, (*path, name)))
    return paths


PATHS = command_paths(main)


def test_command_tree_is_walked() -> None:
    assert ("run",) in PATHS
    assert ("postgres", "dump", "order") in PATHS


@pytest.mark.parametrize("path", PATHS, ids=[" ".join(("eleanor", *path)) for path in PATHS])
def test_short_help_flag_matches_long(runner: CliRunner, path: tuple[str, ...]) -> None:
    short = runner.invoke(main, [*path, "-h"])
    long = runner.invoke(main, [*path, "--help"])

    assert short.exit_code == 0, short.output
    assert short.output == long.output
    assert "-h, --help" in short.output
