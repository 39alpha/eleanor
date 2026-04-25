import argparse
from unittest import mock

from eleanor.cli.util import ConfigArgs, config_from_args
from eleanor.config import Config
from eleanor.exceptions import EleanorConfigurationException
from eleanor.output.postgres.config import database_config_from_config

from .common import TestCase


class TestConfigFromArgs(TestCase):
    """
    Tests of :func:`eleanor.cli.util.config_from_args`.
    """

    def test_database_override_sets_database_name(self):
        """
        Ensure --database injects the override into both config.raw and
        config.output.args so that database_config_from_config and the
        registry's **args splat both see the new value.
        """
        base = Config(raw={'output': {'type': 'postgres', 'args': {}}})
        args: ConfigArgs = {'config': '/fake.yaml', 'database': 'override_db'}
        with mock.patch('eleanor.cli.util.load_config', return_value=base):
            result = config_from_args(argparse.ArgumentParser(), args)

        # Traversal path (via config.raw) must reflect the override.
        self.assertEqual(database_config_from_config(result).database, 'override_db')
        # Parsed snapshot (config.output.args) must also be consistent so the
        # registry's **args splat passes the right value to the factory.
        self.assertIsInstance(result.output.args.get('database'), dict)

    def test_database_override_preserves_existing_database_fields(self):
        """
        Ensure --database only changes the 'database' name field and leaves other
        database settings (username, host, etc.) from the config file intact.
        """
        base = Config(raw={
            'output': {
                'type': 'postgres',
                'args': {'database': {'username': 'alice', 'host': 'db.local'}},
            },
        })
        args: ConfigArgs = {'config': '/fake.yaml', 'database': 'new_db'}
        with mock.patch('eleanor.cli.util.load_config', return_value=base):
            result = config_from_args(argparse.ArgumentParser(), args)

        db_cfg = database_config_from_config(result)
        self.assertEqual(db_cfg.database, 'new_db')
        self.assertEqual(db_cfg.username, 'alice')
        self.assertEqual(db_cfg.host, 'db.local')

    def test_database_override_rejected_for_non_postgres_output(self):
        """
        Ensure --database raises EleanorConfigurationException when output.type
        is not 'postgres', so the flag is never silently ignored.
        """
        with mock.patch('eleanor.config.available_outputs', return_value=frozenset({'postgres', 'csv'})):
            non_postgres = Config(raw={'output': {'type': 'csv'}})
        args: ConfigArgs = {'config': '/fake.yaml', 'database': 'db'}
        with mock.patch('eleanor.cli.util.load_config', return_value=non_postgres):
            with self.assertRaises(EleanorConfigurationException) as ctx:
                config_from_args(argparse.ArgumentParser(), args)
        self.assertIn('postgres', str(ctx.exception))

    def test_missing_database_exits(self):
        """
        Ensure config_from_args calls sys.exit(1) when output.type is postgres
        but no database name is configured and --database is not provided.
        """
        base = Config(raw={'output': {'type': 'postgres', 'args': {}}})
        args: ConfigArgs = {'config': '/fake.yaml', 'database': None}
        with mock.patch('eleanor.cli.util.load_config', return_value=base):
            with self.assertRaises(SystemExit) as ctx:
                config_from_args(argparse.ArgumentParser(), args)
        self.assertEqual(ctx.exception.code, 1)
