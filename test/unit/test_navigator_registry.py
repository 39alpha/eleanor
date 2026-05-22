from typing import override
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.navigator.lattice import Lattice, RandomLattice
from eleanor.navigator.random import Random
from eleanor.navigator.registry import (
    BUILTIN_NAVIGATORS,
    NavigatorFactory,
    available_navigators,
    get_factory,
    register_navigator,
    registry,
)

from .common import TestCase

_ = available_navigators()  # ensure builtins are discovered before registry snapshots


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


class _NavigatorRegistryTestCase(TestCase):
    _saved_entries: dict[str, NavigatorFactory] = {}
    _saved_discovered: bool = False

    @override
    def setUp(self) -> None:
        self._saved_entries = dict(registry._registry)
        self._saved_discovered = registry._discovered

    @override
    def tearDown(self) -> None:
        registry._registry.clear()
        registry._registry.update(self._saved_entries)
        registry._discovered = self._saved_discovered


class TestBuiltinNavigators(TestCase):
    """
    Sanity checks on the built-in navigator set.
    """

    def test_builtins_include_random_lattice_and_random_lattice(self):
        """
        Ensure ``random``, ``random_lattice`` and ``lattice`` are all registered as built-ins.
        """
        self.assertIn("random", BUILTIN_NAVIGATORS)
        self.assertIn("random_lattice", BUILTIN_NAVIGATORS)
        self.assertIn("lattice", BUILTIN_NAVIGATORS)
        self.assertTrue(BUILTIN_NAVIGATORS.issubset(available_navigators()))

    def test_builtin_factory_returns_navigator_subclass(self):
        """
        Ensure the built-in factories instantiate the correct navigator class.
        """
        factory = get_factory("random")
        nav = factory()
        self.assertIsInstance(nav, Random)

        factory = get_factory("random_lattice")
        nav = factory()
        self.assertIsInstance(nav, RandomLattice)

        factory = get_factory("lattice")
        nav = factory()
        self.assertIsInstance(nav, Lattice)


class TestRegisterNavigator(_NavigatorRegistryTestCase):
    """
    Tests of :func:`register_navigator`.
    """

    def test_register_and_retrieve(self):
        """
        Ensure a plugin can be registered and retrieved by name.
        """

        def factory(order, kernel, **_args):
            return mock.Mock()

        _stamp(factory)
        register_navigator("plugin", factory)
        self.assertIs(get_factory("plugin"), factory)
        self.assertIn("plugin", available_navigators())

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory("nope")

    def test_discovery_raises_on_too_new_api_plugin(self):
        """
        Ensure too-new navigator entry points are hard errors.
        """

        def factory(order, kernel, **_args):
            return mock.Mock()

        _stamp(factory, 99)
        ep = _FakeEntryPoint("too_new", "pkg:factory", lambda: factory)
        registry._discovered = False
        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertRaisesRegex(EleanorException, "supports up to"):
                available_navigators()
