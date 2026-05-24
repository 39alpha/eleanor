import importlib
import sys
from types import SimpleNamespace

from eleanor.config import Config
from eleanor.output.postgres.config import DatabaseConfig, database_config_from_config

from ..common import TestCase


class TestPostgresConfig(TestCase):
    """
    Tests of the postgres sink's connection-config module
    (:mod:`eleanor.output.postgres.config`).
    """

    def test_database_config_does_not_validate_dialect(self):
        """
        Ensure PostgresSink -- not DatabaseConfig -- is responsible for dialect rejection.
        """
        cfg = DatabaseConfig(dialect="sqlite", username="alice", password="secret", database="main")
        self.assertEqual(cfg.dialect, "sqlite")

    def test_database_config_allows_missing_credentials(self):
        """
        Ensure that missing credential fields are allowed at construction time.
        """
        cfg = DatabaseConfig(database="main", username=None, password="secret")
        self.assertIsNone(cfg.username)
        self.assertEqual(cfg.password, "secret")

        cfg = DatabaseConfig(database="main", username="alice", password=None)
        self.assertEqual(cfg.username, "alice")
        self.assertIsNone(cfg.password)

        cfg = DatabaseConfig(database="main", dbapi=None, username="alice", password="secret")
        self.assertIsNone(cfg.dbapi)
        self.assertEqual(cfg.username, "alice")
        self.assertEqual(cfg.password, "secret")

    def test_database_config_from_config_reads_args_database(self):
        """
        Ensure database_config_from_config reads the output.args.database raw block.
        """
        cfg = Config.from_dict(
            {
                "output": {
                    "kind": "postgres",
                    "args": {
                        "database": {
                            "database": "sample",
                            "username": "alice",
                            "password": "secret",
                        },
                    },
                },
            }
        )
        database_config = database_config_from_config(cfg.output)
        self.assertEqual(database_config.database, "sample")
        self.assertEqual(database_config.username, "alice")
        self.assertEqual(database_config.password, "secret")

    def test_database_config_from_config_handles_missing_block(self):
        """
        Ensure database_config_from_config returns a default DatabaseConfig when the
        raw config has no output.args.database block at all.
        """
        result = database_config_from_config(Config().output)
        self.assertIsNone(result.database)
        self.assertIsNone(result.username)

    def test_database_config_from_config_tolerates_non_dict_segments(self):
        """
        Ensure database_config_from_config falls back to defaults when any path
        segment along output.args.database is not a mapping. Uses
        :class:`SimpleNamespace` to bypass :class:`Config` constructor
        validation, since the helper must be defensive against
        arbitrary inputs.
        """
        # output is not a mapping
        self.assertIsNone(database_config_from_config(SimpleNamespace(output={}).output).database)

        # args is not a mapping
        self.assertIsNone(database_config_from_config(SimpleNamespace(output={"args": "oops"}).output).database)

        # database is not a mapping
        self.assertIsNone(
            database_config_from_config(SimpleNamespace(output={"args": {"database": "oops"}}).output).database
        )

    def test_postgres_config_module_does_not_load_sqlalchemy(self):
        """
        Ensure importing eleanor.output.postgres.config does not transitively
        load SQLAlchemy. Protects the lazy-import contract maintained by
        eleanor/output/postgres/__init__.py.
        """
        snapshot = dict(sys.modules)
        for name in list(sys.modules):
            if name == "sqlalchemy" or name.startswith("sqlalchemy."):
                del sys.modules[name]
        # Drop the leaf and parent so importing it actually re-runs __init__.
        for name in [
            "eleanor.output.postgres.config",
            "eleanor.output.postgres",
        ]:
            _ = sys.modules.pop(name, None)
        try:
            _ = importlib.import_module("eleanor.output.postgres.config")
            self.assertNotIn("sqlalchemy", sys.modules)
        finally:
            # Remove modules added during the test, then restore the snapshot
            # so subsequent tests see a consistent sys.modules state.
            for name in [k for k in list(sys.modules) if k not in snapshot]:
                del sys.modules[name]
            sys.modules.update(snapshot)
