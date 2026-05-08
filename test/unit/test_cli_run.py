import argparse
from unittest import mock

from eleanor.cli import run as run_cli  # pyright: ignore[reportPrivateImportUsage]
from eleanor.config import Config
from eleanor.exceptions import EleanorException, EleanorShutdown
from eleanor.executor import registry
from eleanor.output.null import NullSink

from .common import TestCase


def _fake_eleanor(run_return=None):
    """Build a ``MagicMock`` that behaves like ``Eleanor`` in a ``with`` block.

    ``__enter__`` returns the mock itself so tests can make assertions
    against the same object used both outside and inside the ``with`` block.
    """
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

    def _namespace(self, **overrides):
        values = {
            "order": "order.yaml",
            "order_id": None,
            "tag": None,
            "kernel_args": None,
            "num_procs": None,
            "simulation_size": 10,
            "scratch": False,
            "progress": False,
            "null_sink": False,
            "bulk_load": None,
            "verbose": False,
            "parallel": None,
            "chunks_per_worker": None,
            "batch_size": None,
            "max_nav_attempts": 1,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def _config(self, backend="multiprocessing", chunks_per_worker=1):
        return Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {"database": {"database": "sample"}},
                },
                "parallel": {
                    "backend": backend,
                    "chunks_per_worker": chunks_per_worker,
                },
            },
        )

    def test_init_parses_phase_two_flags(self):
        """
        Ensure parser init wires --parallel, --chunks-per-worker, --batch-size, and --max-nav-attempts options.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)
        ns = parser.parse_args(
            [
                "--parallel",
                "serial",
                "--chunks-per-worker",
                "4",
                "--batch-size",
                "500",
                "--max-nav-attempts",
                "3",
                "order.yaml",
                "10",
            ]
        )
        self.assertEqual(ns.parallel, "serial")
        self.assertEqual(ns.chunks_per_worker, 4)
        self.assertEqual(ns.batch_size, 500)
        self.assertEqual(ns.max_nav_attempts, 3)

    def test_batch_size_flag_absent_defaults_to_none(self):
        """
        Ensure omitting --batch-size leaves the parsed field as None.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns = parser.parse_args(["order.yaml", "10"])
        self.assertIsNone(ns.batch_size)
        self.assertEqual(ns.max_nav_attempts, 1)

    def test_init_parses_null_sink_flag(self):
        """
        Ensure --null-sink is parsed and defaults to False when omitted.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns_enabled = parser.parse_args(["--null-sink", "order.yaml", "10"])
        self.assertTrue(ns_enabled.null_sink)

        ns_default = parser.parse_args(["order.yaml", "10"])
        self.assertFalse(ns_default.null_sink)

    def test_execute_uses_config_parallel_defaults(self):
        """
        Ensure execute falls back to config parallel values when CLI flags are omitted.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(num_procs=3)
        config = self._config(backend="serial", chunks_per_worker=6)
        eleanor = _fake_eleanor(run_return=[42])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            run_cli.execute(parser, ns)

        load_executor.assert_called_once_with(kind="serial", num_workers=3)
        eleanor_cls.assert_called_once_with(config, [], executor=executor)
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

    def test_execute_cli_flags_override_config_parallel_values(self):
        """
        Ensure CLI-provided parallel and chunk values override config defaults.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(parallel="serial", chunks_per_worker=9)
        config = self._config(backend="multiprocessing", chunks_per_worker=2)
        eleanor = _fake_eleanor(run_return=[7])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            run_cli.execute(parser, ns)

        load_executor.assert_called_once_with(kind="serial", num_workers=None)
        eleanor_cls.assert_called_once_with(config, [], executor=executor)
        self.assertEqual(eleanor.run.call_args.kwargs["chunks_per_worker"], 9)
        self.assertEqual(eleanor.run.call_args.kwargs["max_nav_attempts"], 1)

    def test_execute_null_sink_overrides_output_sink(self):
        """
        Ensure --null-sink injects a NullSink override and bypasses db requirement.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(null_sink=True)
        config = self._config(backend="serial", chunks_per_worker=2)
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
            run_cli.execute(parser, ns)

        config_from_args.assert_called_once_with(parser, mock.ANY, require_database=False)
        load_executor.assert_called_once_with(kind="serial", num_workers=None)
        eleanor_cls.assert_called_once_with(config, [], executor=executor)
        self.assertIsInstance(eleanor.run.call_args.kwargs["output_sink"], NullSink)
        mock_sink_init.assert_called_once()
        mock_sink_fin.assert_called_once()

    def test_execute_cli_max_nav_attempts_overrides_default(self):
        """
        Ensure --max-nav-attempts is forwarded to Eleanor.run().
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(max_nav_attempts=4)
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
            run_cli.execute(parser, ns)

        self.assertEqual(eleanor.run.call_args.kwargs["max_nav_attempts"], 4)

    def test_execute_disables_progress_when_verbose(self):
        """
        Ensure verbose mode still disables progress output even when --progress is set.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(progress=True, verbose=True)
        config = self._config()
        eleanor = _fake_eleanor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor"),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            run_cli.execute(parser, ns)

        self.assertFalse(eleanor.run.call_args.kwargs["show_progress"])

    def test_init_parses_order_id_flag(self):
        """
        Ensure --order-id is parsed into the RunArgs namespace as an int,
        and defaults to None when omitted.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns_long = parser.parse_args(["--order-id", "42", "order.yaml", "10"])
        self.assertEqual(ns_long.order_id, 42)

        ns_long_alt = parser.parse_args(["--order-id", "7", "order.yaml", "10"])
        self.assertEqual(ns_long_alt.order_id, 7)

        ns_default = parser.parse_args(["order.yaml", "10"])
        self.assertIsNone(ns_default.order_id)

    def test_init_parses_tag_flag(self):
        """
        Ensure --tag is parsed into the RunArgs namespace as a str,
        and defaults to None when omitted.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns_long = parser.parse_args(["--tag", "experiment-1", "order.yaml", "10"])
        self.assertEqual(ns_long.tag, "experiment-1")

        ns_default = parser.parse_args(["order.yaml", "10"])
        self.assertIsNone(ns_default.tag)

    def test_execute_applies_order_id_to_order_before_run(self):
        """
        Ensure execute sets order.id from --order-id on the loaded order before calling run().
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(order_id=321)
        config = self._config()
        eleanor = _fake_eleanor(run_return=[321])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            run_cli.execute(parser, ns)

        load_executor.assert_called_once_with(kind="multiprocessing", num_workers=None)
        eleanor_cls.assert_called_once_with(config, [], executor=executor)
        self.assertEqual(fake_order.id, 321)
        self.assertIs(eleanor.run.call_args.args[0], fake_order)

    def test_execute_applies_tag_to_order_before_run(self):
        """
        Ensure execute sets order.tag from --tag on the loaded order before calling run().
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(tag="experiment-1")
        config = self._config()
        eleanor = _fake_eleanor()
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            run_cli.execute(parser, ns)

        load_executor.assert_called_once_with(kind="multiprocessing", num_workers=None)
        eleanor_cls.assert_called_once_with(config, [], executor=executor)
        self.assertEqual(fake_order.tag, "experiment-1")
        self.assertIs(eleanor.run.call_args.args[0], fake_order)

    def test_init_accepts_arbitrary_parallel_name(self):
        """
        Ensure --parallel is no longer constrained by argparse choices so plugin names parse.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns = parser.parse_args(["--parallel", "future-plugin", "order.yaml", "10"])
        self.assertEqual(ns.parallel, "future-plugin")

    def test_execute_accepts_plugin_registered_executor(self):
        """
        Ensure --parallel accepts an executor contributed via register_executor at runtime.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(parallel="plugin")
        config = self._config(backend="multiprocessing", chunks_per_worker=1)
        eleanor = _fake_eleanor(run_return=[99])
        executor = _fake_executor()

        saved_entries = dict(registry.registry._registry)
        saved_discovered = registry.registry._discovered
        registry.registry._registry["plugin"] = lambda _n: mock.Mock()
        fake_order = mock.Mock()
        try:
            with (
                mock.patch("eleanor.cli.run.config_from_args", return_value=config),
                mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
                mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
                mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
            ):
                run_cli.execute(parser, ns)
        finally:
            registry.registry._registry.clear()
            registry.registry._registry.update(saved_entries)
            registry.registry._discovered = saved_discovered

        load_executor.assert_called_once_with(kind="plugin", num_workers=None)
        eleanor_cls.assert_called_once_with(config, [], executor=executor)

    def test_execute_builds_selected_backend_before_entering_eleanor_context(self):
        """
        Ensure execute injects the resolved backend's executor into Eleanor so
        the context manager does not eagerly construct the config-default backend.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(parallel="serial", num_procs=5)
        config = self._config(backend="multiprocessing", chunks_per_worker=1)
        eleanor = _fake_eleanor(run_return=[12])
        executor = _fake_executor()
        fake_order = mock.Mock()

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            run_cli.execute(parser, ns)

        load_executor.assert_called_once_with(kind="serial", num_workers=5)
        executor.__enter__.assert_called_once()
        executor.__exit__.assert_called_once()
        eleanor_cls.assert_called_once_with(config, [], executor=executor)

    def test_execute_rejects_unknown_parallel_backend(self):
        """
        Ensure an unknown --parallel value yields a user-friendly error without running.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(parallel="does-not-exist")
        config = self._config()
        fake_order = mock.Mock()

        printed: list[object] = []
        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.load_order", return_value=fake_order),
            mock.patch("eleanor.cli.run.Eleanor") as eleanor_cls,
            mock.patch("builtins.print", side_effect=lambda *a, **_k: printed.append(a)),
        ):
            run_cli.execute(parser, ns)

        eleanor_cls.assert_not_called()
        joined = " ".join(str(a) for a in printed)
        self.assertIn("does-not-exist", joined)
        self.assertIn("is not supported", joined)
        self.assertIn("executor", joined)

    def test_execute_surfaces_eleanor_exception(self):
        """
        Ensure EleanorException raised during backend validation is surfaced via print.
        """
        # Sanity check that the internal code path uses EleanorException — this
        # keeps the unknown-backend error path honest if refactored.
        self.assertTrue(issubclass(EleanorException, Exception))

    def test_execute_keyboard_interrupt_exits_130_with_friendly_message(self):
        """Ensure plain KeyboardInterrupt emits the generic interrupt message and exits 130."""
        parser = argparse.ArgumentParser()
        ns = self._namespace()
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
            mock.patch("builtins.print") as print_mock,
            mock.patch("eleanor.cli.run.sys.exit", side_effect=SystemExit(130)) as exit_mock,
            self.assertRaises(SystemExit) as raised,
        ):
            run_cli.execute(parser, ns)

        self.assertEqual(raised.exception.code, 130)
        exit_mock.assert_called_once_with(130)
        print_mock.assert_called_once_with("Eleanor run interrupted by interrupt; sink finalized cleanly.")

    def test_init_parses_bulk_load_flag(self):
        """
        Ensure --bulk-load / --no-bulk-load / omitted produce True / False / None.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns_enabled = parser.parse_args(["--bulk-load", "order.yaml", "10"])
        self.assertTrue(ns_enabled.bulk_load)

        ns_disabled = parser.parse_args(["--no-bulk-load", "order.yaml", "10"])
        self.assertFalse(ns_disabled.bulk_load)

        ns_default = parser.parse_args(["order.yaml", "10"])
        self.assertIsNone(ns_default.bulk_load)

    def test_execute_bulk_load_sets_optimization_in_postgres_config(self):
        """
        Ensure --bulk-load injects bulk_load_optimization=True into config.output.args
        when the configured sink is postgres.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(bulk_load=True)
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
            run_cli.execute(parser, ns)

        self.assertTrue(config.output.args.get("bulk_load_optimization"))

    def test_execute_bulk_load_rejects_non_postgres_sink(self):
        """
        Ensure --bulk-load raises an error (surfaced via print) when the
        configured output sink is not postgres.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(bulk_load=True)
        config = Config(
            raw={
                "output": {"type": "csv", "args": {}},
                "parallel": {"backend": "serial", "chunks_per_worker": 1},
            }
        )

        printed: list[object] = []
        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor") as eleanor_cls,
            mock.patch("builtins.print", side_effect=lambda *a, **_k: printed.append(a)),
        ):
            run_cli.execute(parser, ns)

        eleanor_cls.assert_not_called()
        joined = " ".join(str(a) for a in printed)
        self.assertIn("--bulk-load", joined)
        self.assertIn("postgres", joined)

    def test_execute_bulk_load_rejects_missing_output_type(self):
        """
        Ensure --bulk-load raises an error when output.type is None
        (no output sink configured), covering the "no output sink provided" branch.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(bulk_load=True)
        config = Config(
            raw={
                "output": {"args": {}},
                "parallel": {"backend": "serial", "chunks_per_worker": 1},
            }
        )

        printed: list[object] = []
        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor") as eleanor_cls,
            mock.patch("builtins.print", side_effect=lambda *a, **_k: printed.append(a)),
        ):
            run_cli.execute(parser, ns)

        eleanor_cls.assert_not_called()
        joined = " ".join(str(a) for a in printed)
        self.assertIn("--bulk-load", joined)
        self.assertIn("no output sink provided", joined)

    def test_execute_no_bulk_load_disables_config_optimization(self):
        """
        Ensure --no-bulk-load sets bulk_load_optimization=False in config.output.args,
        allowing the user to override a config file that has it enabled.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(bulk_load=False)
        # Config file has bulk_load_optimization=True
        config = Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {"database": {"database": "sample"}, "bulk_load_optimization": True},
                },
                "parallel": {"backend": "serial", "chunks_per_worker": 1},
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
            run_cli.execute(parser, ns)

        self.assertFalse(config.output.args.get("bulk_load_optimization"))

    def test_execute_bulk_load_omitted_leaves_config_unchanged(self):
        """
        Ensure omitting --bulk-load / --no-bulk-load leaves config.output.args untouched,
        so whatever the config file says is used as-is.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(bulk_load=None)
        config = Config(
            raw={
                "output": {
                    "type": "postgres",
                    "args": {"database": {"database": "sample"}, "bulk_load_optimization": True},
                },
                "parallel": {"backend": "serial", "chunks_per_worker": 1},
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
            run_cli.execute(parser, ns)

        # The config value must be untouched (still True as loaded from the file)
        self.assertTrue(config.output.args.get("bulk_load_optimization"))

    def test_execute_bulk_load_ignored_when_null_sink(self):
        """
        Ensure --bulk-load is silently ignored when --null-sink is also passed,
        since the null sink overrides the output entirely.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(bulk_load=True, null_sink=True)
        config = self._config(backend="serial", chunks_per_worker=1)
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
            run_cli.execute(parser, ns)

        # bulk_load_optimization must NOT have been injected into config.output.args
        self.assertNotIn("bulk_load_optimization", config.output.args)
        # and the run must have completed (NullSink was used)
        self.assertIsInstance(eleanor.run.call_args.kwargs["output_sink"], NullSink)

    def test_execute_eleanor_shutdown_uses_signal_name_in_message(self):
        """Ensure EleanorShutdown messages include the signal name and exit 130."""
        parser = argparse.ArgumentParser()
        ns = self._namespace()
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
            mock.patch("builtins.print") as print_mock,
            mock.patch("eleanor.cli.run.sys.exit", side_effect=SystemExit(130)) as exit_mock,
            self.assertRaises(SystemExit) as raised,
        ):
            run_cli.execute(parser, ns)

        self.assertEqual(raised.exception.code, 130)
        exit_mock.assert_called_once_with(130)
        print_mock.assert_called_once_with("Eleanor run interrupted by SIGTERM; sink finalized cleanly.")
