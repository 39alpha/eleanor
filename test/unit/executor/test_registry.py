import warnings
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor import registry as registry_module
from eleanor.executor.registry import (
    BUILTIN_EXECUTORS,
    OVERRIDE_ENV_VAR,
    available_executors,
    get_factory,
    register_executor,
    registry,
)

from ..common import TestCase


def _make_factory(return_value=None):
    """Return a fresh factory callable for registry tests."""
    sentinel = return_value if return_value is not None else object()
    return mock.MagicMock(return_value=sentinel), sentinel


class _FakeEntryPoint:
    """Lightweight stand-in for :class:`importlib.metadata.EntryPoint`."""

    def __init__(self, name: str, value: str, loader):
        self.name = name
        self.value = value
        self._loader = loader

    def load(self):
        return self._loader()


class _RegistryTestCase(TestCase):
    """Base class that snapshots / restores registry state between tests."""

    def setUp(self) -> None:
        self._saved_entries = dict(registry._registry)
        self._saved_discovered = registry._discovered

    def tearDown(self) -> None:
        registry._registry.clear()
        registry._registry.update(self._saved_entries)
        registry._discovered = self._saved_discovered


class TestRegisterExecutor(_RegistryTestCase):
    """
    Tests of :func:`eleanor.executor.registry.register_executor`.
    """

    def test_register_adds_new_executor(self):
        """
        Ensure register_executor exposes the factory through the registry.
        """
        factory, sentinel = _make_factory()
        register_executor('fake', factory)

        self.assertIn('fake', available_executors())
        self.assertIs(get_factory('fake')(2), sentinel)
        factory.assert_called_once_with(2)

    def test_register_is_idempotent_for_same_factory(self):
        """
        Ensure re-registering the same factory under the same name is a no-op.
        """
        factory, _ = _make_factory()
        register_executor('fake', factory)
        # No warning should be raised on the second call.
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            register_executor('fake', factory)
        self.assertIs(registry._registry['fake'], factory)

    def test_register_rejects_builtin_override_without_env(self):
        """
        Ensure built-in executors cannot be overridden by default.
        """
        builtin_name = 'serial'
        original = registry._registry[builtin_name]
        replacement, _ = _make_factory()

        with mock.patch.dict('os.environ', {}, clear=False):
            # Ensure the override env var is unset.
            __import__('os').environ.pop(OVERRIDE_ENV_VAR, None)
            with self.assertWarnsRegex(RuntimeWarning, 'refusing to override built-in'):
                register_executor(builtin_name, replacement)

        self.assertIs(registry._registry[builtin_name], original)

    def test_register_allows_builtin_override_with_env(self):
        """
        Ensure built-in executors can be overridden when the override env var is set.
        """
        builtin_name = 'serial'
        original = registry._registry[builtin_name]
        replacement, _ = _make_factory()

        try:
            with mock.patch.dict('os.environ', {OVERRIDE_ENV_VAR: '1'}):
                register_executor(builtin_name, replacement)
            self.assertIs(registry._registry[builtin_name], replacement)
        finally:
            registry._registry[builtin_name] = original

    def test_register_warns_on_plugin_collision(self):
        """
        Ensure a second plugin registering under an existing plugin name is rejected with a warning.
        """
        first, _ = _make_factory()
        second, _ = _make_factory()
        register_executor('clash', first)

        with self.assertWarnsRegex(RuntimeWarning, 'is already registered'):
            register_executor('clash', second)

        self.assertIs(registry._registry['clash'], first)

    def test_register_rejects_empty_name(self):
        """
        Ensure register_executor validates the executor name.
        """
        factory, _ = _make_factory()
        with self.assertRaises(EleanorException):
            register_executor('', factory)

    def test_register_rejects_non_callable_factory(self):
        """
        Ensure register_executor validates the factory argument.
        """
        with self.assertRaises(EleanorException):
            register_executor('broken', object())  # type: ignore[arg-type]


