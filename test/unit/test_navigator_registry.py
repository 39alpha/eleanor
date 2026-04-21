from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.navigator import (
    BUILTIN_NAVIGATORS,
    Lattice,
    Random,
    RandomLattice,
    available_navigators,
    get_factory,
    register_navigator,
)
from eleanor.navigator.registry import registry

from .common import TestCase


class _NavigatorRegistryTestCase(TestCase):

    def setUp(self) -> None:
        self._saved_entries = dict(registry._registry)
        self._saved_discovered = registry._discovered

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
        self.assertIn('random', BUILTIN_NAVIGATORS)
        self.assertIn('random_lattice', BUILTIN_NAVIGATORS)
        self.assertIn('lattice', BUILTIN_NAVIGATORS)
        self.assertTrue(BUILTIN_NAVIGATORS.issubset(available_navigators()))

    def test_builtin_factory_returns_navigator_subclass(self):
        """
        Ensure the built-in factories instantiate the correct navigator class.
        """
        factory = get_factory('random')
        nav = factory(order=mock.Mock(), kernel=mock.Mock())
        self.assertIsInstance(nav, Random)

        factory = get_factory('random_lattice')
        nav = factory(order=mock.Mock(), kernel=mock.Mock())
        self.assertIsInstance(nav, RandomLattice)

        factory = get_factory('lattice')
        nav = factory(order=mock.Mock(), kernel=mock.Mock())
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

        register_navigator('plugin', factory)
        self.assertIs(get_factory('plugin'), factory)
        self.assertIn('plugin', available_navigators())

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory('nope')
