from typing import override
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.output.registry import (
    BUILTIN_OUTPUTS,
    OutputFactory,
    available_output_sinks,
    get_factory,
    register_output_sink,
    registry,
)

from ..common import TestCase

_ = available_output_sinks()  # ensure builtins are discovered before registry snapshots


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

    _saved_entries: dict[str, OutputFactory] = {}
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


class TestBuiltinOutputs(TestCase):
    """
    Sanity checks on the built-in output set.
    """

    def test_postgres_is_registered(self):
        """
        Ensure ``postgres`` is always present in the output registry.
        """
        self.assertIn("postgres", BUILTIN_OUTPUTS)
        self.assertIn("postgres", available_output_sinks())

    def test_csv_is_registered(self):
        """
        Ensure ``csv`` is always present in the output registry.
        """
        self.assertIn("csv", BUILTIN_OUTPUTS)
        self.assertIn("csv", available_output_sinks())


class TestRegisterOutput(_OutputRegistryTestCase):
    """
    Tests of :func:`register_output_sink`.
    """

    def test_register_and_retrieve(self):
        """
        Ensure a plugin output factory can be registered and retrieved by name.
        """
        factory = _make_factory()
        register_output_sink("plugin", factory)

        self.assertIn("plugin", available_output_sinks())
        self.assertIs(get_factory("plugin"), factory)

    def test_unknown_name_raises(self):
        """
        Ensure ``get_factory`` raises for unknown names.
        """
        with self.assertRaises(EleanorException):
            get_factory("nope")

    def test_register_rejects_builtin_name(self):
        """
        Ensure built-in output names cannot be registered over.
        """
        replacement = _make_factory()
        with self.assertRaisesRegex(EleanorException, "built-in output"):
            register_output_sink("postgres", replacement)


class TestEntryPointDiscovery(_OutputRegistryTestCase):
    """
    Tests of lazy entry-point discovery on the output sink registry.
    """

    @override
    def setUp(self) -> None:
        super().setUp()
        registry._discovered = False

    def test_discovery_registers_entry_points(self):
        """
        Ensure entry points in the ``eleanor.outputs`` group populate the registry.
        """
        factory = _make_factory()
        ep = _FakeEntryPoint("plugin", "pkg.mod:build_sink", lambda: factory)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            outputs = available_output_sinks()

        self.assertIn("plugin", outputs)
        self.assertIs(get_factory("plugin"), factory)

    def test_discovery_raises_on_load_failure(self):
        """
        Ensure a failing entry-point load is a hard error.
        """

        def _fail():
            raise ImportError("boom")

        failing_ep = _FakeEntryPoint("broken", "pkg.bad:build", _fail)

        with mock.patch("eleanor.plugin.entry_points", return_value=[failing_ep]):
            with self.assertRaisesRegex(EleanorException, 'failed to load output entry point "broken"'):
                available_output_sinks()

    def test_discovery_raises_on_non_callable_entry_point(self):
        """
        Ensure non-callable entry-point payloads are hard errors.
        """
        bad_ep = _FakeEntryPoint("bad", "pkg.bad:NOT_CALLABLE", lambda: 42)

        with mock.patch("eleanor.plugin.entry_points", return_value=[bad_ep]):
            with self.assertRaisesRegex(EleanorException, "must be callable"):
                available_output_sinks()

    def test_discovery_raises_on_too_new_api_plugin(self):
        """
        Ensure too-new output entry points are hard errors.
        """
        factory = _make_factory(api_version=99)
        ep = _FakeEntryPoint("too_new", "pkg:factory", lambda: factory)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertRaisesRegex(EleanorException, "supports up to"):
                available_output_sinks()
