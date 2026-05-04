from eleanor.kernel.eq36.codes import RunCode

from ...common import TestCase


class TestEq36Codes(TestCase):
    """
    Tests of the eleanor.kernel.eq36.codes module.
    """

    def test_run_code_string_rendering(self):
        """
        Ensure known run codes render to expected status messages.
        """
        self.assertEqual(str(RunCode.NOT_RUN), "not run")
        self.assertEqual(str(RunCode.SUCCESS), "success")
        self.assertEqual(str(RunCode.EQPT_ERROR), "eqpt failed with an error")
        self.assertEqual(str(RunCode.EQ36_TIMEOUT), "eq36 timed out")

    def test_run_code_missing_string_mapping(self):
        """
        Ensure unmapped enum values surface as TypeError due non-string __str__ return.
        """
        with self.assertRaises(TypeError):
            str(RunCode.EQ3_EARLY_TERMINATION)
