from typing import override
from unittest import TestCase

from click.testing import CliRunner
from eleanor.cli import main


class TestPostgresCli(TestCase):
    runner: CliRunner = CliRunner()

    @override
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_postgres_help_lists_subcommands(self) -> None:
        result = self.runner.invoke(main, ["postgres", "--help"])
        self.assertEqual(result.exit_code, 0)
        for sub in ("schema", "bulkload", "migrate", "dump"):
            self.assertIn(sub, result.output)

    def test_postgres_schema_help_succeeds(self) -> None:
        result = self.runner.invoke(main, ["postgres", "schema", "--help"])
        self.assertEqual(result.exit_code, 0)

    def test_postgres_bulkload_help_succeeds(self) -> None:
        result = self.runner.invoke(main, ["postgres", "bulkload", "--help"])
        self.assertEqual(result.exit_code, 0)

    def test_postgres_migrate_help_succeeds(self) -> None:
        result = self.runner.invoke(main, ["postgres", "migrate", "--help"])
        self.assertEqual(result.exit_code, 0)
