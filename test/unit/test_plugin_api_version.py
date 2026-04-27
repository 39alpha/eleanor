"""Tests for the plugin API-version helpers in :mod:`eleanor.plugin`."""

import os
import sys
import types
import warnings
from abc import ABC, abstractmethod
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.plugin import (
    PLUGIN_API_VERSIONS,
    OverrideWarning,
    check_api_version,
    is_abstract_instantiation_error,
    resolve_api_version,
)

from .common import TestCase


class TestCheckApiVersion(TestCase):
    """
    Tests of :func:`check_api_version`.
    """

    def test_returns_declared_when_in_range(self):
        """
        Ensure in-range declarations are accepted unchanged.
        """
        self.assertEqual(
            check_api_version(
                kind="navigator",
                name="plugin",
                declared=1,
                current=2,
                floor=1,
                override_env_var="ELEANOR_TEST_OVERRIDE",
            ),
            1,
        )

    def test_returns_floor_when_unversioned_and_warns_once(self):
        """
        Ensure unversioned plugins assume floor and warn only once per name.
        """
        warned: set[str] = set()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            first = check_api_version(
                kind="output",
                name="plugin",
                declared=None,
                current=1,
                floor=1,
                override_env_var="ELEANOR_TEST_OVERRIDE",
                warned=warned,
            )
            second = check_api_version(
                kind="output",
                name="plugin",
                declared=None,
                current=1,
                floor=1,
                override_env_var="ELEANOR_TEST_OVERRIDE",
                warned=warned,
            )
        runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)
        self.assertEqual(len(runtime), 1)

    def test_unversioned_warning_text_includes_actionable_hint(self):
        """
        Ensure the unversioned warning tells the author how to silence it.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _ = check_api_version(
                kind="output",
                name="plugin",
                declared=None,
                current=1,
                floor=1,
                override_env_var="ELEANOR_TEST_OVERRIDE",
            )
        runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        self.assertEqual(len(runtime), 1)
        self.assertIn("__eleanor_api_version__", str(runtime[0].message))

    def test_rejects_too_new(self):
        """
        Ensure plugins targeting newer-than-supported APIs are rejected.
        """
        with self.assertRaises(EleanorException) as ctx:
            _ = check_api_version(
                kind="executor",
                name="plugin",
                declared=3,
                current=2,
                floor=1,
                override_env_var="ELEANOR_TEST_OVERRIDE",
            )
        self.assertIn("v3", str(ctx.exception))
        self.assertIn("v2", str(ctx.exception))

    def test_rejects_below_floor(self):
        """
        Ensure plugins below the minimum supported API are rejected.
        """
        with self.assertRaises(EleanorException):
            _ = check_api_version(
                kind="transformer",
                name="plugin",
                declared=1,
                current=3,
                floor=2,
                override_env_var="ELEANOR_TEST_OVERRIDE",
            )

    def test_override_env_downgrades_too_new_to_warning(self):
        """
        Ensure override env var downgrades hard mismatch to OverrideWarning.
        """
        with mock.patch.dict(os.environ, {"X": "1"}):
            with self.assertWarnsRegex(OverrideWarning, "loading anyway because X is set"):
                resolved = check_api_version(
                    kind="navigator",
                    name="plugin",
                    declared=3,
                    current=2,
                    floor=1,
                    override_env_var="X",
                )
        self.assertEqual(resolved, 3)

    def test_override_env_downgrades_below_floor_to_warning(self):
        """
        Ensure override env var downgrades below-floor rejection to OverrideWarning.
        """
        with mock.patch.dict(os.environ, {"X": "1"}):
            with self.assertWarnsRegex(OverrideWarning, "loading anyway because X is set"):
                resolved = check_api_version(
                    kind="navigator",
                    name="plugin",
                    declared=1,
                    current=3,
                    floor=2,
                    override_env_var="X",
                )
        self.assertEqual(resolved, 1)


class TestResolveApiVersion(TestCase):
    """
    Tests of :func:`resolve_api_version`.
    """

    def test_factory_attr(self):
        """
        Ensure declaration on the factory object is preferred.
        """

        def f() -> None:
            return None

        f.__eleanor_api_version__ = 4  # pyright: ignore[reportFunctionMemberAccess]
        self.assertEqual(resolve_api_version(f), 4)

    def test_module_attr_fallback(self):
        """
        Ensure declaration falls back to factory module when needed.
        """
        module_name = "test_plugin_api_version_fake_mod"
        module = types.ModuleType(module_name)
        module.__eleanor_api_version__ = 5  # pyright: ignore[reportAttributeAccessIssue]
        sys.modules[module_name] = module
        try:

            def f() -> None:
                return None

            f.__module__ = module_name
            self.assertEqual(resolve_api_version(f), 5)
        finally:
            sys.modules.pop(module_name, None)

    def test_returns_none_when_missing_or_wrong_type(self):
        """
        Ensure missing or non-int declarations resolve to ``None``.
        """

        def f() -> None:
            return None

        self.assertIsNone(resolve_api_version(f))
        f.__eleanor_api_version__ = True  # pyright: ignore[reportFunctionMemberAccess]
        self.assertIsNone(resolve_api_version(f))
        f.__eleanor_api_version__ = "1"  # pyright: ignore[reportFunctionMemberAccess]
        self.assertIsNone(resolve_api_version(f))


class TestIsAbstractInstantiationError(TestCase):
    """
    Tests of :func:`is_abstract_instantiation_error`.
    """

    def test_detects_abstract_class_typeerror(self):
        """
        Ensure ABCMeta's instantiation TypeError is recognised.
        """

        class Abstract(ABC):
            @abstractmethod
            def do(self) -> None:
                pass

        with self.assertRaises(TypeError) as ctx:
            _ = Abstract()  # pyright: ignore[reportAbstractUsage]
        self.assertTrue(is_abstract_instantiation_error(ctx.exception))

    def test_returns_false_for_unrelated_typeerror(self):
        """
        Ensure unrelated TypeErrors are not misclassified.
        """
        self.assertFalse(is_abstract_instantiation_error(TypeError("argument of type 'int' is not iterable")))
        self.assertFalse(is_abstract_instantiation_error(TypeError("expected str, got bytes")))


class TestOverrideWarning(TestCase):
    """
    Tests of the dedicated :class:`OverrideWarning` category.
    """

    def test_is_runtime_warning_subclass(self):
        """
        Ensure OverrideWarning remains compatible with RuntimeWarning catch sites.
        """
        self.assertTrue(issubclass(OverrideWarning, RuntimeWarning))

    def test_distinguishable_from_other_runtime_warnings(self):
        """
        Ensure callers can filter on OverrideWarning specifically.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warnings.warn("plain", RuntimeWarning)
            warnings.warn("override", OverrideWarning)
        categories = [w.category for w in caught]
        self.assertIn(RuntimeWarning, categories)
        self.assertIn(OverrideWarning, categories)
        # OverrideWarning entries are still RuntimeWarnings on the class side.
        self.assertEqual(
            sum(1 for w in caught if issubclass(w.category, OverrideWarning)),
            1,
        )


class TestPluginApiVersionsMap(TestCase):
    """
    Tests of the public :data:`PLUGIN_API_VERSIONS` introspection map.
    """

    def test_includes_all_builtin_extension_points(self):
        """
        Ensure the five built-in extension points are advertised.
        """
        # Importing the per-extension-point modules populates the map.
        import eleanor.executor  # noqa: F401
        import eleanor.kernel  # noqa: F401
        import eleanor.navigator  # noqa: F401
        import eleanor.output  # noqa: F401
        import eleanor.transformer  # noqa: F401

        for kind in ("executor", "kernel", "navigator", "output", "transformer"):
            self.assertIn(kind, PLUGIN_API_VERSIONS, msg=f"{kind} missing from PLUGIN_API_VERSIONS")

    def test_returns_current_floor_pair(self):
        """
        Ensure each entry is a ``(current, floor)`` pair of integers.
        """
        import eleanor.executor  # noqa: F401

        current, floor = PLUGIN_API_VERSIONS["executor"]
        self.assertIsInstance(current, int)
        self.assertIsInstance(floor, int)
        self.assertGreaterEqual(current, floor)
