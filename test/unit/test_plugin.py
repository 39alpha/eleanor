"""Tests of the generic :class:`eleanor.plugin.PluginRegistry`."""

import os
import sys
import types
import warnings
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.plugin import OverrideWarning, PluginRegistry

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
    return "builtin-ran"


def _plugin():
    return "plugin-ran"


# Built-in tests register named factories; stamp them with an API version so
# the registry does not emit the unversioned-plugin warning during normal
# fixture setup. Tests that *want* to exercise the unversioned path either
# clear the dunder explicitly or use a fresh function.
_builtin.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
_plugin.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]


def _make_registry(**overrides):
    defaults = dict(
        kind="widget",
        entry_point_group="eleanor.test.widgets",
        override_env_var="ELEANOR_WIDGET_OVERRIDES",
        builtins={"b1": _builtin},
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
        self.assertIn("b1", registry.available())
        self.assertTrue(registry.is_builtin("b1"))
        self.assertEqual(registry.builtins, frozenset({"b1"}))

    def test_register_and_get(self):
        """
        Ensure a plugin can be registered and later retrieved by name.
        """
        registry = _make_registry()
        registry.register("p1", _plugin)
        self.assertIs(registry.get("p1"), _plugin)
        self.assertFalse(registry.is_builtin("p1"))

    def test_get_unknown_name_raises(self):
        """
        Ensure ``get`` raises an informative exception for unknown names.
        """
        registry = _make_registry()
        with self.assertRaises(EleanorException) as ctx:
            registry.get("nope")
        self.assertIn("nope", str(ctx.exception))
        self.assertIn("widget", str(ctx.exception))
        self.assertIn("b1", str(ctx.exception))

    def test_register_empty_name_rejected(self):
        """
        Ensure ``register`` rejects empty names.
        """
        registry = _make_registry()
        with self.assertRaises(EleanorException):
            registry.register("", _plugin)

    def test_register_non_callable_without_validator(self):
        """
        Ensure the default validator rejects non-callable factories.
        """
        registry = _make_registry()
        with self.assertRaises(EleanorException):
            registry.register("bad", "not-callable")  # type: ignore[arg-type]

    def test_min_above_current_rejected_at_construction(self):
        """
        Ensure the registry refuses to construct with floor > current.
        """
        with self.assertRaises(EleanorException):
            _make_registry(api_version=1, min_api_version=2)

    def test_api_version_properties_expose_constants(self):
        """
        Ensure registry exposes the configured api_version pair.
        """
        # Built-ins are seeded at construction and would be rejected against a
        # floor>1; use an empty seed so the test focuses on the property
        # accessors rather than the registration path.
        registry = _make_registry(builtins={}, api_version=3, min_api_version=2)
        self.assertEqual(registry.current_api_version, 3)
        self.assertEqual(registry.min_api_version, 2)


class TestCollisionPolicy(TestCase):
    """
    Tests of the registry's builtin-vs-plugin and plugin-vs-plugin collision handling.
    """

    def test_builtin_collision_refused_without_override(self):
        """
        Ensure a plugin cannot override a built-in without the override env var.
        """
        registry = _make_registry()
        with self.assertWarnsRegex(RuntimeWarning, "refusing to override built-in"):
            registry.register("b1", _plugin)
        self.assertIs(registry.get("b1"), _builtin)

    def test_builtin_collision_allowed_with_override(self):
        """
        Ensure built-ins can be overridden when ``ELEANOR_<KIND>_OVERRIDES`` is truthy.
        """
        registry = _make_registry()
        with mock.patch.dict(os.environ, {"ELEANOR_WIDGET_OVERRIDES": "1"}):
            registry.register("b1", _plugin)
        self.assertIs(registry.get("b1"), _plugin)

    def test_plugin_collision_keeps_first(self):
        """
        Ensure plugin-vs-plugin collisions are rejected with a warning and the first wins.
        """
        registry = _make_registry()
        registry.register("p1", _plugin)

        def _other():
            return "other"

        _other.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
        with self.assertWarnsRegex(RuntimeWarning, "is already registered"):
            registry.register("p1", _other)
        self.assertIs(registry.get("p1"), _plugin)


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
        registry.register("p1", _plugin)
        self.assertIn(("b1", _builtin), calls)
        self.assertIn(("p1", _plugin), calls)

    def test_validator_can_coerce(self):
        """
        Ensure the validator can transform or replace the factory.
        """

        def sentinel():
            return "sentinel"

        sentinel.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]

        def validator(_name, _factory):
            return sentinel

        registry = _make_registry(validator=validator)
        registry.register("p1", _plugin)
        self.assertIs(registry.get("p1"), sentinel)

    def test_validator_can_reject(self):
        """
        Ensure the validator can reject a registration with an EleanorException.
        """

        def validator(name, _factory):
            if name == "bad":
                raise EleanorException("nope")
            return _factory

        registry = _make_registry(validator=validator)
        with self.assertRaises(EleanorException):
            registry.register("bad", _plugin)


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
        with mock.patch("eleanor.plugin.entry_points", ep_call):
            registry.available()
            registry.available()
            registry.get("b1")
        self.assertEqual(ep_call.call_count, 1)

    def test_discovery_registers_entry_points(self):
        """
        Ensure entry points are registered with the registry on first access.
        """
        ep = _FakeEntryPoint("p1", "pkg:factory", lambda: _plugin)
        registry = _make_registry()
        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            self.assertIn("p1", registry.available())
        self.assertIs(registry.get("p1"), _plugin)

    def test_discovery_warns_on_load_failure(self):
        """
        Ensure a failing entry-point load emits a warning and does not abort discovery.
        """

        def _fail():
            raise ImportError("boom")

        failing = _FakeEntryPoint("broken", "pkg.bad:factory", _fail)
        working = _FakeEntryPoint("good", "pkg.ok:factory", lambda: _plugin)

        registry = _make_registry()
        with mock.patch("eleanor.plugin.entry_points", return_value=[failing, working]):
            with self.assertWarnsRegex(RuntimeWarning, 'failed to load widget entry point "broken"'):
                self.assertIn("good", registry.available())
        self.assertNotIn("broken", registry.available())

    def test_discovery_warns_on_invalid_entry_point(self):
        """
        Ensure entry points rejected by the validator emit a warning and are skipped.
        """
        # The default validator rejects non-callables.
        ep = _FakeEntryPoint("bad", "pkg.bad:nothing", lambda: 42)
        registry = _make_registry()
        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertWarnsRegex(RuntimeWarning, "is invalid"):
                self.assertNotIn("bad", registry.available())


