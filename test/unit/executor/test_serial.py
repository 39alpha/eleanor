from eleanor.executor.serial import SerialExecutor

from ..common import TestCase


class TestSerialExecutor(TestCase):
    """
    Tests of the serial executor backend.
    """

    def test_submit_returns_immediate_future(self):
        """
        Ensure submit executes immediately and returns a resolved future.
        """
        executor = SerialExecutor()
        future = executor.submit(lambda x, y: x + y, 2, 3)
        self.assertEqual(executor.num_workers, 1)
        self.assertEqual(future.result(), 5)
