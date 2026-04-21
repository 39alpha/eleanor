"""Tests of the generic :class:`eleanor.plugin.PluginRegistry`."""
import os
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

from .common import TestCase


class _FakeEntryPoint:
    """Lightweight stand-in for :class:`importlib.metadata.EntryPoint`."""

    def __init__(self, name: str, value: str, loader):
        self.name = name
        self.value = value
        self._loader = loader

    def load(self):
        return self._loader()


def _builtin():
    return 'builtin-ran'


def _plugin():
    return 'plugin-ran'


def _make_registry(**overrides):
    defaults = dict(
        kind='widget',
        entry_point_group='eleanor.test.widgets',
        override_env_var='ELEANOR_WIDGET_OVERRIDES',
        builtins={'b1': _builtin},
    )
    defaults.update(overrides)
    return PluginRegistry(**defaults)


class TestPluginRegistryBasics(TestCase):
    """
    Tests of :class:`PluginRegistry` construction, registration and lookup.
    """

    def test_available_includes_builtins(self):
        """
        Ensure builtins appear in ``available()`` and are marked as builtin.
        """
        registry = _make_registry()
        self.assertIn('b1', registry.available())
        self.assertTrue(registry.is_builtin('b1'))
        self.assertEqual(registry.builtins, frozenset({'b1'}))

    def test_register_and_get(self):
        """
        Ensure a plugin can be registered and later retrieved by name.
        """
        registry = _make_registry()
        registry.register('p1', _plugin)
        self.assertIs(registry.get('p1'), _plugin)
        self.assertFalse(registry.is_builtin('p1'))

    def test_get_unknown_name_raises(self):
        """
        Ensure ``get`` raises an informative exception for unknown names.
        """
        registry = _make_registry()
        with self.assertRaises(EleanorException) as ctx:
            registry.get('nope')
        self.assertIn('nope', str(ctx.exception))
        self.assertIn('widget', str(ctx.exception))
        self.assertIn('b1', str(ctx.exception))

    def test_register_empty_name_rejected(self):
        """
        Ensure ``register`` rejects empty names.
        """
        registry = _make_registry()
        with self.assertRaises(EleanorException):
            registry.register('', _plugin)

    def test_register_non_callable_without_validator(self):
        """
        Ensure the default validator rejects non-callable factories.
        """
        registry = _make_registry()
        with self.assertRaises(EleanorException):
            registry.register('bad', 'not-callable')  # type: ignore[arg-type]


class TestCollisionPolicy(TestCase):
    """
    Tests of the registry's builtin-vs-plugin and plugin-vs-plugin collision handling.
    """

    def test_builtin_collision_refused_without_override(self):
        """
        Ensure a plugin cannot override a built-in without the override env var.
        """
        registry = _make_registry()
        with self.assertWarnsRegex(RuntimeWarning, 'refusing to override built-in'):
            registry.register('b1', _plugin)
        self.assertIs(registry.get('b1'), _builtin)

    def test_builtin_collision_allowed_with_override(self):
        """
        Ensure built-ins can be overridden when ``ELEANOR_<KIND>_OVERRIDES`` is truthy.
        """
        registry = _make_registry()
        with mock.patch.dict(os.environ, {'ELEANOR_WIDGET_OVERRIDES': '1'}):
            registry.register('b1', _plugin)
        self.assertIs(registry.get('b1'), _plugin)

    def test_plugin_collision_keeps_first(self):
        """
        Ensure plugin-vs-plugin collisions are rejected with a warning and the first wins.
        """
        registry = _make_registry()
        registry.register('p1', _plugin)

        def _other():
            return 'other'

        with self.assertWarnsRegex(RuntimeWarning, 'is already registered'):
            registry.register('p1', _other)
        self.assertIs(registry.get('p1'), _plugin)


class TestValidator(TestCase):
    """
    Tests of the optional registration-time validator callback.
    """

    def test_validator_runs_at_registration(self):
        """
        Ensure the validator is invoked for every registration.
        """
        calls = []

        def validator(name: str, factory):
            calls.append((name, factory))
            return factory

        registry = _make_registry(validator=validator)
        registry.register('p1', _plugin)
        self.assertIn(('b1', _builtin), calls)
        self.assertIn(('p1', _plugin), calls)

    def test_validator_can_coerce(self):
        """
        Ensure the validator can transform or replace the factory.
        """
        sentinel = object()

        def validator(_name, _factory):
            return sentinel

        registry = _make_registry(validator=validator)
        registry.register('p1', _plugin)
        self.assertIs(registry.get('p1'), sentinel)

    def test_validator_can_reject(self):
        """
        Ensure the validator can reject a registration with an EleanorException.
        """

        def validator(name, _factory):
            if name == 'bad':
                raise EleanorException('nope')
            return _factory

        registry = _make_registry(validator=validator)
        with self.assertRaises(EleanorException):
            registry.register('bad', _plugin)


class TestEntryPointDiscovery(TestCase):
    """
    Tests of lazy entry-point discovery on :class:`PluginRegistry`.
    """

    def test_discovery_runs_once(self):
        """
        Ensure entry-point discovery is triggered exactly once.
        """
        ep_call = mock.MagicMock(return_value=[])
        registry = _make_registry()
        with mock.patch('eleanor.plugin.entry_points', ep_call):
            registry.available()
            registry.available()
            registry.get('b1')
        self.assertEqual(ep_call.call_count, 1)

    def test_discovery_registers_entry_points(self):
        """
        Ensure entry points are registered with the registry on first access.
        """
        ep = _FakeEntryPoint('p1', 'pkg:factory', lambda: _plugin)
        registry = _make_registry()
        with mock.patch('eleanor.plugin.entry_points', return_value=[ep]):
            self.assertIn('p1', registry.available())
        self.assertIs(registry.get('p1'), _plugin)

    def test_discovery_warns_on_load_failure(self):
        """
        Ensure a failing entry-point load emits a warning and does not abort discovery.
        """

        def _fail():
            raise ImportError('boom')

        failing = _FakeEntryPoint('broken', 'pkg.bad:factory', _fail)
        working = _FakeEntryPoint('good', 'pkg.ok:factory', lambda: _plugin)

        registry = _make_registry()
        with mock.patch('eleanor.plugin.entry_points', return_value=[failing, working]):
            with self.assertWarnsRegex(RuntimeWarning, 'failed to load widget entry point "broken"'):
                self.assertIn('good', registry.available())
        self.assertNotIn('broken', registry.available())

    def test_discovery_warns_on_invalid_entry_point(self):
        """
        Ensure entry points rejected by the validator emit a warning and are skipped.
        """
        # The default validator rejects non-callables.
        ep = _FakeEntryPoint('bad', 'pkg.bad:nothing', lambda: 42)
        registry = _make_registry()
        with mock.patch('eleanor.plugin.entry_points', return_value=[ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'is invalid'):
                self.assertNotIn('bad', registry.available())