class TestApiVersionEnforcement(TestCase):
    """
    Tests of API-version-aware plugin validation in registries.
    """

    def _versioned_registry(self, *, current: int = 1, floor: int = 1) -> PluginRegistry[object]:
        return _make_registry(
            builtins={},
            api_version=current,
            min_api_version=floor,
        )

    def test_unversioned_plugin_warns_and_loads(self):
        """
        Ensure unversioned plugins are accepted with a warning.
        """
        registry = self._versioned_registry()

        def plugin():
            return "ok"

        with self.assertWarnsRegex(RuntimeWarning, "did not declare an API version"):
            registry.register("p1", plugin)
        self.assertIn("p1", registry.available())

    def test_unversioned_warning_only_fires_once_per_name(self):
        """
        Ensure repeated registrations of an unversioned plugin do not re-warn.
        """
        registry = self._versioned_registry()

        def plugin():
            return "ok"

        with self.assertWarns(RuntimeWarning):
            registry.register("p1", plugin)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            registry.register("p1", plugin)  # idempotent re-register
        self.assertEqual(
            [w for w in caught if issubclass(w.category, RuntimeWarning)],
            [],
        )

    def test_too_new_plugin_rejected(self):
        """
        Ensure plugins targeting newer API versions are rejected.
        """
        registry = self._versioned_registry(current=1, floor=1)

        def plugin():
            return "ok"

        plugin.__eleanor_api_version__ = 99  # pyright: ignore[reportFunctionMemberAccess]
        with self.assertRaises(EleanorException):
            registry.register("p1", plugin)

    def test_below_floor_plugin_rejected(self):
        """
        Ensure plugins below the minimum supported API are rejected.
        """
        registry = self._versioned_registry(current=2, floor=2)

        def plugin():
            return "ok"

        plugin.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
        with self.assertRaises(EleanorException):
            registry.register("p1", plugin)

    def test_override_env_downgrades_too_new(self):
        """
        Ensure version mismatches are downgraded when override env var is set.
        """
        registry = self._versioned_registry(current=1, floor=1)

        def plugin():
            return "ok"

        plugin.__eleanor_api_version__ = 99  # pyright: ignore[reportFunctionMemberAccess]
        with mock.patch.dict(os.environ, {"ELEANOR_WIDGET_OVERRIDES": "1"}):
            with self.assertWarnsRegex(OverrideWarning, "loading anyway"):
                registry.register("p1", plugin)
        self.assertIn("p1", registry.available())

    def test_override_env_downgrades_below_floor(self):
        """
        Ensure below-floor mismatches are also downgraded under the override env var.
        """
        registry = self._versioned_registry(current=2, floor=2)

        def plugin():
            return "ok"

        plugin.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
        with mock.patch.dict(os.environ, {"ELEANOR_WIDGET_OVERRIDES": "1"}):
            with self.assertWarnsRegex(OverrideWarning, "loading anyway"):
                registry.register("p1", plugin)
        self.assertIn("p1", registry.available())

    def test_module_attr_used_when_factory_attr_missing(self):
        """
        Ensure validators use module-level declarations when factory lacks one.
        """
        registry = self._versioned_registry(current=2, floor=1)
        module_name = "test_plugin_widget_mod"
        module = types.ModuleType(module_name)
        module.__eleanor_api_version__ = 2  # pyright: ignore[reportAttributeAccessIssue]
        sys.modules[module_name] = module
        try:

            def plugin():
                return "ok"

            plugin.__module__ = module_name
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                registry.register("p1", plugin)
            self.assertIn("p1", registry.available())
        finally:
            sys.modules.pop(module_name, None)

    def test_unversioned_warning_isolated_between_registries(self):
        """
        Ensure each registry maintains its own ``_unversioned_warned`` set.
        """
        registry_a = self._versioned_registry()
        registry_b = self._versioned_registry()

        def plugin():
            return "ok"

        with self.assertWarns(RuntimeWarning):
            registry_a.register("p1", plugin)
        # Same name in a different registry must still warn — the dedup is
        # per-registry, not module-global.
        with self.assertWarns(RuntimeWarning):
            registry_b.register("p1", plugin)


