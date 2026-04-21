from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor import available_backends, build_executor
from eleanor.executor.backends import SUPPORTED_BACKENDS, supported_backends
from eleanor.executor.registry import _normalize_num_workers
from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.serial import SerialExecutor

from ..common import TestCase


class _Future(AbstractFuture):
    _value: object

    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


class _Executor(AbstractExecutor):
    submitted: list[tuple]
    shutdown_calls: int

    def __init__(self):
        self.submitted = []
        self.shutdown_calls = 0

    @property
    def num_workers(self) -> int:
        return 2

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args, kwargs))
        return _Future(fn(*args, **kwargs))

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_calls += 1


class TestExecutorInterface(TestCase):
    """
    Tests of executor interface-level behavior and factory helpers.
    """

    def test_default_map_uses_submit_and_result(self):
        """
        Ensure the default map implementation delegates through submit/result.
        """
        executor = _Executor()
        values = list(executor.map(lambda x: x * 2, [1, 2, 3]))
        self.assertEqual(values, [2, 4, 6])
        self.assertEqual(len(executor.submitted), 3)

    def test_context_manager_calls_shutdown(self):
        """
        Ensure AbstractExecutor context-manager exit calls shutdown.
        """
        executor = _Executor()
        with executor as active:
            self.assertIs(active, executor)
        self.assertEqual(executor.shutdown_calls, 1)

    def test_normalize_num_workers(self):
        """
        Ensure worker-count normalization preserves None and clamps non-positive values.
        """
        self.assertIsNone(_normalize_num_workers(None))
        self.assertEqual(_normalize_num_workers(0), 1)
        self.assertEqual(_normalize_num_workers(-8), 1)
        self.assertEqual(_normalize_num_workers(5), 5)

    def test_build_executor_serial(self):
        """
        Ensure serial backend selection returns a SerialExecutor instance.
        """
        with self.assertWarnsRegex(RuntimeWarning, 'num_workers is ignored for serial backend'):
            out = build_executor(kind='serial', num_workers=8)
        self.assertIsInstance(out, SerialExecutor)

    def test_build_executor_multiprocessing_normalizes_workers(self):
        """
        Ensure multiprocessing backend passes normalized worker counts to constructor.
        """
        sentinel = object()
        # The multiprocessing factory resolves MultiprocessingExecutor from its
        # source module on each call, so patch it there.
        with mock.patch(
            "eleanor.executor.multiprocessing.MultiprocessingExecutor",
            return_value=sentinel,
        ) as mp_executor:
            out = build_executor(kind='multiprocessing', num_workers=0)
        self.assertIs(out, sentinel)
        mp_executor.assert_called_once_with(num_workers=1)

    def test_build_executor_rejects_unknown_backend(self):
        """
        Ensure unsupported backend names raise EleanorException with a helpful choices list.
        """
        with self.assertRaisesRegex(EleanorException, 'unsupported executor backend'):
            build_executor(kind='bad-backend')

    def test_build_executor_registry_matches_supported_backends(self):
        """
        Ensure every advertised backend name is accepted by build_executor.

        This guards against drift between the supported-backends surface
        (``supported_backends()`` / ``SUPPORTED_BACKENDS``) and the live
        registry queried by ``available_backends()``.
        """
        live = available_backends()
        # The two built-ins must always be present; plugins (e.g. eleanor_mpi)
        # may add more.
        self.assertIn('serial', live)
        self.assertIn('multiprocessing', live)
        self.assertNotIn('bad-backend', live)
        # The backends shim and the registry must agree.
        self.assertEqual(supported_backends(), live)
        self.assertEqual(SUPPORTED_BACKENDS, live)

    def test_build_executor_rejects_unknown_kwargs(self):
        """
        Ensure unexpected keyword arguments to build_executor are rejected (not silently swallowed).
        """
        with self.assertRaises(TypeError):
            build_executor(kind='serial', num_worker=4)  # type: ignore[call-arg]

    def test_abstract_executor_default_supports_worker_progress(self):
        """
        Ensure AbstractExecutor advertises worker-side progress support by default.
        """
        executor = _Executor()
        self.assertTrue(executor.supports_worker_progress)
