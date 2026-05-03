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
from unittest import mock

from eleanor.eleanor import Eleanor
from eleanor.exceptions import EleanorException
from eleanor.executor import AbstractExecutor, build_executor
from eleanor.executor.registry import registry as executor_registry
from eleanor.kernel.registry import KernelSpec, registry as kernel_registry
from eleanor.navigator.registry import registry as navigator_registry
from eleanor.order import NavigatorProtocol  # noqa: F401
from eleanor.output import OutputSink  # noqa: F401
from eleanor.output.registry import registry as output_registry

from .common import TestCase


def _stamp(obj, version: int = 1):
    obj.__eleanor_api_version__ = version
    return obj


class _RegistrySnapshot:
    """Mixin that snapshots/restores a registry's mutable state."""

    def _snapshot(self, registry) -> None:
        self._saved_entries = dict(registry._registry)
        self._saved_discovered = registry._discovered
        self._registry = registry

    def _restore(self) -> None:
        self._registry._registry.clear()
        self._registry._registry.update(self._saved_entries)
        self._registry._discovered = self._saved_discovered


class TestBuildExecutorErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the use-site wrapper in :func:`eleanor.executor.build_executor`.
    """

    def setUp(self) -> None:
        self._snapshot(executor_registry)

    def tearDown(self) -> None:
        self._restore()

    def test_abstract_subclass_typeerror_is_wrapped(self):
        """
        Ensure a plugin whose class misses an abstract method is rethrown as EleanorException.
        """

        class _IncompleteExecutor(AbstractExecutor):
            # Deliberately omit ``submit`` and ``shutdown`` overrides so the
            # ``ABCMeta`` instantiation in the factory raises ``TypeError``.
            pass

        def factory(_num_workers):
            return _IncompleteExecutor()  # pyright: ignore[reportAbstractUsage]

        _stamp(factory, 1)
        executor_registry.register("incomplete", factory)
        with self.assertRaisesRegex(EleanorException, 'executor plugin "incomplete" failed to instantiate'):
            _ = build_executor(kind="incomplete")

    def test_abstract_subclass_typeerror_message_includes_api_version(self):
        """
        Ensure the wrapped error mentions the plugin's resolved API version.
        """

        class _IncompleteExecutor(AbstractExecutor):
            pass

        def factory(_num_workers):
            return _IncompleteExecutor()  # pyright: ignore[reportAbstractUsage]

        _stamp(factory, 1)
        executor_registry.register("incomplete2", factory)
        with self.assertRaisesRegex(EleanorException, r"API v1"):
            _ = build_executor(kind="incomplete2")

    def test_unrelated_typeerror_propagates(self):
        """
        Ensure a non-abstract TypeError from inside the factory is not rewrapped.
        """

        def factory(_num_workers):
            raise TypeError("argument of type 'int' is not iterable")

        _stamp(factory, 1)
        executor_registry.register("typeerror", factory)
        with self.assertRaisesRegex(TypeError, "is not iterable"):
            _ = build_executor(kind="typeerror")

    def test_non_executor_return_is_rejected(self):
        """
        Ensure a factory returning a non-AbstractExecutor is rejected with EleanorException.
        """

        def factory(_num_workers):
            return "not-an-executor"

        _stamp(factory, 1)
        executor_registry.register("badreturn", factory)
        with self.assertRaisesRegex(EleanorException, "expected an AbstractExecutor"):
            _ = build_executor(kind="badreturn")


class TestLoadKernelErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the use-site wrapper in :meth:`Eleanor.load_kernel`.
    """

    def setUp(self) -> None:
        self._snapshot(kernel_registry)

    def tearDown(self) -> None:
        self._restore()

    def _make_eleanor(self) -> Eleanor:
        config = SimpleNamespace(
            database="db",
            output=SimpleNamespace(type="postgres", args={}),
            parallel=SimpleNamespace(backend="multiprocessing", chunks_per_worker=1),
        )
        return Eleanor(config, ["arg1"])

    def _make_order(self, kernel_type: str):
        return SimpleNamespace(
            kernel=SimpleNamespace(
                type=kernel_type,
                resolved_settings=lambda: SimpleNamespace(),
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
        eleanor = self._make_eleanor()
        with self.assertRaisesRegex(EleanorException, 'kernel plugin "flawed" failed to instantiate'):
            _ = eleanor.load_kernel(self._make_order("flawed"))  # type: ignore[arg-type]

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
        eleanor = self._make_eleanor()
        with self.assertRaisesRegex(TypeError, "argument count mismatch"):
            _ = eleanor.load_kernel(self._make_order("typeerror"))  # type: ignore[arg-type]


class TestLoadOutputSinkErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the use-site wrapper in :meth:`Eleanor.load_output_sink`.
    """

    def setUp(self) -> None:
        self._snapshot(output_registry)

    def tearDown(self) -> None:
        self._restore()

    def _make_eleanor(self, sink_type: str) -> Eleanor:
        config = SimpleNamespace(
            database="db",
            output=SimpleNamespace(type=sink_type, args={}),
            parallel=SimpleNamespace(backend="multiprocessing", chunks_per_worker=1),
        )
        return Eleanor(config, [])

    def test_abstract_subclass_typeerror_is_wrapped(self):
        """
        Ensure an incomplete OutputSink subclass produces an EleanorException.
        """

        class _IncompleteSink(ABC):
            @abstractmethod
            def begin_run(self, order):  # pragma: no cover - never called
                pass

        def factory(_config, *, verbose: bool = False, **_args):
            return _IncompleteSink()  # pyright: ignore[reportAbstractUsage]

        _stamp(factory, 1)
        output_registry.register("flawed", factory)
        eleanor = self._make_eleanor("flawed")
        with self.assertRaisesRegex(EleanorException, 'output sink plugin "flawed" failed to instantiate'):
            _ = eleanor.load_output_sink()

    def test_unrelated_typeerror_propagates(self):
        """
        Ensure unrelated TypeErrors in the sink builder propagate.
        """

        def factory(_config, *, verbose: bool = False, **_args):
            raise TypeError("unsupported operand")

        _stamp(factory, 1)
        output_registry.register("typeerror", factory)
        eleanor = self._make_eleanor("typeerror")
        with self.assertRaisesRegex(TypeError, "unsupported operand"):
            _ = eleanor.load_output_sink()


class TestDispatchNavigatorErrorWrapping(_RegistrySnapshot, TestCase):
    """
    Tests of the navigator-loading wrapper reached via :meth:`Eleanor.run`.

    ``run`` only reaches navigator construction when ``navigator`` is not
    supplied; these tests pin kernel/executor/sink to minimal stubs so they
    assert only on navigator-factory error handling.
    """

    def setUp(self) -> None:
        self._snapshot(navigator_registry)

    def tearDown(self) -> None:
        self._restore()

    def _make_eleanor(self, executor) -> Eleanor:
        config = SimpleNamespace(
            database="db",
            output=SimpleNamespace(type="postgres", args={}),
            parallel=SimpleNamespace(backend="multiprocessing", chunks_per_worker=1),
        )
        return Eleanor(config, [], executor=executor)

    def _order_with_navigator(self, navigator_type: str):
        return SimpleNamespace(
            navigator=SimpleNamespace(type=navigator_type, args={}),
            id=None,
        )

    def _executor_stub(self):
        return SimpleNamespace(num_workers=1)

    def test_abstract_subclass_typeerror_is_wrapped(self):
        """
        Ensure an incomplete navigator factory rewraps the TypeError.
        """

        def factory(_order, _kernel, **_args):
            raise TypeError("Can't instantiate abstract class FakeNav")

        _stamp(factory, 1)
        navigator_registry.register("flawed", factory)
        executor = self._executor_stub()
        eleanor = self._make_eleanor(executor)
        sink = mock.Mock()
        with self.assertRaisesRegex(EleanorException, 'navigator plugin "flawed" failed to instantiate'):
            _ = eleanor.run(
                self._order_with_navigator("flawed"),  # type: ignore[arg-type]
                simulation_size=1,
                kernel=mock.Mock(),
                output_sink=sink,
            )

    def test_unrelated_typeerror_propagates(self):
        """
        Ensure unrelated TypeErrors from the navigator factory propagate.
        """

        def factory(_order, _kernel, **_args):
            raise TypeError("unexpected keyword argument 'foo'")

        _stamp(factory, 1)
        navigator_registry.register("typeerror", factory)
        executor = self._executor_stub()
        eleanor = self._make_eleanor(executor)
        sink = mock.Mock()
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument"):
            _ = eleanor.run(
                self._order_with_navigator("typeerror"),  # type: ignore[arg-type]
                simulation_size=1,
                kernel=mock.Mock(),
                output_sink=sink,
            )
