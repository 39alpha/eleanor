from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor import _normalize_num_workers, available_executors, load_executor
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
    shutdown_calls: int

    def __init__(self):
        self.shutdown_calls = 0

    @property
    def num_workers(self) -> int:
        return 2

    def submit(self, fn, *args, **kwargs):
        return _Future(fn(*args, **kwargs))

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_calls += 1


class TestExecutorInterface(TestCase):
    """
    Tests of executor interface-level behavior and factory helpers.
    """

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

    def test_load_executor_serial(self):
        """
        Ensure serial executor selection returns a SerialExecutor instance.
        """
        with self.assertWarnsRegex(RuntimeWarning, "num_workers is ignored for serial executor"):
            out = load_executor(kind="serial", num_workers=8)
        self.assertIsInstance(out, SerialExecutor)

    def test_load_executor_multiprocessing_normalizes_workers(self):
        """
        Ensure multiprocessing backend passes normalized worker counts to constructor.
        """
        sentinel = _Executor()
        # The multiprocessing factory references MultiprocessingExecutor from the
        # executor package's namespace (imported at module scope in __init__.py).
        with mock.patch(
            "eleanor.executor.MultiprocessingExecutor",
            return_value=sentinel,
        ) as mp_executor:
            out = load_executor(kind="multiprocessing", num_workers=0)
        self.assertIs(out, sentinel)
        mp_executor.assert_called_once_with(num_workers=1)

    def test_load_executor_rejects_unknown_executor(self):
        """
        Ensure unsupported executor names raise EleanorException with a helpful choices list.
        """
        with self.assertRaisesRegex(EleanorException, "unsupported executor"):
            load_executor(kind="bad-backend")

    def test_load_executor_registry_contains_builtins(self):
        """
        Ensure every advertised executor name is accepted by load_executor.
        """
        live = available_executors()
        # The two built-ins must always be present; plugins (e.g. eleanor_mpi)
        # may add more.
        self.assertIn("serial", live)
        self.assertIn("multiprocessing", live)
        self.assertNotIn("bad-backend", live)

    def test_load_executor_rejects_unknown_kwargs(self):
        """
        Ensure unexpected keyword arguments to load_executor are rejected (not silently swallowed).
        """
        with self.assertRaises(TypeError):
            load_executor(kind="serial", num_worker=4)  # type: ignore[call-arg]

    def test_abstract_executor_default_supports_worker_progress(self):
        """
        Ensure AbstractExecutor advertises worker-side progress support by default.
        """
        executor = _Executor()
        self.assertTrue(executor.supports_worker_progress)
