from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.output import (
    BUILTIN_OUTPUTS,
    OVERRIDE_ENV_VAR,
    available_outputs,
    get_factory,
    register_output,
)
from eleanor.output.registry import registry

from ..common import TestCase


def _make_factory(return_value=None, *, api_version: int = 1):
    """Return a stamped Mock factory for output registry tests."""
    sentinel = return_value if return_value is not None else object()
    factory = mock.Mock(return_value=sentinel)
    factory.__eleanor_api_version__ = api_version
    return factory


class _FakeEntryPoint:
    """Lightweight stand-in for :class:`importlib.metadata.EntryPoint`."""

    def __init__(self, name: str, value: str, loader):
        self.name = name
        self.value = value
        self._loader = loader

    def load(self):
        return self._loader()


class _OutputRegistryTestCase(TestCase):
    """Base class that snapshots / restores output registry state between tests."""

    def setUp(self) -> None:
        self._saved_entries = dict(registry._registry)
        self._saved_discovered = registry._discovered

    def tearDown(self) -> None:
        registry._registry.clear()
        registry._registry.update(self._saved_entries)
        registry._discovered = self._saved_discovered


class TestBuiltinOutputs(TestCase):
    """
    Sanity checks on the built-in output set.
    """

    def test_postgres_is_registered(self):
        """
        Ensure ``postgres`` is always present in the output registry.
        """
        self.assertIn('postgres', BUILTIN_OUTPUTS)
        self.assertIn('postgres', available_outputs())

    def test_csv_is_registered(self):
        """
        Ensure ``csv`` is always present in the output registry.
        """
        self.assertIn('csv', BUILTIN_OUTPUTS)
        self.assertIn('csv', available_outputs())


class TestRegisterOutput(_OutputRegistryTestCase):
    """
    Tests of :func:`register_output`.
    """

    def test_register_and_retrieve(self):
        """
        Ensure a plugin output factory can be registered and retrieved by name.
        """
        factory = _make_factory()
        register_output('plugin', factory)

        self.assertIn('plugin', available_outputs())
        self.assertIs(get_factory('plugin'), factory)

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory('nope')

    def test_register_rejects_builtin_override_without_env(self):
        """
        Ensure built-in outputs cannot be overridden by default.
        """
        import os

        original = registry._registry['postgres']
        replacement = _make_factory()

        with mock.patch.dict('os.environ', {}, clear=False):
            os.environ.pop(OVERRIDE_ENV_VAR, None)
            with self.assertWarnsRegex(RuntimeWarning, 'refusing to override built-in'):
                register_output('postgres', replacement)

        self.assertIs(registry._registry['postgres'], original)

    def test_register_allows_builtin_override_with_env(self):
        """
        Ensure built-in outputs can be overridden when the override env var is set.
        """
        original = registry._registry['postgres']
        replacement = _make_factory()
        try:
            with mock.patch.dict('os.environ', {OVERRIDE_ENV_VAR: '1'}):
                register_output('postgres', replacement)
            self.assertIs(registry._registry['postgres'], replacement)
        finally:
            registry._registry['postgres'] = original


class TestEntryPointDiscovery(_OutputRegistryTestCase):
    """
    Tests of lazy entry-point discovery on the output sink registry.
    """

    def setUp(self) -> None:
        super().setUp()
        registry._discovered = False

    def test_discovery_registers_entry_points(self):
        """
        Ensure entry points in the ``eleanor.outputs`` group populate the registry.
        """
        factory = _make_factory()
        ep = _FakeEntryPoint('plugin', 'pkg.mod:build_sink', lambda: factory)

        with mock.patch('eleanor.plugin.entry_points', return_value=[ep]):
            outputs = available_outputs()

        self.assertIn('plugin', outputs)
        self.assertIs(get_factory('plugin'), factory)

    def test_discovery_warns_and_continues_on_load_failure(self):
        """
        Ensure a failing entry point emits a warning and does not abort discovery.
        """
        good_factory = _make_factory()

        def _fail():
            raise ImportError('boom')

        failing_ep = _FakeEntryPoint('broken', 'pkg.bad:build', _fail)
        working_ep = _FakeEntryPoint('working', 'pkg.ok:build', lambda: good_factory)

        with mock.patch('eleanor.plugin.entry_points', return_value=[failing_ep, working_ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'failed to load output entry point "broken"'):
                outputs = available_outputs()

        self.assertNotIn('broken', outputs)
        self.assertIn('working', outputs)

    def test_discovery_rejects_non_callable_entry_point(self):
        """
        Ensure non-callable entry-point payloads are skipped with a warning.
        """
        bad_ep = _FakeEntryPoint('bad', 'pkg.bad:NOT_CALLABLE', lambda: 42)

        with mock.patch('eleanor.plugin.entry_points', return_value=[bad_ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'is invalid'):
                outputs = available_outputs()

        self.assertNotIn('bad', outputs)

    def test_discovery_skips_too_new_api_plugin_with_warning(self):
        """
        Ensure too-new output entry points are warned and skipped.
        """
        factory = _make_factory(api_version=99)
        ep = _FakeEntryPoint("too_new", "pkg:factory", lambda: factory)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'output entry point "too_new"'):
                outputs = available_outputs()

        self.assertNotIn("too_new", outputs)
