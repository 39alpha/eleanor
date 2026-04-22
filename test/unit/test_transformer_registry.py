from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.transformer import (
    BUILTIN_TRANSFORMERS,
    GlassReactantEmbedder,
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

    def test_glass_reactant_embedder_is_registered(self):
        """
        Ensure ``glass_reactant_embedder`` is registered as a built-in.
        """
        self.assertIn('glass_reactant_embedder', BUILTIN_TRANSFORMERS)
        self.assertIn('glass_reactant_embedder', available_transformers())

    def test_glass_reactant_embedder_factory_returns_instance(self):
        """
        Ensure the built-in factory returns a GlassReactantEmbedder configured from kwargs.
        """
        factory = get_factory('glass_reactant_embedder')
        instance = factory(filename='x.csv', reactant_name='g', amount=1.0)
        self.assertIsInstance(instance, GlassReactantEmbedder)
        self.assertEqual(instance.filename, 'x.csv')


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

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory('nope')
