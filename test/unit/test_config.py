import json
import textwrap
from os.path import join
from tempfile import TemporaryDirectory
from typing import cast

from eleanor.config import Config, ConfigRaw, ParallelConfig, load_config
from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.output.config import Config as OutputConfig
from eleanor.output.config import ConfigRaw as OutputRaw
from eleanor.output.postgres.config import database_config_from_config

from .common import TestCase


class TestConfig(TestCase):
    """
    Tests of the eleanor.config module.
    """

    def test_parallel_config_defaults(self):
        """
        Ensure that :class:`ParallelConfig` defaults to multiprocessing with a multi-chunk worker batch.
        """
        cfg = ParallelConfig()
        self.assertEqual(cfg.kind, "multiprocessing")
        self.assertEqual(cfg.chunks_per_worker, 10)

    def test_parallel_config_validation(self):
        """
        Ensure invalid chunk values raise configuration errors at construction.

        Backend name validation is deferred to :func:`load_executor`;
        ``ParallelConfig`` itself accepts any string.
        """
        cfg = ParallelConfig(kind="bogus")
        self.assertEqual(cfg.kind, "bogus")
        with self.assertRaises(EleanorConfigurationException):
            _ = ParallelConfig(chunks_per_worker=0)

    def test_config_defaults_allow_missing_credentials(self):
        """
        Ensure that :class:`Config` default construction allows missing credentials.
        """
        cfg = Config()
        database_config = database_config_from_config(cfg)
        self.assertIsNone(database_config.username)
        self.assertIsNone(database_config.password)
        self.assertEqual(cfg.parallel.kind, "multiprocessing")
        self.assertEqual(cfg.parallel.chunks_per_worker, 10)

    def test_config_from_yaml(self):
        """
        Ensure that YAML configuration files are parsed correctly.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, "config.yaml")
            content = textwrap.dedent("""\
                output:
                  kind: postgres
                  args:
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
            with open(path, "w") as f:
                _ = f.write(content)

            cfg = Config.from_yaml(path)
            database_config = database_config_from_config(cfg)
            self.assertEqual(database_config.database, "sample")
            self.assertEqual(database_config.port, 5432)
            self.assertEqual(database_config.sslmode, "require")

    def test_config_from_toml(self):
        """
        Ensure that TOML configuration files are parsed correctly.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, "config.toml")
            content = textwrap.dedent("""\
                [output]
                kind = "postgres"
                [output.args.database]
                dialect = "postgresql"
                dbapi = "pstypeycopg"
                host = "localhost"
                port = 5432
                database = "sample"
                username = "alice"
                password = "secret"
                sslmode = "require"
                [parallel]
                kind = "serial"
                chunks_per_worker = 3
            """)
            with open(path, "w") as f:
                _ = f.write(content)

            cfg = Config.from_toml(path)
            database_config = database_config_from_config(cfg)
            self.assertEqual(database_config.database, "sample")
            self.assertEqual(database_config.port, 5432)
            self.assertEqual(database_config.sslmode, "require")
            self.assertEqual(cfg.parallel.kind, "serial")
            self.assertEqual(cfg.parallel.chunks_per_worker, 3)

    def test_config_from_json(self):
        """
        Ensure that JSON configuration files are parsed correctly.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, "config.json")
            raw = {
                "output": {
                    "kind": "postgres",
                    "args": {
                        "database": {
                            "dialect": "postgresql",
                            "dbapi": "psycopg",
                            "host": "localhost",
                            "port": 5432,
                            "database": "sample",
                            "username": "alice",
                            "password": "secret",
                            "sslmode": "require",
                        },
                    },
                },
                "parallel": {
                    "kind": "serial",
                    "chunks_per_worker": 8,
                },
            }
            with open(path, "w") as f:
                json.dump(raw, f)

            cfg = Config.from_json(path)
            database_config = database_config_from_config(cfg)
            self.assertEqual(database_config.database, "sample")
            self.assertEqual(database_config.port, 5432)
            self.assertEqual(database_config.sslmode, "require")
            self.assertEqual(cfg.parallel.kind, "serial")
            self.assertEqual(cfg.parallel.chunks_per_worker, 8)

    def test_config_from_file_dispatches_by_extension(self):
        """
        Ensure that :meth:`Config.from_file` dispatches loaders by file extension.
        """
        with TemporaryDirectory() as tmp:
            yaml_path = join(tmp, "config.yml")
            with open(yaml_path, "w") as f:
                _ = f.write(
                    "output:\n"
                    + "  kind: postgres\n"
                    + "  args:\n"
                    + "    database:\n"
                    + "      dialect: postgresql\n"
                    + "      dbapi: psycopg\n"
                    + "      host: localhost\n"
                    + "      database: sample\n"
                    + "      username: alice\n"
                    + "      password: secret\n"
                )

            cfg = Config.from_file(yaml_path)
            self.assertEqual(database_config_from_config(cfg).username, "alice")

    def test_config_from_file_dispatches_yaml_extension(self):
        """
        Ensure that :meth:`Config.from_file` dispatches the explicit .yaml extension.
        """
        with TemporaryDirectory() as tmp:
            yaml_path = join(tmp, "config.yaml")
            with open(yaml_path, "w") as f:
                _ = f.write(
                    "output:\n"
                    + "  kind: postgres\n"
                    + "  args:\n"
                    + "    database:\n"
                    + "      dialect: postgresql\n"
                    + "      dbapi: psycopg\n"
                    + "      host: localhost\n"
                    + "      database: sample\n"
                    + "      username: alice\n"
                    + "      password: secret\n"
                )

            cfg = Config.from_file(yaml_path)
            self.assertEqual(database_config_from_config(cfg).database, "sample")

    def test_config_from_file_dispatches_toml_extension(self):
        """
        Ensure that :meth:`Config.from_file` dispatches the .toml extension.
        """
        with TemporaryDirectory() as tmp:
            toml_path = join(tmp, "config.toml")
            with open(toml_path, "w") as f:
                _ = f.write(
                    "[output]\n"
                    + 'kind = "postgres"\n'
                    + "[output.args.database]\n"
                    + 'dialect = "postgresql"\n'
                    + 'dbapi = "psycopg"\n'
                    + 'host = "localhost"\n'
                    + 'database = "sample"\n'
                    + 'username = "alice"\n'
                    + 'password = "secret"\n'
                )

            cfg = Config.from_file(toml_path)
            self.assertEqual(database_config_from_config(cfg).database, "sample")

    def test_config_from_file_rejects_bad_extension(self):
        """
        Ensure that unsupported config file extensions raise wrapped parse errors.
        """
        with TemporaryDirectory() as tmp:
            path = join(tmp, "config.ini")
            with open(path, "w") as f:
                _ = f.write("[output]\n")

            with self.assertRaises(EleanorException):
                _ = Config.from_file(path)

    def test_load_config(self):
        """
        Ensure that :func:`load_config` handles None, file paths, and Config objects.
        """
        default_cfg = load_config(None)
        self.assertIsInstance(default_cfg, Config)
        default_database_config = database_config_from_config(default_cfg)
        self.assertIsNone(default_database_config.username)
        self.assertIsNone(default_database_config.password)

        with TemporaryDirectory() as tmp:
            path = join(tmp, "config.json")
            raw = {
                "output": {
                    "kind": "postgres",
                    "args": {
                        "database": {
                            "dialect": "postgresql",
                            "dbapi": "psycopg",
                            "host": "localhost",
                            "database": "sample",
                            "username": "alice",
                            "password": "secret",
                        },
                    },
                },
            }
            with open(path, "w") as f:
                json.dump(raw, f)

            from_file = load_config(path)
            self.assertEqual(database_config_from_config(from_file).database, "sample")

        cfg = Config(
            raw={"output": {"kind": "postgres", "args": {"database": {"username": "alice", "password": "secret"}}}}
        )
        same = load_config(cfg)
        self.assertIs(same, cfg)

    def test_config_has_no_default_output_target(self):
        """
        Ensure Config does not silently default to a specific output type.

        Callers must set ``output.type`` explicitly or supply an
        ``output_sink=`` override to :class:`Eleanor`.
        """
        cfg = Config()
        self.assertIsNone(cfg.output.kind)

    def test_output_config_defers_type_validation(self):
        """
        Ensure ``OutputConfig`` stores any type string without raising.

        Type validation is deferred to :func:`load_output_sink`, so
        ``OutputConfig`` itself accepts arbitrary values — including
        third-party plugin names not yet registered.
        """
        cfg = OutputConfig(kind="definitely-not-a-sink")
        self.assertEqual(cfg.kind, "definitely-not-a-sink")

        cfg_plugin = OutputConfig(kind="csv")
        self.assertEqual(cfg_plugin.kind, "csv")

    def test_output_config_from_raw_parses_args(self):
        """
        Ensure output.args is preserved as a string-keyed dict.
        """
        cfg = Config(raw={"output": {"kind": "postgres", "args": {"batch_size": 4, "format": "json"}}})
        self.assertEqual(cfg.output.kind, "postgres")
        self.assertEqual(cfg.output.args, {"batch_size": 4, "format": "json"})

    def test_output_config_rejects_non_dict_args(self):
        """
        Ensure output.args validation rejects non-dict values.
        """
        with self.assertRaises(EleanorConfigurationException):
            _ = OutputConfig.from_raw(cast(OutputRaw, cast(object, {"type": "postgres", "args": "nope"})))

    def test_output_config_rejects_none_args(self):
        """
        Ensure output.args validation rejects None instead of silently defaulting.
        """
        with self.assertRaises(EleanorConfigurationException):
            _ = OutputConfig.from_raw(cast(OutputRaw, cast(object, {"type": "postgres", "args": None})))

    def test_config_parallel_raw_defaults_when_missing(self):
        """
        Ensure parallel defaults are applied when raw config omits the parallel section.
        """
        cfg = Config(raw={"output": {"kind": "postgres", "args": {"database": {"database": "sample"}}}})
        self.assertEqual(cfg.parallel.kind, "multiprocessing")
        self.assertEqual(cfg.parallel.chunks_per_worker, 10)

    def test_config_rejects_legacy_database_key(self):
        """
        Ensure Config raises EleanorConfigurationException when the raw dict contains
        the old top-level 'database:' key, guiding users to migrate rather than
        silently producing a confusing 'no database provided' error.
        """
        with self.assertRaises(EleanorConfigurationException) as ctx:
            _ = Config(
                raw=cast(ConfigRaw, cast(object, {"database": {"database": "sample"}}))
            )  # kind: ignore[typeddict-unknown-key]
        self.assertIn("database", str(ctx.exception))
        self.assertIn("output.args.database", str(ctx.exception))
