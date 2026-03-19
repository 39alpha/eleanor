import json
import textwrap
from os.path import join
from tempfile import TemporaryDirectory

from eleanor.config import Config, DatabaseConfig, load_config
from eleanor.exceptions import EleanorConfigurationException, EleanorException

from .common import TestCase


class TestConfig(TestCase):
    """
    Tests of the eleanor.config module.
    """

    def test_database_config_str_without_port(self):
        """
        Ensure that :class:`DatabaseConfig` string formatting omits a port when not provided.
        """
        cfg = DatabaseConfig(database='main', username='alice', password='secret')
        self.assertEqual(str(cfg), 'postgresql+psycopg://alice:secret@localhost/main')

    def test_database_config_str_with_port(self):
        """
        Ensure that :class:`DatabaseConfig` string formatting includes the configured port.
        """
        cfg = DatabaseConfig(
            database='main',
            username='alice',
            password='secret',
            host='db.local',
            port=5432,
        )
        self.assertEqual(str(cfg), 'postgresql+psycopg://alice:secret@db.local:5432/main')

    def test_database_config_rejects_unsupported_dialect(self):
        """
        Ensure that unsupported database dialects raise configuration errors.
        """
        with self.assertRaises(EleanorConfigurationException):
            DatabaseConfig(dialect='sqlite', username='alice', password='secret')

    def test_database_config_requires_credentials(self):
        """
        Ensure that required database credential fields are validated at construction time.
        """
        with self.assertRaises(EleanorConfigurationException):
            DatabaseConfig(database='main', username=None, password='secret')

        with self.assertRaises(EleanorConfigurationException):
            DatabaseConfig(database='main', username='alice', password=None)

        with self.assertRaises(EleanorConfigurationException):
            DatabaseConfig(database='main', dbapi=None, username='alice', password='secret')

    def test_config_defaults_raise_without_credentials(self):
        """
        Ensure that :class:`Config` default construction raises without required credentials.
        """
        with self.assertRaises(EleanorConfigurationException):
            Config()

    def test_config_from_yaml(self):
        """
        Ensure that YAML configuration files are parsed correctly.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, 'config.yaml')
            content = textwrap.dedent("""\
                database:
                  dialect: postgresql
                  dbapi: psycopg
                  host: localhost
                  port: 5432
                  database: sample
                  username: alice
                  password: secret
                  sslmode: require
            """)
            with open(path, 'w') as f:
                f.write(content)

            cfg = Config.from_yaml(path)
            self.assertEqual(cfg.database.database, 'sample')
            self.assertEqual(cfg.database.port, 5432)
            self.assertEqual(cfg.database.sslmode, 'require')

    def test_config_from_toml(self):
        """
        Ensure that TOML configuration files are parsed correctly.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, 'config.toml')
            content = textwrap.dedent("""\
                [database]
                dialect = "postgresql"
                dbapi = "psycopg"
                host = "localhost"
                port = 5432
                database = "sample"
                username = "alice"
                password = "secret"
                sslmode = "require"
            """)
            with open(path, 'w') as f:
                f.write(content)

            cfg = Config.from_toml(path)
            self.assertEqual(cfg.database.database, 'sample')
            self.assertEqual(cfg.database.port, 5432)
            self.assertEqual(cfg.database.sslmode, 'require')

    def test_config_from_json(self):
        """
        Ensure that JSON configuration files are parsed correctly.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, 'config.json')
            raw = {
                'database': {
                    'dialect': 'postgresql',
                    'dbapi': 'psycopg',
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'sample',
                    'username': 'alice',
                    'password': 'secret',
                    'sslmode': 'require',
                }
            }
            with open(path, 'w') as f:
                json.dump(raw, f)

            cfg = Config.from_json(path)
            self.assertEqual(cfg.database.database, 'sample')
            self.assertEqual(cfg.database.port, 5432)
            self.assertEqual(cfg.database.sslmode, 'require')

    def test_config_from_file_dispatches_by_extension(self):
        """
        Ensure that :meth:`Config.from_file` dispatches loaders by file extension.
        """
        with TemporaryDirectory() as tmp:
            yaml_path = join(tmp, 'config.yml')
            with open(yaml_path, 'w') as f:
                f.write(
                    "database:\n"
                    "  dialect: postgresql\n"
                    "  dbapi: psycopg\n"
                    "  host: localhost\n"
                    "  database: sample\n"
                    "  username: alice\n"
                    "  password: secret\n"
                )

            cfg = Config.from_file(yaml_path)
            self.assertEqual(cfg.database.username, 'alice')

    def test_config_from_file_dispatches_yaml_extension(self):
        """
        Ensure that :meth:`Config.from_file` dispatches the explicit .yaml extension.
        """
        with TemporaryDirectory() as tmp:
            yaml_path = join(tmp, 'config.yaml')
            with open(yaml_path, 'w') as f:
                f.write(
                    "database:\n"
                    "  dialect: postgresql\n"
                    "  dbapi: psycopg\n"
                    "  host: localhost\n"
                    "  database: sample\n"
                    "  username: alice\n"
                    "  password: secret\n"
                )

            cfg = Config.from_file(yaml_path)
            self.assertEqual(cfg.database.database, 'sample')

    def test_config_from_file_dispatches_toml_extension(self):
        """
        Ensure that :meth:`Config.from_file` dispatches the .toml extension.
        """
        with TemporaryDirectory() as tmp:
            toml_path = join(tmp, 'config.toml')
            with open(toml_path, 'w') as f:
                f.write(
                    "[database]\n"
                    "dialect = \"postgresql\"\n"
                    "dbapi = \"psycopg\"\n"
                    "host = \"localhost\"\n"
                    "database = \"sample\"\n"
                    "username = \"alice\"\n"
                    "password = \"secret\"\n"
                )

            cfg = Config.from_file(toml_path)
            self.assertEqual(cfg.database.database, 'sample')

    def test_config_from_file_rejects_bad_extension(self):
        """
        Ensure that unsupported config file extensions raise wrapped parse errors.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, 'config.ini')
            with open(path, 'w') as f:
                f.write('[database]\n')

            with self.assertRaises(EleanorException):
                Config.from_file(path)

    def test_load_config(self):
        """
        Ensure that :func:`load_config` handles None, file paths, and Config objects.
        """
        with self.assertRaises(EleanorConfigurationException):
            load_config(None)

        with TemporaryDirectory() as tmp:
            path = join(tmp, 'config.json')
            raw = {
                'database': {
                    'dialect': 'postgresql',
                    'dbapi': 'psycopg',
                    'host': 'localhost',
                    'database': 'sample',
                    'username': 'alice',
                    'password': 'secret',
                }
            }
            with open(path, 'w') as f:
                json.dump(raw, f)

            from_file = load_config(path)
            self.assertEqual(from_file.database.database, 'sample')

        cfg = Config(raw={'database': {'username': 'alice', 'password': 'secret'}})
        same = load_config(cfg)
        self.assertIs(same, cfg)
