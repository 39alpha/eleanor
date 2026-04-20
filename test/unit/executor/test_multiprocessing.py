from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor.multiprocessing import MultiprocessingExecutor

from ..common import TestCase


class _AsyncResult:
    _value: object

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _Pool:
    def __init__(self, processes=None):
        self.close = mock.Mock()
        self.join = mock.Mock()
        self.terminate = mock.Mock()

    def apply_async(self, fn, args, kwargs):
        return _AsyncResult(fn(*args, **kwargs))


class TestMultiprocessingExecutor(TestCase):
    """
    Tests of the multiprocessing executor backend.
    """

    def test_submit_and_result(self):
        """
        Ensure submit delegates to apply_async and returned futures resolve via result().
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=4)
            future = executor.submit(lambda x, y: x + y, 5, 7)

        self.assertEqual(executor.num_workers, 4)
        self.assertEqual(future.result(), 12)

    def test_shutdown_wait_true_closes_and_joins(self):
        """
        Ensure wait=True shutdown closes and joins the pool.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)

        pool = executor._pool
        self.assertIsNotNone(pool)
        executor.shutdown(wait=True)
        pool.close.assert_called_once()
        pool.join.assert_called_once()
        pool.terminate.assert_not_called()

    def test_shutdown_wait_false_terminates_pool(self):
        """
        Ensure wait=False shutdown terminates the pool.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)

        pool = executor._pool
        self.assertIsNotNone(pool)
        executor.shutdown(wait=False)
        pool.terminate.assert_called_once()
        pool.close.assert_not_called()
        pool.join.assert_not_called()

    def test_submit_after_shutdown_raises(self):
        """
        Ensure submit fails once the executor has been shut down.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
        executor.shutdown(wait=True)
        with self.assertRaises(EleanorException):
            executor.submit(lambda x: x, 1)
