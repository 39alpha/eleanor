from eleanor.exceptions import EleanorException
from eleanor.kernel.eq36.exceptions import Eq36Exception
from eleanor.kernel.exceptions import EleanorKernelException

from ...common import TestCase


class TestEq36Exceptions(TestCase):
    """
    Tests of the eleanor.kernel.eq36.exceptions module.
    """

    def test_eq36_exception_inheritance_and_formatting(self):
        """
        Ensure Eq36Exception preserves Eleanor exception inheritance and string formatting.
        """
        e = Eq36Exception("eq36 failed", code=29)
        self.assertIsInstance(e, EleanorException)
        self.assertIsInstance(e, EleanorKernelException)
        self.assertEqual(e.code, 29)
        self.assertEqual(str(e), "(code: 29) eq36 failed")
