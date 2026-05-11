import warnings
from typing import override
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.executor import registry as registry_module
from eleanor.executor.registry import (
    BUILTIN_EXECUTORS,
    ExecutorFactory,
    available_executors,
    get_factory,
    register_executor,
    registry,
)

from ..common import TestCase

_ = available_executors()  # ensure builtins are discovered before registry snapshots


def _make_factory(return_value=None, *, api_version: int = 1):
    """Return a fresh factory callable for registry tests.

    The factory is stamped with ``__eleanor_api_version__ = api_version`` so
    the registry does not emit the unversioned-plugin warning during normal
    fixture setup. Tests that exercise the version-mismatch path pass an
    out-of-range ``api_version`` explicitly.
    """
    sentinel = return_value if return_value is not None else object()
    factory = mock.MagicMock(return_value=sentinel)
    factory.__eleanor_api_version__ = api_version
    return factory, sentinel


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

    _saved_entries: dict[str, ExecutorFactory] = {}
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


class TestRegisterExecutor(_RegistryTestCase):
    """
    Tests of :func:`eleanor.executor.registry.register_executor`.
    """

    def test_register_adds_new_executor(self):
        """
        Ensure register_executor exposes the factory through the registry.
        """
        factory, sentinel = _make_factory()
        register_executor("fake", factory)

        self.assertIn("fake", available_executors())
        self.assertIs(get_factory("fake")(2), sentinel)
        factory.assert_called_once_with(2)

    def test_register_is_idempotent_for_same_factory(self):
        """
        Ensure re-registering the same factory under the same name is a no-op.
        """
        factory, _ = _make_factory()
        register_executor("fake", factory)
        # No warning should be raised on the second call.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            register_executor("fake", factory)
        self.assertIs(registry._registry["fake"], factory)

    def test_register_rejects_builtin_name(self):
        """
        Ensure built-in executor names cannot be registered over.
        """
        replacement, _ = _make_factory()
        with self.assertRaisesRegex(EleanorException, "built-in executor"):
            register_executor("serial", replacement)

    def test_register_rejects_duplicate_name(self):
        """
        Ensure a second plugin registering under an existing name is a hard error.
        """
        first, _ = _make_factory()
        second, _ = _make_factory()
        register_executor("clash", first)

        with self.assertRaisesRegex(EleanorException, "is already registered"):
            register_executor("clash", second)

        self.assertIs(registry._registry["clash"], first)

    def test_register_rejects_empty_name(self):
        """
        Ensure register_executor validates the executor name.
        """
        factory, _ = _make_factory()
        with self.assertRaises(EleanorException):
            register_executor("", factory)

    def test_register_rejects_non_callable_factory(self):
        """
        Ensure register_executor validates the factory argument.
        """
        with self.assertRaises(EleanorException):
            register_executor("broken", object())  # pyright: ignore[reportArgumentType]


class TestEntryPointDiscovery(_RegistryTestCase):
    """
    Tests of entry-point discovery on the executor registry.
    """

    @override
    def setUp(self) -> None:
        super().setUp()
        # Force discovery to re-run for each test.
        registry._discovered = False

    def test_discovery_registers_entry_points(self):
        """
        Ensure entry points in the ``eleanor.executors`` group populate the registry.
        """
        factory, sentinel = _make_factory()
        ep = _FakeEntryPoint("plugin", "pkg.mod:build", lambda: factory)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            executors = available_executors()

        self.assertIn("plugin", executors)
        self.assertIs(get_factory("plugin")(4), sentinel)
        factory.assert_called_once_with(4)

    def test_discovery_raises_on_load_failure(self):
        """
        Ensure a failing entry-point load is a hard error.
        """

        def _fail():
            raise ImportError("boom")

        failing_ep = _FakeEntryPoint("broken", "pkg.broken:build", _fail)

        with mock.patch("eleanor.plugin.entry_points", return_value=[failing_ep]):
            with self.assertRaisesRegex(EleanorException, 'failed to load executor entry point "broken"'):
                available_executors()

    def test_discovery_raises_on_non_callable_entry_point(self):
        """
        Ensure entry points that do not resolve to callables are hard errors.
        """
        not_callable_ep = _FakeEntryPoint("bad", "pkg.bad:NOT_CALLABLE", lambda: 42)

        with mock.patch("eleanor.plugin.entry_points", return_value=[not_callable_ep]):
            with self.assertRaisesRegex(EleanorException, "must be callable"):
                available_executors()

    def test_discovery_runs_at_most_once(self):
        """
        Ensure repeated calls do not re-query entry points.
        """
        ep_call = mock.MagicMock(return_value=[])
        with mock.patch("eleanor.plugin.entry_points", ep_call):
            available_executors()
            available_executors()
            get_factory("serial")
        self.assertEqual(ep_call.call_count, 1)

    def test_discovery_raises_on_too_new_api_plugin(self):
        """
        Ensure too-new executor entry points are hard errors.
        """
        factory, _ = _make_factory(api_version=99)
        ep = _FakeEntryPoint("too_new", "pkg:factory", lambda: factory)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertRaisesRegex(EleanorException, "supports up to"):
                available_executors()


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
        ep = _FakeEntryPoint("plugin", "pkg:build", lambda: plugin_factory)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertRaises(EleanorException) as ctx:
                get_factory("nope")

        message = str(ctx.exception)
        self.assertIn("nope", message)
        self.assertIn("plugin", message)
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
        self.assertEqual(registry_module.registry.kind, "executor")
        self.assertEqual(registry_module.registry.entry_point_group, "eleanor.executors")

    def test_builtin_executors_is_registry_builtins(self):
        """
        Ensure BUILTIN_EXECUTORS is the registry's built-in set.
        """
        self.assertEqual(BUILTIN_EXECUTORS, registry_module.registry.builtins)
