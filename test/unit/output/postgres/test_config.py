import importlib
import sys
from unittest import TestCase

from eleanor.exceptions import EleanorError
from eleanor.output.postgres.settings import PostgresDatabaseSettings, PostgresSinkSettings


class TestPostgresConfig(TestCase):
    """
    Tests of the postgres sink's settings module
    """

    def test_database_config_allows_missing_credentials(self) -> None:
        """
        Ensure that missing credential fields are allowed at construction time.
        """
        cfg = PostgresDatabaseSettings(
            database="main", username=None, password="secret"
        )
        self.assertIsNone(cfg.username)
        self.assertEqual(cfg.password, "secret")

        cfg = PostgresDatabaseSettings(database="main", username="alice", password=None)
        self.assertEqual(cfg.username, "alice")
        self.assertIsNone(cfg.password)

    def test_postgres_config_module_does_not_load_sqlalchemy(self) -> None:
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


class TestPostgresSinkSettingsFilterFields(TestCase):

    def test_defaults(self) -> None:
        settings = PostgresSinkSettings(database=PostgresDatabaseSettings())
        self.assertIs(settings.write_unformed, True)
        self.assertEqual(settings.min_log_moles, float("-inf"))
        self.assertEqual(settings.min_log_molality, float("-inf"))
        self.assertEqual(settings.min_log_fugacity, float("-inf"))

    def test_from_dict_parses_all_filter_fields(self) -> None:
        settings = PostgresSinkSettings.from_dict({
            "write_unformed": False,
            "min_log_moles": -8.0,
            "min_log_molality": -6.0,
            "min_log_fugacity": -4.0,
        })
        self.assertIs(settings.write_unformed, False)
        self.assertEqual(settings.min_log_moles, -8.0)
        self.assertEqual(settings.min_log_molality, -6.0)
        self.assertEqual(settings.min_log_fugacity, -4.0)

    def test_from_dict_defaults_when_keys_absent(self) -> None:
        settings = PostgresSinkSettings.from_dict({})
        self.assertIs(settings.write_unformed, True)
        self.assertEqual(settings.min_log_moles, float("-inf"))
        self.assertEqual(settings.min_log_molality, float("-inf"))
        self.assertEqual(settings.min_log_fugacity, float("-inf"))

    def test_write_unformed_rejects_non_bool(self) -> None:
        with self.assertRaises(EleanorError):
            _ = PostgresSinkSettings(database=PostgresDatabaseSettings(), write_unformed="yes")  # pyright: ignore[reportArgumentType]

    def test_min_log_moles_rejects_non_number(self) -> None:
        with self.assertRaises(EleanorError):
            _ = PostgresSinkSettings(database=PostgresDatabaseSettings(), min_log_moles="low")  # pyright: ignore[reportArgumentType]

    def test_min_log_molality_rejects_non_number(self) -> None:
        with self.assertRaises(EleanorError):
            _ = PostgresSinkSettings(database=PostgresDatabaseSettings(), min_log_molality="low")  # pyright: ignore[reportArgumentType]

    def test_min_log_fugacity_rejects_non_number(self) -> None:
        with self.assertRaises(EleanorError):
            _ = PostgresSinkSettings(database=PostgresDatabaseSettings(), min_log_fugacity="low")  # pyright: ignore[reportArgumentType]

    def test_from_dict_accepts_integer_thresholds(self) -> None:
        settings = PostgresSinkSettings.from_dict({
            "min_log_moles": -8,
            "min_log_molality": -6,
            "min_log_fugacity": -4,
        })
        self.assertEqual(settings.min_log_moles, -8.0)
        self.assertEqual(settings.min_log_molality, -6.0)
        self.assertEqual(settings.min_log_fugacity, -4.0)
