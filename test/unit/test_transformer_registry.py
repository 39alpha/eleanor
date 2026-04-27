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


class _FakeEntryPoint:
    """
    Lightweight stand-in for :class:`importlib.metadata.EntryPoint`.
    """

    def __init__(self, name: str, value: str, loader):
        self.name = name
        self.value = value
        self._loader = loader

    def load(self):
        return self._loader()


def _stamp(factory, version: int = 1):
    """Stamp the eleanor plugin API version on a test factory."""
    factory.__eleanor_api_version__ = version
    return factory


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

        _stamp(factory)
        register_transformer('plugin', factory)
        self.assertIs(get_factory('plugin'), factory)
        self.assertIn('plugin', available_transformers())

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory('nope')

    def test_discovery_skips_too_new_api_plugin_with_warning(self):
        """
        Ensure too-new transformer entry points are warned and skipped.
        """

        def factory(**_args):
            return mock.Mock()

        _stamp(factory, 99)
        ep = _FakeEntryPoint("too_new", "pkg:factory", lambda: factory)
        registry._discovered = False
        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'transformer entry point "too_new"'):
                names = available_transformers()
        self.assertNotIn("too_new", names)
