from typing import override
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.kernel.registry import (
    BUILTIN_KERNELS,
    KernelSpec,
    available_kernels,
    get_factory,
    register_kernel,
    registry,
)

from ..common import TestCase

_ = available_kernels()  # ensure builtins are discovered before registry snapshots


class _KernelRegistryTestCase(TestCase):
    """Base class that snapshots / restores kernel registry state between tests."""

    _saved_entries: dict[str, KernelSpec] = {}
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


class _FakeEntryPoint:
    """Lightweight stand-in for :class:`importlib.metadata.EntryPoint`."""

    def __init__(self, name: str, value: str, loader):
        self.name = name
        self.value = value
        self._loader = loader

    def load(self):
        return self._loader()


def _spec(settings_ret=None, build_ret=None) -> KernelSpec:
    return KernelSpec(
        settings_from_dict=mock.Mock(return_value=settings_ret),
        build=mock.Mock(return_value=build_ret),
    )


class TestBuiltin(TestCase):
    """
    Sanity checks on the built-in eq36 kernel.
    """

    def test_eq36_is_registered(self):
        """
        Ensure eq36 is always present in the registry.
        """
        self.assertIn("eq36", BUILTIN_KERNELS)
        self.assertIn("eq36", available_kernels())
        spec = get_factory("eq36")
        self.assertIsInstance(spec, KernelSpec)


class TestRegisterKernel(_KernelRegistryTestCase):
    """
    Tests of :func:`register_kernel`.
    """

    def test_register_spec_directly(self):
        """
        Ensure a KernelSpec can be registered and retrieved by name.
        """
        spec = _spec(settings_ret="parsed", build_ret="kernel")
        register_kernel("fake", spec)

        self.assertIn("fake", available_kernels())
        self.assertIs(get_factory("fake"), spec)

    def test_register_zero_arg_callable_returning_spec(self):
        """
        Ensure a zero-arg callable factory is accepted and its spec is unwrapped.
        """
        spec = _spec()
        register_kernel("lazy", lambda: spec)

        self.assertIs(get_factory("lazy"), spec)

    def test_register_rejects_callable_returning_non_spec(self):
        """
        Ensure factory callables that don't return a KernelSpec are rejected.
        """
        with self.assertRaises(EleanorException):
            register_kernel("bad", lambda: "not a spec")  # pyright: ignore[reportArgumentType]

    def test_register_rejects_bool_plugin_api_version(self):
        """
        Ensure a KernelSpec with bool plugin_api_version is rejected.
        """
        # ``bool`` is a subclass of ``int`` in Python; the dataclass field
        # annotation does not enforce the distinction at construction, so the
        # registry has to reject it explicitly to keep the version comparison
        # honest.
        bad_spec = KernelSpec(
            settings_from_dict=mock.Mock(),
            build=mock.Mock(),
            plugin_api_version=True,
        )
        with self.assertRaisesRegex(EleanorException, "plugin_api_version must be int"):
            register_kernel("bad", bad_spec)

    def test_register_rejects_float_plugin_api_version(self):
        """
        Ensure a KernelSpec with non-int plugin_api_version is rejected.
        """
        bad_spec = KernelSpec(
            settings_from_dict=mock.Mock(),
            build=mock.Mock(),
            plugin_api_version=1.5,  # pyright: ignore[reportArgumentType]
        )
        with self.assertRaisesRegex(EleanorException, "plugin_api_version must be int"):
            register_kernel("bad", bad_spec)

    def test_register_rejects_builtin_name(self):
        """
        Ensure built-in kernel names cannot be registered over.
        """
        replacement = _spec()
        with self.assertRaisesRegex(EleanorException, "built-in kernel"):
            register_kernel("eq36", replacement)


class TestEntryPointDiscovery(_KernelRegistryTestCase):
    """
    Tests of lazy entry-point discovery on the kernel registry.
    """

    @override
    def setUp(self) -> None:
        super().setUp()
        registry._discovered = False

    def test_discovery_accepts_spec_entry_point(self):
        """
        Ensure entry points that resolve to a :class:`KernelSpec` register directly.
        """
        spec = _spec()
        ep = _FakeEntryPoint("plugin", "pkg:spec", lambda: spec)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            self.assertIn("plugin", available_kernels())
        self.assertIs(get_factory("plugin"), spec)

    def test_discovery_accepts_factory_returning_spec(self):
        """
        Ensure entry points resolving to a zero-arg callable returning a spec are accepted.
        """
        spec = _spec()
        ep = _FakeEntryPoint("lazy", "pkg:build_spec", lambda: lambda: spec)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            self.assertIn("lazy", available_kernels())
        self.assertIs(get_factory("lazy"), spec)

    def test_discovery_raises_on_invalid_factory(self):
        """
        Ensure entry points that resolve to an invalid factory are hard errors.
        """
        ep = _FakeEntryPoint("broken", "pkg:bogus", lambda: "not a spec or callable")

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertRaisesRegex(EleanorException, "must be a KernelSpec"):
                available_kernels()

    def test_discovery_raises_on_too_new_api_plugin(self):
        """
        Ensure too-new kernel entry points are hard errors.
        """
        spec = KernelSpec(
            settings_from_dict=_spec().settings_from_dict,
            build=_spec().build,
            plugin_api_version=99,
        )
        ep = _FakeEntryPoint("too_new", "pkg:spec", lambda: spec)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertRaisesRegex(EleanorException, "supports up to"):
                available_kernels()
