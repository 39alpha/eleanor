from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.output import (
    BUILTIN_OUTPUT_SINKS,
    OVERRIDE_ENV_VAR,
    available_output_sinks,
    get_factory,
    register_output_sink,
)
from eleanor.output.registry import registry

from ..common import TestCase


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


class TestBuiltinOutputSinks(TestCase):
    """
    Sanity checks on the built-in output sink set.
    """

    def test_postgres_is_registered(self):
        """
        Ensure ``postgres`` is always present in the output sink registry.
        """
        self.assertIn('postgres', BUILTIN_OUTPUT_SINKS)
        self.assertIn('postgres', available_output_sinks())


class TestRegisterOutputSink(_OutputRegistryTestCase):
    """
    Tests of :func:`register_output_sink`.
    """

    def test_register_and_retrieve(self):
        """
        Ensure a plugin sink factory can be registered and retrieved by name.
        """
        factory = mock.Mock(return_value=object())
        register_output_sink('plugin', factory)

        self.assertIn('plugin', available_output_sinks())
        self.assertIs(get_factory('plugin'), factory)

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory('nope')

    def test_register_rejects_builtin_override_without_env(self):
        """
        Ensure built-in sinks cannot be overridden by default.
        """
        original = registry._registry['postgres']
        replacement = mock.Mock(return_value=object())

        with mock.patch.dict('os.environ', {}, clear=False):
            __import__('os').environ.pop(OVERRIDE_ENV_VAR, None)
            with self.assertWarnsRegex(RuntimeWarning, 'refusing to override built-in'):
                register_output_sink('postgres', replacement)

        self.assertIs(registry._registry['postgres'], original)

    def test_register_allows_builtin_override_with_env(self):
        """
        Ensure built-in sinks can be overridden when the override env var is set.
        """
        original = registry._registry['postgres']
        replacement = mock.Mock(return_value=object())
        try:
            with mock.patch.dict('os.environ', {OVERRIDE_ENV_VAR: '1'}):
                register_output_sink('postgres', replacement)
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
        factory = mock.Mock(return_value=object())
        ep = _FakeEntryPoint('plugin', 'pkg.mod:build_sink', lambda: factory)

        with mock.patch('eleanor.plugin.entry_points', return_value=[ep]):
            sinks = available_output_sinks()

        self.assertIn('plugin', sinks)
        self.assertIs(get_factory('plugin'), factory)

    def test_discovery_warns_and_continues_on_load_failure(self):
        """
        Ensure a failing entry point emits a warning and does not abort discovery.
        """
        good_factory = mock.Mock(return_value=object())

        def _fail():
            raise ImportError('boom')

        failing_ep = _FakeEntryPoint('broken', 'pkg.bad:build', _fail)
        working_ep = _FakeEntryPoint('working', 'pkg.ok:build', lambda: good_factory)

        with mock.patch('eleanor.plugin.entry_points', return_value=[failing_ep, working_ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'failed to load output sink entry point "broken"'):
                sinks = available_output_sinks()

        self.assertNotIn('broken', sinks)
        self.assertIn('working', sinks)

    def test_discovery_rejects_non_callable_entry_point(self):
        """
        Ensure non-callable entry-point payloads are skipped with a warning.
        """
        bad_ep = _FakeEntryPoint('bad', 'pkg.bad:NOT_CALLABLE', lambda: 42)

        with mock.patch('eleanor.plugin.entry_points', return_value=[bad_ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'is invalid'):
                sinks = available_output_sinks()

        self.assertNotIn('bad', sinks)
