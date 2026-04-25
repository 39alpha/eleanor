"""Unit tests for the bulkload CLI module.

The CLI is a thin glue around the persistence-layer repository helpers;
the tests pin down the dispatch contract (drop -> drop_indexes,
recreate -> recreate_indexes) and the early-exit when the loaded
config carries no database name.
"""
import argparse
from unittest import mock

from eleanor.cli import bulkload
from eleanor.config import Config
from eleanor.output.postgres.config import DatabaseConfig

from .common import TestCase


class TestBulkLoadCli(TestCase):
    """Coverage of eleanor.cli.bulkload."""

    def _ns(self, action: str) -> argparse.Namespace:
        """Build the argparse-namespace shape execute consumes."""
        return argparse.Namespace(
            action=action,
            config='/fake.yaml',
            database='demo_db',
        )

    def _config(self) -> Config:
        return Config(raw={
            'output': {
                'type': 'postgres',
                'args': {'database': {'database': 'demo_db'}},
            },
        })

    def test_drop_action_dispatches_to_repository_drop_indexes(self):
        """
        Ensure 'eleanor bulkload drop' calls repositories.drop_indexes
        with the resolved DatabaseConfig.
        """
        cfg = self._config()
        with (
            mock.patch('eleanor.cli.bulkload.config_from_args', return_value=cfg),
            mock.patch('eleanor.cli.bulkload.drop_indexes') as drop_indexes,
            mock.patch('eleanor.cli.bulkload.recreate_indexes') as recreate_indexes,
        ):
            bulkload.execute(argparse.ArgumentParser(), self._ns('drop'))

        drop_indexes.assert_called_once()
        recreate_indexes.assert_not_called()
        passed = drop_indexes.call_args.args[0]
        self.assertIsInstance(passed, DatabaseConfig)
        self.assertEqual(passed.database, 'demo_db')

    def test_recreate_action_dispatches_to_repository_recreate_indexes(self):
        """Ensure 'eleanor bulkload recreate' calls the recreate repository helper."""
        cfg = self._config()
        with (
            mock.patch('eleanor.cli.bulkload.config_from_args', return_value=cfg),
            mock.patch('eleanor.cli.bulkload.drop_indexes') as drop_indexes,
            mock.patch('eleanor.cli.bulkload.recreate_indexes') as recreate_indexes,
        ):
            bulkload.execute(argparse.ArgumentParser(), self._ns('recreate'))

        recreate_indexes.assert_called_once()
        drop_indexes.assert_not_called()

    def test_missing_database_exits_before_dispatch(self):
        """
        Ensure 'bulkload' exits with code 1 and never calls the
        repository helpers when the resolved config has no database
        name. The CLI must not silently no-op against the local default
        database.
        """
        bare = Config(raw={'output': {'type': 'postgres', 'args': {}}})
        with (
            mock.patch('eleanor.cli.bulkload.config_from_args', return_value=bare),
            mock.patch('eleanor.cli.bulkload.drop_indexes') as drop_indexes,
            mock.patch('eleanor.cli.bulkload.recreate_indexes') as recreate_indexes,
        ):
            with self.assertRaises(SystemExit) as ctx:
                bulkload.execute(argparse.ArgumentParser(), self._ns('drop'))

        self.assertEqual(ctx.exception.code, 1)
        drop_indexes.assert_not_called()
        recreate_indexes.assert_not_called()

    def test_init_registers_action_choices_and_default_func(self):
        """
        Ensure init wires up the positional 'action' argument with
        choices=['drop', 'recreate'] and points 'func' at execute.
        Without this, the top-level CLI dispatcher would not be able
        to find the command.
        """
        parser = argparse.ArgumentParser()
        _ = bulkload.init(parser)
        self.assertIs(parser.get_default('func'), bulkload.execute)
        choices: set[str] = set()
        for action in parser._actions:  # pyright: ignore[reportPrivateUsage]
            if action.dest == 'action' and action.choices is not None:
                choices = set(action.choices)
        self.assertEqual(choices, {'drop', 'recreate'})
