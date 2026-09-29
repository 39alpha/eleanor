from typing import override
from unittest import TestCase

from click.testing import CliRunner
from eleanor.cli import main


class TestPostgresDumpCli(TestCase):
    runner: CliRunner = CliRunner()

    @override
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_dump_help_lists_subcommands(self) -> None:
        result = self.runner.invoke(main, ["postgres", "dump", "--help"])
        self.assertEqual(result.exit_code, 0)
        for sub in ("order", "scratch"):
            self.assertIn(sub, result.output)

    def test_postgres_dump_order_help_succeeds(self) -> None:
        result = self.runner.invoke(main, ["postgres", "dump", "order", "--help"])
        self.assertEqual(result.exit_code, 0)

    def test_postgres_dump_scratch_help_succeeds(self) -> None:
        result = self.runner.invoke(main, ["postgres", "dump", "scratch", "--help"])
        self.assertEqual(result.exit_code, 0)
