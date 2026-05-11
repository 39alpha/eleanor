from typing import override

from click.testing import CliRunner

from eleanor.cli import main

from .common import TestCase


class TestCliDoctor(TestCase):
    runner: CliRunner = CliRunner()

    @override
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_doctor_lists_postgres_cli_plugin(self):
        result = self.runner.invoke(main, ["doctor"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("CLI commands", result.output)
        self.assertIn("postgres", result.output)
