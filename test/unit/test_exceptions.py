from eleanor.exceptions import (
    EleanorConfigurationException,
    EleanorException,
    EleanorFileException,
    EleanorParserException,
)

from .common import TestCase


class TestExceptions(TestCase):
    """
    Tests of the eleanor.exceptions module.
    """

    def test_eleonor_exception_str_and_code(self):
        """
        Ensure that :class:`EleanorException` stores error code and renders formatted text.
        """
        e = EleanorException("boom", code=7)
        self.assertEqual(e.code, 7)
        self.assertEqual(str(e), "(code: 7) boom")

        e2 = EleanorException("oops")
        self.assertIsNone(e2.code)
        self.assertEqual(str(e2), "(code: None) oops")

    def test_eleanor_file_exception_wraps_error(self):
        """
        Ensure that :class:`EleanorFileException` wraps source exceptions in its message args.
        """
        src = ValueError("file not found")
        e = EleanorFileException(src, code=3)
        self.assertEqual(e.code, 3)
        self.assertIn("file not found", str(e))

    def test_subclass_exceptions(self):
        """
        Ensure parser/configuration exception subclasses behave as EleanorException types.
        """
        p = EleanorParserException("parse")
        c = EleanorConfigurationException("config")
        self.assertIsInstance(p, EleanorException)
        self.assertIsInstance(c, EleanorException)
        self.assertEqual(str(p), "(code: None) parse")
        self.assertEqual(str(c), "(code: None) config")
