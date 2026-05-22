from pathlib import Path
from typing import override
from unittest import mock

from click.testing import CliRunner

from eleanor.cli import main
from eleanor.config import Config
from eleanor.exceptions import EleanorShutdown
from eleanor.output.null import NullSink

from .common import TestCase


def _fake_eleanor(run_return=None):
    """Build a ``MagicMock`` that behaves like ``Eleanor`` in a ``with`` block."""
    eleanor = mock.MagicMock()
    eleanor.__enter__.return_value = eleanor
    eleanor.__exit__.return_value = None
    if run_return is None:
        run_return = [1]
    eleanor.run.return_value = run_return
    return eleanor


def _fake_executor():
    """Build an executor double that behaves as a no-op context manager."""
    executor = mock.MagicMock()
    executor.__enter__.return_value = executor
    executor.__exit__.return_value = None
    return executor


class TestCLIRun(TestCase):
    """
    Tests of the eleanor.cli.run module.
    """

    runner: CliRunner = CliRunner()

    @override
    def setUp(self) -> None:
        self.runner = CliRunner()

    def _config(self, kind: str = "multiprocessing", chunks_per_worker: int = 1) -> Config:
        return Config(
            raw={
                "output": {
                    "kind": "postgres",
                    "args": {"database": {"database": "sample"}},
                },
                "parallel": {
                    "kind": kind,
                    "chunks_per_worker": chunks_per_worker,
                },
            },
        )

    def _invoke_run(self, extra_args: list[str]):
        with self.runner.isolated_filesystem():
            _ = Path("order.yaml").write_text("order: demo\n", encoding="utf-8")
            return self.runner.invoke(main, ["run", *extra_args, "order.yaml", "10"])

    def test_run_uses_config_parallel_defaults(self):
        config = self._config(kind="serial", chunks_per_worker=6)
        eleanor = _fake_eleanor(run_return=[42])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--num-procs", "3"])

        self.assertEqual(result.exit_code, 0)
        load_executor.assert_called_once_with(kind="serial", num_workers=3)
        eleanor_cls.assert_called_once_with(config=config, kernel_args=[], executor=executor)
        eleanor.run.assert_called_once_with(
            fake_order,
            10,
            scratch=False,
            show_progress=False,
            verbose=False,
            chunks_per_worker=6,
            batch_size=None,
            max_nav_attempts=1,
            output_sink=None,
        )

    def test_run_cli_flags_override_config_parallel_values(self):
        config = self._config(kind="multiprocessing", chunks_per_worker=2)
        eleanor = _fake_eleanor(run_return=[7])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            result = self._invoke_run(
                ["-c", "/fake.yaml", "-d", "sample", "--parallel", "serial", "--chunks-per-worker", "9"]
            )

        self.assertEqual(result.exit_code, 0)
        load_executor.assert_called_once_with(kind="serial", num_workers=None)
        eleanor_cls.assert_called_once_with(config=config, kernel_args=[], executor=executor)
        self.assertEqual(eleanor.run.call_args.kwargs["chunks_per_worker"], 9)
        self.assertEqual(eleanor.run.call_args.kwargs["max_nav_attempts"], 1)

    def test_run_null_sink_overrides_output_sink(self):
        config = self._config(kind="serial", chunks_per_worker=2)
        eleanor = _fake_eleanor(run_return=[11])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch.object(NullSink, "initialize") as mock_sink_init,
            mock.patch.object(NullSink, "finalize") as mock_sink_fin,
            mock.patch("eleanor.cli.run.config_from_args", return_value=config) as config_from_args,
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "--null-sink"])

        self.assertEqual(result.exit_code, 0)
        config_from_args.assert_called_once_with("/fake.yaml", None, require_database=False)
        load_executor.assert_called_once_with(kind="serial", num_workers=None)
        eleanor_cls.assert_called_once_with(config=config, kernel_args=[], executor=executor)
        self.assertIsInstance(eleanor.run.call_args.kwargs["output_sink"], NullSink)
        mock_sink_init.assert_called_once()
        mock_sink_fin.assert_called_once()

    def test_run_max_nav_attempts_is_forwarded(self):
        config = self._config()
        eleanor = _fake_eleanor(run_return=[7])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--max-nav-attempts", "4"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(eleanor.run.call_args.kwargs["max_nav_attempts"], 4)

    def test_run_disables_progress_when_verbose(self):
        config = self._config()
        eleanor = _fake_eleanor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor"),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--progress", "--verbose"])

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(eleanor.run.call_args.kwargs["show_progress"])

    def test_run_applies_order_id_to_loaded_order(self):
        config = self._config()
        eleanor = _fake_eleanor(run_return=[321])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--order-id", "321"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(fake_order.id, 321)
        self.assertIs(eleanor.run.call_args.args[0], fake_order)

    def test_run_applies_tag_to_loaded_order(self):
        config = self._config()
        eleanor = _fake_eleanor()
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--tag", "experiment-1"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(fake_order.tag, "experiment-1")
        self.assertIs(eleanor.run.call_args.args[0], fake_order)

    def test_run_rejects_unknown_parallel_kind(self):
        config = self._config()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.available_executors", return_value={"serial"}),
            mock.patch("eleanor.cli.run.Eleanor") as eleanor_cls,
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--parallel", "does-not-exist"])

        self.assertEqual(result.exit_code, 0)
        eleanor_cls.assert_not_called()
        self.assertIn("does-not-exist", result.output)
        self.assertIn("unsupported", result.output)
        self.assertIn("executor", result.output)

    def test_run_keyboard_interrupt_exits_130_with_friendly_message(self):
        config = self._config()
        eleanor = _fake_eleanor()
        eleanor.run.side_effect = KeyboardInterrupt()
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample"])

        self.assertEqual(result.exit_code, 130)
        self.assertIn("Eleanor run interrupted by interrupt; sink finalized cleanly.", result.output)

    def test_run_bulk_load_sets_optimization_in_postgres_config(self):
        """Ensure --bulk-load injects bulk_load_optimization=True into config.output.args."""
        config = self._config()
        eleanor = _fake_eleanor(run_return=[1])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--bulk-load"])

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(config.output.args.get("bulk_load_optimization"))

    def test_run_bulk_load_rejects_non_postgres_sink(self):
        """Ensure --bulk-load errors when the configured output sink is not postgres."""
        config = Config(
            raw={
                "output": {"kind": "csv", "args": {}},
                "parallel": {"kind": "serial", "chunks_per_worker": 1},
            }
        )

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor") as eleanor_cls,
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--bulk-load"])

        self.assertEqual(result.exit_code, 0)
        eleanor_cls.assert_not_called()
        self.assertIn("--bulk-load", result.output)
        self.assertIn("postgres", result.output)

    def test_run_bulk_load_rejects_missing_output_type(self):
        """
        Ensure --bulk-load errors when output.type is None (no output sink
        configured), covering the "no output sink provided" branch.
        """
        config = Config(
            raw={
                "output": {"args": {}},
                "parallel": {"kind": "serial", "chunks_per_worker": 1},
            }
        )

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor") as eleanor_cls,
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--bulk-load"])

        self.assertEqual(result.exit_code, 0)
        eleanor_cls.assert_not_called()
        self.assertIn("--bulk-load", result.output)
        self.assertIn("no output sink provided", result.output)

    def test_run_no_bulk_load_disables_config_optimization(self):
        """
        Ensure --no-bulk-load sets bulk_load_optimization=False, allowing
        the user to override a config file that has it enabled.
        """
        config = Config(
            raw={
                "output": {
                    "kind": "postgres",
                    "args": {"database": {"database": "sample"}, "bulk_load_optimization": True},
                },
                "parallel": {"kind": "serial", "chunks_per_worker": 1},
            }
        )
        eleanor = _fake_eleanor(run_return=[1])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample", "--no-bulk-load"])

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(config.output.args.get("bulk_load_optimization"))

    def test_run_bulk_load_omitted_leaves_config_unchanged(self):
        """
        Ensure omitting --bulk-load / --no-bulk-load leaves config.output.args
        untouched, so whatever the config file says is used as-is.
        """
        config = Config(
            raw={
                "output": {
                    "kind": "postgres",
                    "args": {"database": {"database": "sample"}, "bulk_load_optimization": True},
                },
                "parallel": {"kind": "serial", "chunks_per_worker": 1},
            }
        )
        eleanor = _fake_eleanor(run_return=[1])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample"])

        self.assertEqual(result.exit_code, 0)
        # The config value must be untouched (still True as loaded from the file)
        self.assertTrue(config.output.args.get("bulk_load_optimization"))

    def test_run_bulk_load_ignored_when_null_sink(self):
        """
        Ensure --bulk-load is silently ignored when --null-sink is also
        passed, since the null sink overrides the output entirely.
        """
        config = self._config(kind="serial", chunks_per_worker=1)
        eleanor = _fake_eleanor(run_return=[5])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch.object(NullSink, "initialize"),
            mock.patch.object(NullSink, "finalize"),
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "--null-sink", "--bulk-load"])

        self.assertEqual(result.exit_code, 0)
        # bulk_load_optimization must NOT have been injected into config.output.args
        self.assertNotIn("bulk_load_optimization", config.output.args)
        # and the run must have completed (NullSink was used)
        self.assertIsInstance(eleanor.run.call_args.kwargs["output_sink"], NullSink)

    def test_run_eleanor_shutdown_uses_signal_name_in_message(self):
        """Ensure EleanorShutdown messages include the signal name and exit 130."""
        config = self._config()
        eleanor = _fake_eleanor()
        eleanor.run.side_effect = EleanorShutdown("SIGTERM")
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            result = self._invoke_run(["-c", "/fake.yaml", "-d", "sample"])

        self.assertEqual(result.exit_code, 130)
        self.assertIn("Eleanor run interrupted by SIGTERM; sink finalized cleanly.", result.output)
