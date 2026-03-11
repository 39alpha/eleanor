from eleanor.exceptions import EleanorException
from eleanor.kernel.exceptions import EleanorKernelException

from ..common import TestCase


class TestKernelExceptions(TestCase):
    """
    Tests of the eleanor.kernel.exceptions module.
    """

    def test_eleanor_kernel_exception_is_eleonor_exception(self):
        """
        Ensure kernel exception subclasses inherit EleanorException behavior.
        """
        e = EleanorKernelException("kernel boom", code=12)
        self.assertIsInstance(e, EleanorException)
        self.assertEqual(e.code, 12)
        self.assertEqual(str(e), "(code: 12) kernel boom")
