import importlib
import sys
from unittest import TestCase

from eleanor.output.postgres.settings import PostgresDatabaseSettings


class TestPostgresConfig(TestCase):
    """
    Tests of the postgres sink's settings module
    """

    def test_database_config_allows_missing_credentials(self):
        """
        Ensure that missing credential fields are allowed at construction time.
        """
        cfg = PostgresDatabaseSettings(database="main", username=None, password="secret")
        self.assertIsNone(cfg.username)
        self.assertEqual(cfg.password, "secret")

        cfg = PostgresDatabaseSettings(database="main", username="alice", password=None)
        self.assertEqual(cfg.username, "alice")
        self.assertIsNone(cfg.password)

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
            "eleanor.output.postgres.settings",
            "eleanor.output.postgres",
        ]:
            _ = sys.modules.pop(name, None)
        try:
            _ = importlib.import_module("eleanor.output.postgres.settings")
            self.assertNotIn("sqlalchemy", sys.modules)
        finally:
            # Remove modules added during the test, then restore the snapshot
            # so subsequent tests see a consistent sys.modules state.
            for name in [k for k in list(sys.modules) if k not in snapshot]:
                del sys.modules[name]
            sys.modules.update(snapshot)
