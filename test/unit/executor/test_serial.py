from unittest import TestCase

from eleanor.executor.serial import SerialExecutor
from eleanor.executor.settings import ExecutorSettings


class TestSerialExecutor(TestCase):
    """
    Tests of the serial executor backend.
    """

    def test_submit_returns_immediate_future(self):
        """
        Ensure submit executes immediately and returns a resolved future.
        """

        def work(x: int, y: int) -> int:
            return x + y

        executor = SerialExecutor(settings=ExecutorSettings())
        future = executor.submit(work, 2, 3)
        self.assertEqual(executor.num_workers, 1)
        self.assertEqual(future.result(), 5)
