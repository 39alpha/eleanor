"""Unit tests for the bulkload Click command."""

from typing import override
from unittest import TestCase, mock

from click.testing import CliRunner
from eleanor.cli import main
from eleanor.config import Config
from eleanor.output.postgres.persistence.schema import BulkLoadTargets
from eleanor.output.postgres.settings import PostgresDatabaseSettings


class TestBulkLoadCli(TestCase):
    """Coverage of eleanor.output.postgres.cli.bulkload."""

    runner: CliRunner = CliRunner()

    @override
    def setUp(self) -> None:
        self.runner = CliRunner()

    def _config(self) -> Config:
        return Config.from_dict(
            {
                "output": {
                    "kind": "postgres",
                    "database": {
                        "database": "demo_db",
                    },
                },
            }
        )

    def test_drop_action_dispatches_to_repository_drop_indexes(self) -> None:
        """
        Ensure 'eleanor postgres bulkload drop' calls repositories.drop_indexes
        with the resolved PostgresDatabaseSettings.
        """
        cfg = self._config()
        with (
            mock.patch(
                "eleanor.output.postgres.cli.config_from_args", return_value=cfg
            ) as config_from_args,
            mock.patch("eleanor.output.postgres.cli.drop_indexes") as drop_indexes,
            mock.patch(
                "eleanor.output.postgres.cli.recreate_indexes"
            ) as recreate_indexes,
        ):
            result = self.runner.invoke(
                main,
                [
                    "postgres",
                    "bulkload",
                    "drop",
                    "-y",
                    "-c",
                    "/fake.yaml",
                    "-d",
                    "demo_db",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        config_from_args.assert_called_once_with("/fake.yaml", "demo_db")
        drop_indexes.assert_called_once()
        recreate_indexes.assert_not_called()
        passed = drop_indexes.call_args.args[0]
        self.assertIsInstance(passed, PostgresDatabaseSettings)
        self.assertEqual(passed.database, "demo_db")

    def test_recreate_action_dispatches_to_repository_recreate_indexes(self) -> None:
        """Ensure 'eleanor postgres bulkload recreate' calls the recreate repository helper."""
        cfg = self._config()
        with (
            mock.patch(
                "eleanor.output.postgres.cli.config_from_args", return_value=cfg
            ),
            mock.patch("eleanor.output.postgres.cli.drop_indexes") as drop_indexes,
            mock.patch(
                "eleanor.output.postgres.cli.recreate_indexes"
            ) as recreate_indexes,
        ):
            result = self.runner.invoke(
                main,
                [
                    "postgres",
                    "bulkload",
                    "recreate",
                    "-c",
                    "/fake.yaml",
                    "-d",
                    "demo_db",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        recreate_indexes.assert_called_once()
        drop_indexes.assert_not_called()

    def test_drop_forwards_selected_targets(self) -> None:
        """Ensure --no-fks reaches drop_indexes as a restricted BulkLoadTargets."""
        cfg = self._config()
        with (
            mock.patch("eleanor.output.postgres.cli.config_from_args", return_value=cfg),
            mock.patch("eleanor.output.postgres.cli.drop_indexes") as drop_indexes,
            mock.patch("eleanor.output.postgres.cli.recreate_indexes"),
        ):
            result = self.runner.invoke(
                main,
                ["postgres", "bulkload", "drop", "--no-fks", "-y", "-c", "/fake.yaml", "-d", "demo_db"],
            )

        self.assertEqual(result.exit_code, 0)
        targets = drop_indexes.call_args.args[1]
        self.assertEqual(targets, BulkLoadTargets(indexes=True, checks=True, foreign_keys=False))

    def test_nothing_selected_is_usage_error(self) -> None:
        """Ensure selecting no classes is a usage error and never dispatches."""
        cfg = self._config()
        with (
            mock.patch("eleanor.output.postgres.cli.config_from_args", return_value=cfg),
            mock.patch("eleanor.output.postgres.cli.drop_indexes") as drop_indexes,
            mock.patch("eleanor.output.postgres.cli.recreate_indexes") as recreate_indexes,
        ):
            result = self.runner.invoke(
                main,
                [
                    "postgres", "bulkload", "drop",
                    "--no-indexes", "--no-fks", "--no-checks",
                    "-y", "-c", "/fake.yaml", "-d", "demo_db",
                ],
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("nothing selected", result.output)
        drop_indexes.assert_not_called()
        recreate_indexes.assert_not_called()

    def test_confirmation_lists_selected_classes(self) -> None:
        """Ensure the drop confirmation prompt names exactly the selected classes."""
        cfg = self._config()
        with (
            mock.patch("eleanor.output.postgres.cli.config_from_args", return_value=cfg),
            mock.patch("eleanor.output.postgres.cli.drop_indexes") as drop_indexes,
            mock.patch("eleanor.output.postgres.cli.recreate_indexes"),
        ):
            result = self.runner.invoke(
                main,
                ["postgres", "bulkload", "drop", "--no-checks", "-c", "/fake.yaml", "-d", "demo_db"],
                input="n\n",
            )

        self.assertIn("indexes, foreign keys", result.output)
        self.assertNotIn("CHECK constraints", result.output)
        drop_indexes.assert_not_called()

    def test_missing_database_exits_before_dispatch(self) -> None:
        """
        Ensure 'bulkload' exits with code 1 and never calls the
        repository helpers when the resolved config has no database
        name. The CLI must not silently no-op against the local default
        database.
        """
        bare = Config.from_dict({"output": {"kind": "postgres"}})
        with (
            mock.patch(
                "eleanor.output.postgres.cli.config_from_args", return_value=bare
            ),
            mock.patch("eleanor.output.postgres.cli.drop_indexes") as drop_indexes,
            mock.patch(
                "eleanor.output.postgres.cli.recreate_indexes"
            ) as recreate_indexes,
        ):
            result = self.runner.invoke(
                main, ["postgres", "bulkload", "drop", "-y", "-c", "/fake.yaml"]
            )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("no database provided", result.output)
        drop_indexes.assert_not_called()
        recreate_indexes.assert_not_called()