class TestBuiltInsDoNotWarn(TestCase):
    """
    Tests that built-ins shipped with eleanor declare API versions correctly.
    """

    def test_executor_builtins_do_not_warn_as_unversioned(self):
        """
        Ensure version metadata on built-in executor factories suppresses warnings.
        """
        from eleanor.executor import _build_multiprocessing, _build_serial

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _ = PluginRegistry(
                kind="executor",
                entry_point_group="eleanor.executors",
                override_env_var="ELEANOR_EXECUTOR_OVERRIDES",
                builtins={
                    "serial": _build_serial,
                    "multiprocessing": _build_multiprocessing,
                },
            )
        self.assertTrue(all(w.category is not RuntimeWarning for w in caught))

    def test_navigator_builtins_do_not_warn_as_unversioned(self):
        """
        Ensure built-in navigator factories suppress the unversioned warning.
        """
        from eleanor.navigator import get_factory as get_navigator_factory

        # Re-register every built-in into a fresh registry and assert no
        # ``did not declare`` warnings are raised.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fresh: PluginRegistry[object] = PluginRegistry(
                kind="navigator",
                entry_point_group="eleanor.test.navigators",
                override_env_var="ELEANOR_TEST_OVERRIDES",
                builtins={
                    "random": get_navigator_factory("random"),
                    "random_lattice": get_navigator_factory("random_lattice"),
                    "lattice": get_navigator_factory("lattice"),
                },
            )
            self.assertEqual(fresh.builtins, frozenset({"random", "random_lattice", "lattice"}))
        unversioned = [w for w in caught if "did not declare an API version" in str(w.message)]
        self.assertEqual(unversioned, [])
