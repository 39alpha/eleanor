from concurrent.futures import FIRST_COMPLETED, Future
from typing import cast
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor.interface import AbstractFuture
from eleanor.executor.multiprocessing import MultiprocessingExecutor, MultiprocessingFuture

from ..common import TestCase


class _Pool:
    def __init__(self, max_workers=None, initializer=None):
        self.shutdown = mock.Mock()
        self._processes: dict[int, mock.Mock] = {1: mock.Mock(), 2: mock.Mock()}

    def submit(self, fn, *args, **kwargs):
        future = Future()
        future.set_result(fn(*args, **kwargs))
        return future


class TestMultiprocessingExecutor(TestCase):
    """
    Tests of the multiprocessing executor backend.
    """

    def test_submit_and_result(self):
        """
        Ensure submit delegates to submit and returned futures resolve via result().
        """
        with mock.patch("eleanor.executor.multiprocessing.ProcessPoolExecutor", _Pool):
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

    def test_shutdown_wait_true_delegates_to_pool_shutdown(self):
        """
        Ensure wait=True shutdown delegates to ProcessPoolExecutor.shutdown.
        """
        with mock.patch("eleanor.executor.multiprocessing.ProcessPoolExecutor", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.shutdown(wait=True)
        typed_pool.shutdown.assert_called_once_with(wait=True, cancel_futures=False)

    def test_shutdown_wait_false_terminates_pool(self):
        """
        Ensure wait=False shutdown terminates workers and requests non-blocking shutdown.
        """
        with mock.patch("eleanor.executor.multiprocessing.ProcessPoolExecutor", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.shutdown(wait=False)
        for process in typed_pool._processes.values():
            process.terminate.assert_called_once()
        typed_pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)

    def test_exit_uses_wait_false_on_keyboard_interrupt(self):
        """
        Ensure __exit__ uses wait=False when unwinding from KeyboardInterrupt.
        """
        with mock.patch("eleanor.executor.multiprocessing.ProcessPoolExecutor", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.__exit__(KeyboardInterrupt, KeyboardInterrupt(), None)
        for process in typed_pool._processes.values():
            process.terminate.assert_called_once()
        typed_pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)

    def test_exit_uses_wait_true_on_normal_exit(self):
        """
        Ensure __exit__ uses wait=True on normal exit.
        """
        with mock.patch("eleanor.executor.multiprocessing.ProcessPoolExecutor", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()

        pool = executor._pool
        self.assertIsNotNone(pool)
        typed_pool = cast(_Pool, cast(object, pool))
        executor.__exit__(None, None, None)
        typed_pool.shutdown.assert_called_once_with(wait=True, cancel_futures=False)

    def test_submit_after_shutdown_raises(self):
        """
        Ensure submit fails once the executor has been shut down.
        """
        with mock.patch("eleanor.executor.multiprocessing.ProcessPoolExecutor", _Pool):
            executor = MultiprocessingExecutor(num_workers=2)
            executor.__enter__()
        executor.shutdown(wait=True)
        with self.assertRaises(EleanorException):
            executor.submit(lambda x: x, 1)

    def test_pop_completed_future_uses_event_driven_wait(self):
        """
        Ensure pop_completed_future waits for FIRST_COMPLETED and pops a completed future.
        """
        executor = MultiprocessingExecutor(num_workers=2)
        slow_inner: Future[int] = Future()
        ready_inner: Future[int] = Future()
        ready_inner.set_result(2)
        slow = MultiprocessingFuture(slow_inner)
        ready = MultiprocessingFuture(ready_inner)
        futures: list[AbstractFuture[int]] = [slow, ready]
        done: set[Future[int]] = {ready_inner}
        with mock.patch(
            "eleanor.executor.multiprocessing.futures_wait",
            return_value=(done, {slow_inner}),
        ) as wait_mock:
            popped = executor.pop_completed_future(futures)
        wait_mock.assert_called_once_with(
            [slow.inner, ready.inner],
            return_when=FIRST_COMPLETED,
        )
        self.assertIs(popped, ready)
        self.assertEqual(futures, [slow])

    def test_pop_completed_future_falls_back_for_mixed_future_types(self):
        """
        Ensure pop_completed_future delegates to the base-class busy-poll when
        the futures list contains non-MultiprocessingFuture entries.
        """
        executor = MultiprocessingExecutor(num_workers=2)
        foreign: AbstractFuture[int] = cast(
            AbstractFuture[int],
            cast(object, type("Fake", (), {"result": lambda self: 1, "ready": lambda self: True})()),
        )
        futures: list[AbstractFuture[int]] = [foreign]
        popped = executor.pop_completed_future(futures)
        self.assertIs(popped, foreign)
        self.assertEqual(futures, [])
