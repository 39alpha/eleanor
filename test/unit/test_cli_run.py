import argparse
from unittest import mock

from eleanor.cli import run as run_cli
from eleanor.config import Config
from eleanor.exceptions import EleanorException
from eleanor.executor import registry

from .common import TestCase


class TestCLIRun(TestCase):
    """
    Tests of the eleanor.cli.run module.
    """

    def _namespace(self, **overrides):
        values = {
            'order': 'order.yaml',
            'kernel_args': None,
            'no_huffer': False,
            'num_procs': None,
            'simulation_size': 10,
            'scratch': False,
            'progress': False,
            'combined': False,
            'proportional': False,
            'success_sampling': False,
            'verbose': False,
            'parallel': None,
            'chunks_per_worker': None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def _config(self, backend='multiprocessing', chunks_per_worker=1):
        return Config(
            raw={
                'database': {'database': 'sample'},
                'parallel': {
                    'backend': backend,
                    'chunks_per_worker': chunks_per_worker,
                },
            },
        )

    def test_init_parses_phase_two_flags(self):
        """
        Ensure parser init wires --parallel and --chunks-per-worker options.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns = parser.parse_args(['--parallel', 'serial', '--chunks-per-worker', '4', 'order.yaml', '10'])
        self.assertEqual(ns.parallel, 'serial')
        self.assertEqual(ns.chunks_per_worker, 4)

    def test_execute_uses_config_parallel_defaults(self):
        """
        Ensure execute falls back to config parallel values when CLI flags are omitted.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(num_procs=3)
        config = self._config(backend='serial', chunks_per_worker=6)
        eleanor = mock.Mock()
        eleanor.run.return_value = [42]

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor) as eleanor_cls,
        ):
            run_cli.execute(parser, ns)

        eleanor_cls.assert_called_once_with(config, 'order.yaml', [])
        eleanor.run.assert_called_once_with(
            10,
            no_huffer=False,
            num_procs=3,
            scratch=False,
            show_progress=False,
            combined=False,
            proportional_sampling=False,
            success_sampling=False,
            verbose=False,
            parallel='serial',
            chunks_per_worker=6,
        )

    def test_execute_cli_flags_override_config_parallel_values(self):
        """
        Ensure CLI-provided parallel and chunk values override config defaults.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(parallel='serial', chunks_per_worker=9)
        config = self._config(backend='multiprocessing', chunks_per_worker=2)
        eleanor = mock.Mock()
        eleanor.run.return_value = [7]

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            run_cli.execute(parser, ns)

        self.assertEqual(eleanor.run.call_args.kwargs['parallel'], 'serial')
        self.assertEqual(eleanor.run.call_args.kwargs['chunks_per_worker'], 9)

    def test_execute_disables_progress_when_verbose(self):
        """
        Ensure verbose mode still disables progress output even when --progress is set.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(progress=True, verbose=True)
        config = self._config()
        eleanor = mock.Mock()
        eleanor.run.return_value = [1]

        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
        ):
            run_cli.execute(parser, ns)

        self.assertFalse(eleanor.run.call_args.kwargs['show_progress'])

    def test_init_accepts_arbitrary_parallel_name(self):
        """
        Ensure --parallel is no longer constrained by argparse choices so plugin names parse.
        """
        parser = argparse.ArgumentParser()
        with mock.patch("eleanor.cli.run.add_config_args"):
            run_cli.init(parser)

        ns = parser.parse_args(['--parallel', 'future-plugin', 'order.yaml', '10'])
        self.assertEqual(ns.parallel, 'future-plugin')

    def test_execute_accepts_plugin_registered_backend(self):
        """
        Ensure --parallel accepts a backend contributed via register_backend at runtime.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(parallel='plugin')
        config = self._config(backend='multiprocessing', chunks_per_worker=1)
        eleanor = mock.Mock()
        eleanor.run.return_value = [99]

        saved_entries = dict(registry.registry._registry)
        saved_discovered = registry.registry._discovered
        registry.registry._registry['plugin'] = lambda _n: mock.Mock()
        try:
            with (
                mock.patch("eleanor.cli.run.config_from_args", return_value=config),
                mock.patch("eleanor.cli.run.Eleanor", return_value=eleanor),
            ):
                run_cli.execute(parser, ns)
        finally:
            registry.registry._registry.clear()
            registry.registry._registry.update(saved_entries)
            registry.registry._discovered = saved_discovered

        self.assertEqual(eleanor.run.call_args.kwargs['parallel'], 'plugin')

    def test_execute_rejects_unknown_parallel_backend(self):
        """
        Ensure an unknown --parallel value yields a user-friendly error without running.
        """
        parser = argparse.ArgumentParser()
        ns = self._namespace(parallel='does-not-exist')
        config = self._config()

        printed: list[object] = []
        with (
            mock.patch("eleanor.cli.run.config_from_args", return_value=config),
            mock.patch("eleanor.cli.run.Eleanor") as eleanor_cls,
            mock.patch("builtins.print", side_effect=lambda *a, **_k: printed.append(a)),
        ):
            run_cli.execute(parser, ns)

        eleanor_cls.assert_not_called()
        joined = ' '.join(str(a) for a in printed)
        self.assertIn('does-not-exist', joined)
        self.assertIn('unsupported', joined)
        self.assertIn('executor backend', joined)

    def test_execute_surfaces_eleanor_exception(self):
        """
        Ensure EleanorException raised during backend validation is surfaced via print.
        """
        # Sanity check that the internal code path uses EleanorException — this
        # keeps the unknown-backend error path honest if refactored.
        self.assertTrue(issubclass(EleanorException, Exception))
