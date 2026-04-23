from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.transformer import (
    BUILTIN_TRANSFORMERS,
    available_transformers,
    get_factory,
    register_transformer,
)
from eleanor.transformer.registry import registry

from .common import TestCase


class _TransformerRegistryTestCase(TestCase):

    def setUp(self) -> None:
        self._saved_entries = dict(registry._registry)
        self._saved_discovered = registry._discovered

    def tearDown(self) -> None:
        registry._registry.clear()
        registry._registry.update(self._saved_entries)
        registry._discovered = self._saved_discovered


class TestBuiltinTransformers(TestCase):
    """
    Sanity checks on the built-in transformer set.
    """

    def test_no_builtin_transformers_are_shipped(self):
        """
        Ensure the built-in transformer set is empty.
        """
        self.assertEqual(BUILTIN_TRANSFORMERS, frozenset())
        self.assertEqual(BUILTIN_TRANSFORMERS.intersection(available_transformers()), frozenset())


class TestRegisterTransformer(_TransformerRegistryTestCase):
    """
    Tests of :func:`register_transformer`.
    """

    def test_register_and_retrieve(self):
        """
        Ensure a plugin factory can be registered and retrieved by name.
        """

        def factory(**_args):
            return mock.Mock()

        register_transformer('plugin', factory)
        self.assertIs(get_factory('plugin'), factory)
        self.assertIn('plugin', available_transformers())

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory('nope')
