import warnings
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor import registry
from eleanor.executor.registry import (
    BUILTIN_BACKENDS,
    OVERRIDE_ENV_VAR,
    available_backends,
    get_factory,
    register_backend,
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
        self._saved_registry = dict(registry._BACKEND_REGISTRY)
        self._saved_discovered = registry._DISCOVERED

    def tearDown(self) -> None:
        registry._BACKEND_REGISTRY.clear()
        registry._BACKEND_REGISTRY.update(self._saved_registry)
        registry._DISCOVERED = self._saved_discovered


class TestRegisterBackend(_RegistryTestCase):
    """
    Tests of :func:`eleanor.executor.registry.register_backend`.
    """

    def test_register_adds_new_backend(self):
        """
        Ensure register_backend exposes the factory through the registry.
        """
        factory, sentinel = _make_factory()
        register_backend('fake', factory)

        self.assertIn('fake', available_backends())
        self.assertIs(get_factory('fake')(2), sentinel)
        factory.assert_called_once_with(2)

    def test_register_is_idempotent_for_same_factory(self):
        """
        Ensure re-registering the same factory under the same name is a no-op.
        """
        factory, _ = _make_factory()
        register_backend('fake', factory)
        # No warning should be raised on the second call.
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            register_backend('fake', factory)
        self.assertIs(registry._BACKEND_REGISTRY['fake'], factory)

    def test_register_rejects_builtin_override_without_env(self):
        """
        Ensure built-in backends cannot be overridden by default.
        """
        builtin_name = 'serial'
        original = registry._BACKEND_REGISTRY[builtin_name]
        replacement, _ = _make_factory()

        with mock.patch.dict('os.environ', {}, clear=False):
            # Ensure the override env var is unset.
            __import__('os').environ.pop(OVERRIDE_ENV_VAR, None)
            with self.assertWarnsRegex(RuntimeWarning, 'refusing to override built-in'):
                register_backend(builtin_name, replacement)

        self.assertIs(registry._BACKEND_REGISTRY[builtin_name], original)

    def test_register_allows_builtin_override_with_env(self):
        """
        Ensure built-in backends can be overridden when the override env var is set.
        """
        builtin_name = 'serial'
        original = registry._BACKEND_REGISTRY[builtin_name]
        replacement, _ = _make_factory()

        try:
            with mock.patch.dict('os.environ', {OVERRIDE_ENV_VAR: '1'}):
                register_backend(builtin_name, replacement)
            self.assertIs(registry._BACKEND_REGISTRY[builtin_name], replacement)
        finally:
            registry._BACKEND_REGISTRY[builtin_name] = original

    def test_register_warns_on_plugin_collision(self):
        """
        Ensure a second plugin registering under an existing plugin name is rejected with a warning.
        """
        first, _ = _make_factory()
        second, _ = _make_factory()
        register_backend('clash', first)

        with self.assertWarnsRegex(RuntimeWarning, 'is already registered'):
            register_backend('clash', second)

        self.assertIs(registry._BACKEND_REGISTRY['clash'], first)

    def test_register_rejects_empty_name(self):
        """
        Ensure register_backend validates the backend name.
        """
        factory, _ = _make_factory()
        with self.assertRaises(EleanorException):
            register_backend('', factory)

    def test_register_rejects_non_callable_factory(self):
        """
        Ensure register_backend validates the factory argument.
        """
        with self.assertRaises(EleanorException):
            register_backend('broken', object())  # type: ignore[arg-type]


class TestEntryPointDiscovery(_RegistryTestCase):
    """
    Tests of :func:`eleanor.executor.registry._discover_entry_points`.
    """

    def setUp(self) -> None:
        super().setUp()
        # Force discovery to re-run for each test.
        registry._DISCOVERED = False

    def test_discovery_registers_entry_points(self):
        """
        Ensure entry points in the ``eleanor.executors`` group populate the registry.
        """
        factory, sentinel = _make_factory()
        ep = _FakeEntryPoint('plugin', 'pkg.mod:build', lambda: factory)

        with mock.patch('eleanor.executor.registry.entry_points', return_value=[ep]):
            backends = available_backends()

        self.assertIn('plugin', backends)
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
            'eleanor.executor.registry.entry_points',
            return_value=[failing_ep, working_ep],
        ):
            with self.assertWarnsRegex(RuntimeWarning, 'failed to load executor entry point "broken"'):
                backends = available_backends()

        self.assertNotIn('broken', backends)
        self.assertIn('working', backends)

    def test_discovery_rejects_non_callable_entry_point(self):
        """
        Ensure entry points that do not resolve to callables are skipped with a warning.
        """
        not_callable_ep = _FakeEntryPoint('bad', 'pkg.bad:NOT_CALLABLE', lambda: 42)

        with mock.patch(
            'eleanor.executor.registry.entry_points',
            return_value=[not_callable_ep],
        ):
            with self.assertWarnsRegex(RuntimeWarning, 'did not resolve to a callable'):
                backends = available_backends()

        self.assertNotIn('bad', backends)

    def test_discovery_runs_at_most_once(self):
        """
        Ensure repeated calls do not re-query entry points.
        """
        ep_call = mock.MagicMock(return_value=[])
        with mock.patch('eleanor.executor.registry.entry_points', ep_call):
            available_backends()
            available_backends()
            get_factory('serial')
        self.assertEqual(ep_call.call_count, 1)

    def test_discovery_rejects_builtin_name_from_plugin(self):
        """
        Ensure a plugin that tries to register a built-in name is rejected with a warning.
        """
        replacement, _ = _make_factory()
        ep = _FakeEntryPoint('serial', 'bad_plugin:build', lambda: replacement)
        original = registry._BACKEND_REGISTRY['serial']

        with mock.patch('eleanor.executor.registry.entry_points', return_value=[ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'refusing to override built-in'):
                available_backends()

        self.assertIs(registry._BACKEND_REGISTRY['serial'], original)


class TestGetFactory(_RegistryTestCase):
    """
    Tests of :func:`eleanor.executor.registry.get_factory`.
    """

    def test_unknown_backend_error_enumerates_plugin_names(self):
        """
        Ensure the error message lists both built-ins and discovered plugins.
        """
        registry._DISCOVERED = False
        plugin_factory, _ = _make_factory()
        ep = _FakeEntryPoint('plugin', 'pkg:build', lambda: plugin_factory)

        with mock.patch('eleanor.executor.registry.entry_points', return_value=[ep]):
            with self.assertRaises(EleanorException) as ctx:
                get_factory('nope')

        message = str(ctx.exception)
        self.assertIn('nope', message)
        self.assertIn('plugin', message)
        for builtin in sorted(BUILTIN_BACKENDS):
            self.assertIn(builtin, message)
