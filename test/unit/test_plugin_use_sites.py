"""Tests of use-site error wrappers for plugin instantiation.

Each plugin extension point's use site catches :class:`TypeError`,
checks whether it came from :class:`abc.ABCMeta` (i.e. the plugin
forgot to override an ``@abstractmethod``), and re-raises as
:class:`EleanorException` with the plugin name and resolved API
version. Unrelated ``TypeError``s must propagate unchanged so the
original traceback survives.
"""

from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import cast, override

from eleanor.exceptions import EleanorException
from eleanor.executor import AbstractExecutor, load_executor
from eleanor.executor.registry import registry as executor_registry
from eleanor.kernel import load_kernel
from eleanor.kernel.registry import KernelSpec
from eleanor.kernel.registry import registry as kernel_registry
from eleanor.navigator import load_navigator
from eleanor.navigator.registry import registry as navigator_registry
from eleanor.order import Order
from eleanor.output import load_output_sink
from eleanor.output.registry import registry as output_registry
from eleanor.plugin import PluginRegistry

from .common import TestCase


def _stamp(obj, version: int = 1):
    obj.__eleanor_api_version__ = version
    return obj


class _RegistrySnapshot:
    """Mixin that snapshots/restores a registry's mutable state."""

    _saved_entries: dict[str, object] = {}
    _saved_discovered: bool = False
    _registry: PluginRegistry[object] = cast(PluginRegistry[object], object())

    def _snapshot(self, registry: object) -> None:
        typed_registry = cast(PluginRegistry[object], registry)
        self._saved_entries = dict(typed_registry._registry)
        self._saved_discovered = typed_registry._discovered
        self._registry = typed_registry

    def _restore(self) -> None:
        self._registry._registry.clear()
        self._registry._registry.update(self._saved_entries)
        self._registry._discovered = self._saved_discovered


class TestLoadExecutorErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the use-site wrapper in :func:`eleanor.executor.load_executor`.
    """

    @override
    def setUp(self) -> None:
        self._snapshot(executor_registry)

    @override
    def tearDown(self) -> None:
        self._restore()

    def test_abstract_subclass_typeerror_is_wrapped(self):
        """
        Ensure a plugin whose class misses an abstract method is rethrown as EleanorException.
        """

        class _IncompleteExecutor(AbstractExecutor, ABC):
            # Deliberately omit ``submit`` and ``shutdown`` overrides so the
            # ``ABCMeta`` instantiation in the factory raises ``TypeError``.
            pass

        def factory(_num_workers):
            return _IncompleteExecutor()  # pyright: ignore[reportAbstractUsage]

        _stamp(factory, 1)
        executor_registry.register("incomplete", factory)
        with self.assertRaisesRegex(EleanorException, "executor plugin 'incomplete' failed to instantiate"):
            _ = load_executor(kind="incomplete")

    def test_abstract_subclass_typeerror_message_includes_api_version(self):
        """
        Ensure the wrapped error mentions the plugin's resolved API version.
        """

        class _IncompleteExecutor(AbstractExecutor, ABC):
            pass

        def factory(_num_workers):
            return _IncompleteExecutor()  # pyright: ignore[reportAbstractUsage]

        _stamp(factory, 1)
        executor_registry.register("incomplete2", factory)
        with self.assertRaisesRegex(EleanorException, r"API v1"):
            _ = load_executor(kind="incomplete2")

    def test_unrelated_typeerror_propagates(self):
        """
        Ensure a non-abstract TypeError from inside the factory is not rewrapped.
        """

        def factory(_num_workers):
            raise TypeError("argument of type 'int' is not iterable")

        _stamp(factory, 1)
        executor_registry.register("typeerror", factory)
        with self.assertRaisesRegex(TypeError, "is not iterable"):
            _ = load_executor(kind="typeerror")

    def test_non_executor_return_is_rejected(self):
        """
        Ensure a factory returning a non-AbstractExecutor is rejected with EleanorException.
        """

        def factory(_num_workers):
            return "not-an-executor"

        _stamp(factory, 1)
        executor_registry.register("badreturn", factory)
        with self.assertRaisesRegex(EleanorException, "expected an AbstractExecutor"):
            _ = load_executor(kind="badreturn")


class TestLoadKernelErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the use-site wrapper in :func:`eleanor.kernel.load_kernel`.
    """

    @override
    def setUp(self) -> None:
        self._snapshot(kernel_registry)

    @override
    def tearDown(self) -> None:
        self._restore()

    def _make_order(self, kernel_type: str) -> Order:
        return cast(
            Order,
            cast(
                object,
                SimpleNamespace(
                    kernel=SimpleNamespace(
                        type=kernel_type,
                        resolved_settings=lambda: SimpleNamespace(),
                    ),
                ),
            ),
        )

    def test_abstract_subclass_typeerror_is_wrapped(self):
        """
        Ensure load_kernel rewraps an abstract instantiation TypeError.
        """

        def build_fn(_settings, *_args):
            raise TypeError("Can't instantiate abstract class FakeKernel")

        spec = KernelSpec(
            settings_from_dict=lambda raw: raw,
            build=build_fn,
            plugin_api_version=1,
        )
        kernel_registry.register("flawed", spec)
        with self.assertRaisesRegex(EleanorException, "kernel plugin 'flawed' failed to instantiate"):
            _ = load_kernel(self._make_order("flawed"), ["arg1"])

    def test_unrelated_typeerror_propagates(self):
        """
        Ensure non-abstract TypeErrors in the kernel build propagate.
        """

        def build_fn(_settings, *_args):
            raise TypeError("argument count mismatch")

        spec = KernelSpec(
            settings_from_dict=lambda raw: raw,
            build=build_fn,
            plugin_api_version=1,
        )
        kernel_registry.register("typeerror", spec)
        with self.assertRaisesRegex(TypeError, "argument count mismatch"):
            _ = load_kernel(self._make_order("typeerror"), ["arg1"])


class TestLoadOutputSinkErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the use-site wrapper in :func:`eleanor.output.load_output_sink`.
    """

    @override
    def setUp(self) -> None:
        self._snapshot(output_registry)

    @override
    def tearDown(self) -> None:
        self._restore()

    def test_abstract_subclass_typeerror_is_wrapped(self):
        """
        Ensure an incomplete OutputSink subclass produces an EleanorException.
        """

        class _IncompleteSink(ABC):
            @abstractmethod
            def begin_run(self, order):  # pragma: no cover - never called
                pass

        def factory(*, verbose: bool = False, **_args):
            return _IncompleteSink()  # pyright: ignore[reportAbstractUsage]

        _stamp(factory, 1)
        output_registry.register("flawed", factory)
        with self.assertRaisesRegex(EleanorException, "output sink plugin 'flawed' failed to instantiate"):
            _ = load_output_sink("flawed")

    def test_unrelated_typeerror_propagates(self):
        """
        Ensure unrelated TypeErrors in the sink builder propagate.
        """

        def factory(*, verbose: bool = False, **_args):
            raise TypeError("unsupported operand")

        _stamp(factory, 1)
        output_registry.register("typeerror", factory)
        with self.assertRaisesRegex(TypeError, "unsupported operand"):
            _ = load_output_sink("typeerror")


class TestLoadNavigatorErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the use-site wrapper in :func:`eleanor.navigator.load_navigator`.
    """

    @override
    def setUp(self) -> None:
        self._snapshot(navigator_registry)

    @override
    def tearDown(self) -> None:
        self._restore()

    def test_abstract_subclass_typeerror_is_wrapped(self):
        """
        Ensure an incomplete navigator factory rewraps the TypeError.
        """

        def factory(**_args):
            raise TypeError("Can't instantiate abstract class FakeNav")

        _stamp(factory, 1)
        navigator_registry.register("flawed", factory)
        with self.assertRaisesRegex(EleanorException, "navigator plugin 'flawed' failed to instantiate"):
            _ = load_navigator("flawed")

    def test_unrelated_typeerror_propagates(self):
        """
        Ensure unrelated TypeErrors from the navigator factory propagate.
        """

        def factory(**_args):
            raise TypeError("unexpected keyword argument 'foo'")

        _stamp(factory, 1)
        navigator_registry.register("typeerror", factory)
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument"):
            _ = load_navigator("typeerror")
