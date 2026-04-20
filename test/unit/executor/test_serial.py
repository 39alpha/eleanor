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

    def test_map_runs_functions_in_order(self):
        """
        Ensure map preserves item order for serial execution.
        """
        executor = SerialExecutor()
        out = list(executor.map(lambda x: x * x, [1, 2, 3, 4]))
        self.assertEqual(out, [1, 4, 9, 16])
