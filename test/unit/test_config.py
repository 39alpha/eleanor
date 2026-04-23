import json
import textwrap
from os.path import join
from tempfile import TemporaryDirectory
from unittest import mock

from eleanor.config import Config, DatabaseConfig, OutputConfig, ParallelConfig, load_config
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

    def test_database_config_allows_non_postgres_dialect(self):
        """
        Ensure DatabaseConfig itself stays sink-agnostic; sink-specific code enforces dialect support.
        """
        cfg = DatabaseConfig(dialect='sqlite', username='alice', password='secret', database='main')
        self.assertEqual(cfg.dialect, 'sqlite')

    def test_database_config_allows_missing_credentials(self):
        """
        Ensure that missing credential fields are allowed at construction time.
        """
        cfg = DatabaseConfig(database='main', username=None, password='secret')
        self.assertIsNone(cfg.username)
        self.assertEqual(cfg.password, 'secret')

        cfg = DatabaseConfig(database='main', username='alice', password=None)
        self.assertEqual(cfg.username, 'alice')
        self.assertIsNone(cfg.password)

        cfg = DatabaseConfig(database='main', dbapi=None, username='alice', password='secret')
        self.assertIsNone(cfg.dbapi)
        self.assertEqual(cfg.username, 'alice')
        self.assertEqual(cfg.password, 'secret')

    def test_parallel_config_defaults(self):
        """
        Ensure that :class:`ParallelConfig` defaults to multiprocessing with one chunk per worker.
        """
        cfg = ParallelConfig()
        self.assertEqual(cfg.backend, 'multiprocessing')
        self.assertEqual(cfg.chunks_per_worker, 1)

    def test_parallel_config_validation(self):
        """
        Ensure invalid backend names and chunk values raise configuration errors.
        """
        with self.assertRaises(EleanorConfigurationException):
            ParallelConfig(backend='bogus')
        with self.assertRaises(EleanorConfigurationException):
            ParallelConfig(chunks_per_worker=0)

    def test_config_defaults_allow_missing_credentials(self):
        """
        Ensure that :class:`Config` default construction allows missing credentials.
        """
        cfg = Config()
        self.assertIsNone(cfg.database.username)
        self.assertIsNone(cfg.database.password)
        self.assertEqual(cfg.parallel.backend, 'multiprocessing')
        self.assertEqual(cfg.parallel.chunks_per_worker, 1)

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
                [parallel]
                backend = "serial"
                chunks_per_worker = 3
            """)
            with open(path, 'w') as f:
                f.write(content)

            cfg = Config.from_toml(path)
            self.assertEqual(cfg.database.database, 'sample')
            self.assertEqual(cfg.database.port, 5432)
            self.assertEqual(cfg.database.sslmode, 'require')
            self.assertEqual(cfg.parallel.backend, 'serial')
            self.assertEqual(cfg.parallel.chunks_per_worker, 3)

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
                },
                'parallel': {
                    'backend': 'serial',
                    'chunks_per_worker': 8,
                },
            }
            with open(path, 'w') as f:
                json.dump(raw, f)

            cfg = Config.from_json(path)
            self.assertEqual(cfg.database.database, 'sample')
            self.assertEqual(cfg.database.port, 5432)
            self.assertEqual(cfg.database.sslmode, 'require')
            self.assertEqual(cfg.parallel.backend, 'serial')
            self.assertEqual(cfg.parallel.chunks_per_worker, 8)

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
        default_cfg = load_config(None)
        self.assertIsInstance(default_cfg, Config)
        self.assertIsNone(default_cfg.database.username)
        self.assertIsNone(default_cfg.database.password)

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

    def test_config_has_default_output_target(self):
        """
        Ensure Config provides an explicit default output target for sink selection.
        """
        cfg = Config()
        self.assertEqual(cfg.output.type, 'postgres')

    def test_output_config_rejects_unsupported_type(self):
        """
        Ensure OutputConfig raises with a message that names the unsupported type
        and lists available sink options.
        """
        with self.assertRaises(EleanorConfigurationException) as ctx:
            OutputConfig(type='csv')
        msg = str(ctx.exception)
        self.assertIn('csv', msg)
        self.assertIn('postgres', msg)

    def test_output_config_accepts_plugin_type_when_registry_exposes_it(self):
        """
        Ensure OutputConfig validation follows the registry's dynamic sink names.
        """
        with mock.patch('eleanor.config.available_outputs', return_value=frozenset({'postgres', 'csv'})):
            cfg = OutputConfig(type='csv')
        self.assertEqual(cfg.type, 'csv')

    def test_output_config_from_raw_parses_args(self):
        """
        Ensure output.args is preserved as a string-keyed dict.
        """
        cfg = Config(raw={'output': {'type': 'postgres', 'args': {'batch_size': 4, 'format': 'json'}}})
        self.assertEqual(cfg.output.type, 'postgres')
        self.assertEqual(cfg.output.args, {'batch_size': 4, 'format': 'json'})

    def test_output_config_rejects_non_dict_args(self):
        """
        Ensure output.args validation rejects non-dict values.
        """
        with self.assertRaises(EleanorConfigurationException):
            _ = OutputConfig.from_raw({'type': 'postgres', 'args': 'nope'})  # type: ignore[arg-type]

    def test_output_config_rejects_none_args(self):
        """
        Ensure output.args validation rejects None instead of silently defaulting.
        """
        with self.assertRaises(EleanorConfigurationException):
            _ = OutputConfig.from_raw({'type': 'postgres', 'args': None})  # type: ignore[arg-type]

    def test_config_parallel_raw_defaults_when_missing(self):
        """
        Ensure parallel defaults are applied when raw config omits the parallel section.
        """
        cfg = Config(raw={'database': {'database': 'sample'}})
        self.assertEqual(cfg.parallel.backend, 'multiprocessing')
        self.assertEqual(cfg.parallel.chunks_per_worker, 1)