class TestEntryPointDiscovery(_RegistryTestCase):
    """
    Tests of entry-point discovery on the executor registry.
    """

    def setUp(self) -> None:
        super().setUp()
        # Force discovery to re-run for each test.
        registry._discovered = False

    def test_discovery_registers_entry_points(self):
        """
        Ensure entry points in the ``eleanor.executors`` group populate the registry.
        """
        factory, sentinel = _make_factory()
        ep = _FakeEntryPoint('plugin', 'pkg.mod:build', lambda: factory)

        with mock.patch('eleanor.plugin.entry_points', return_value=[ep]):
            executors = available_executors()

        self.assertIn('plugin', executors)
        self.assertIs(get_factory('plugin')(4), sentinel)
        factory.assert_called_once_with(4)

    def test_discovery_warns_and_continues_on_load_failure(self):
        """
        Ensure a failing entry point emits a RuntimeWarning and does not abort discovery of others.
        """
        good_factory, sentinel = _make_factory()

        def _fail():
            raise ImportError('boom')

        failing_ep = _FakeEntryPoint('broken', 'pkg.broken:build', _fail)
        working_ep = _FakeEntryPoint('working', 'pkg.ok:build', lambda: good_factory)

        with mock.patch(
            'eleanor.plugin.entry_points',
            return_value=[failing_ep, working_ep],
        ):
            with self.assertWarnsRegex(RuntimeWarning, 'failed to load executor entry point "broken"'):
                executors = available_executors()

        self.assertNotIn('broken', executors)
        self.assertIn('working', executors)

    def test_discovery_rejects_non_callable_entry_point(self):
        """
        Ensure entry points that do not resolve to callables are skipped with a warning.
        """
        not_callable_ep = _FakeEntryPoint('bad', 'pkg.bad:NOT_CALLABLE', lambda: 42)

        with mock.patch(
            'eleanor.plugin.entry_points',
            return_value=[not_callable_ep],
        ):
            with self.assertWarnsRegex(RuntimeWarning, 'is invalid'):
                executors = available_executors()

        self.assertNotIn('bad', executors)

    def test_discovery_runs_at_most_once(self):
        """
        Ensure repeated calls do not re-query entry points.
        """
        ep_call = mock.MagicMock(return_value=[])
        with mock.patch('eleanor.plugin.entry_points', ep_call):
            available_executors()
            available_executors()
            get_factory('serial')
        self.assertEqual(ep_call.call_count, 1)

    def test_discovery_rejects_builtin_name_from_plugin(self):
        """
        Ensure a plugin that tries to register a built-in name is rejected with a warning.
        """
        replacement, _ = _make_factory()
        ep = _FakeEntryPoint('serial', 'bad_plugin:build', lambda: replacement)
        original = registry._registry['serial']

        with mock.patch('eleanor.plugin.entry_points', return_value=[ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'refusing to override built-in'):
                available_executors()

        self.assertIs(registry._registry['serial'], original)


class TestGetFactory(_RegistryTestCase):
    """
    Tests of :func:`eleanor.executor.registry.get_factory`.
    """

    def test_unknown_executor_error_enumerates_plugin_names(self):
        """
        Ensure the error message lists both built-ins and discovered plugins.
        """
        registry._discovered = False
        plugin_factory, _ = _make_factory()
        ep = _FakeEntryPoint('plugin', 'pkg:build', lambda: plugin_factory)

        with mock.patch('eleanor.plugin.entry_points', return_value=[ep]):
            with self.assertRaises(EleanorException) as ctx:
                get_factory('nope')

        message = str(ctx.exception)
        self.assertIn('nope', message)
        self.assertIn('plugin', message)
        for builtin in sorted(BUILTIN_EXECUTORS):
            self.assertIn(builtin, message)


class TestRegistrySurface(TestCase):
    """
    Module-level sanity checks that don't need to mutate the registry.
    """

    def test_module_exposes_registry(self):
        """
        Ensure the module-level ``registry`` attribute is a PluginRegistry instance.
        """
        from eleanor.plugin import PluginRegistry
        self.assertIsInstance(registry_module.registry, PluginRegistry)
        self.assertEqual(registry_module.registry.kind, 'executor')
        self.assertEqual(registry_module.registry.entry_point_group, 'eleanor.executors')

    def test_builtin_executors_is_registry_builtins(self):
        """
        Ensure BUILTIN_EXECUTORS is the registry's built-in set.
        """
        self.assertEqual(BUILTIN_EXECUTORS, registry_module.registry.builtins)
