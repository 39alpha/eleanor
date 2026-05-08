from multiprocessing.pool import ApplyResult
from typing import cast
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor.interface import AbstractFuture
from eleanor.executor.multiprocessing import MultiprocessingExecutor, MultiprocessingFuture

from ..common import TestCase


class _AsyncResult:
    _value: object

    def __init__(self, value, ready=True):
        self._value = value
        self._ready = ready

    def get(self):
        return self._value

    def ready(self):
        return self._ready


class _Pool:
    def __init__(self, processes=None, initializer=None):
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
            with MultiprocessingExecutor(num_workers=4) as executor:
                future = executor.submit(lambda x, y: x + y, 5, 7)

        self.assertEqual(executor.num_workers, 4)
        self.assertEqual(future.result(), 12)

    def test_pool_is_none_before_enter(self):
        """
        Ensure __init__ does not create the pool; it is created only on __enter__.
        """
        executor = MultiprocessingExecutor(num_workers=2)
        self.assertIsNone(executor._pool)

    def test_shutdown_wait_true_closes_and_joins(self):
        """
        Ensure wait=True shutdown closes and joins the pool.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.shutdown(wait=True)
        typed_pool.close.assert_called_once()
        typed_pool.join.assert_called_once()
        typed_pool.terminate.assert_not_called()

    def test_shutdown_wait_false_terminates_pool(self):
        """
        Ensure wait=False shutdown terminates the pool.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.shutdown(wait=False)
        typed_pool.terminate.assert_called_once()
        typed_pool.close.assert_not_called()
        typed_pool.join.assert_not_called()

    def test_exit_uses_wait_false_on_keyboard_interrupt(self):
        """
        Ensure __exit__ uses wait=False when unwinding from KeyboardInterrupt.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.__exit__(KeyboardInterrupt, KeyboardInterrupt(), None)
        typed_pool.terminate.assert_called_once()
        typed_pool.close.assert_not_called()
        typed_pool.join.assert_not_called()

    def test_exit_uses_wait_true_on_normal_exit(self):
        """
        Ensure __exit__ uses wait=True on normal exit.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.__exit__(None, None, None)
        typed_pool.close.assert_called_once()
        typed_pool.join.assert_called_once()
        typed_pool.terminate.assert_not_called()

    def test_submit_after_shutdown_raises(self):
        """
        Ensure submit fails once the executor has been shut down.
        """
        with mock.patch("eleanor.executor.multiprocessing.Pool", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()
        executor.shutdown(wait=True)
        with self.assertRaises(EleanorException):
            executor.submit(lambda x: x, 1)

    def test_pop_completed_future_prefers_ready_futures(self):
        """
        Ensure pop_completed_future returns a ready future before earlier
        non-ready entries in the same queue.
        """
        executor = MultiprocessingExecutor(num_workers=2)
        slow = MultiprocessingFuture(cast(ApplyResult[int], cast(object, _AsyncResult(1, ready=False))))
        ready = MultiprocessingFuture(cast(ApplyResult[int], cast(object, _AsyncResult(2, ready=True))))
        futures: list[AbstractFuture[int]] = [slow, ready]

        popped = executor.pop_completed_future(futures)

        self.assertIs(popped, ready)
        self.assertEqual(futures, [slow])
