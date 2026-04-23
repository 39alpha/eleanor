"""
Registry and discovery for eleanor kernel plugins.

Each kernel plugin registers a :class:`KernelSpec` — a small dataclass that
bundles two callables: one that parses a raw settings dict into the kernel's
``Settings`` object, and one that instantiates the kernel from those settings
and any caller-supplied positional arguments.

Built-in kernels are registered by :mod:`eleanor.kernel` itself at package
import time (see :mod:`eleanor.kernel.__init__`), using deferred imports so
that merely importing the parent package does not drag in a built-in's heavy
transitive dependencies. Third-party kernels advertise themselves through
the ``eleanor.kernels`` entry-point group in their distribution metadata,
e.g.::

    [project.entry-points."eleanor.kernels"]
    my_kernel = "eleanor_my_kernel:kernel_spec"

An entry point may resolve to either:

* a :class:`KernelSpec` instance; or
* a zero-argument callable returning a :class:`KernelSpec`.

The second form lets plugin authors defer expensive imports until their
kernel is actually requested.

Kernel factories are typed with ``object`` rather than concrete kernel
classes so the registry module itself has no structural dependency on
:mod:`eleanor.kernel.interface` or :mod:`eleanor.kernel.config`. Callers
that need typed access are expected to validate the returned values with
:func:`isinstance` before use.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = 'eleanor.kernels'

#: Environment variable that, when truthy, allows plugin registrations to
#: override built-in or previously-registered kernels.
OVERRIDE_ENV_VAR = 'ELEANOR_KERNEL_OVERRIDES'

#: Raw settings mapping shape (``kernel.args`` in an order file).
SettingsRaw: TypeAlias = dict[str, object]

#: Callable that converts a raw mapping into a kernel-specific Settings
#: object. The concrete return value is a subclass of
#: :class:`eleanor.kernel.config.Settings` at runtime; typed as ``object``
#: here to keep this module decoupled from ``kernel.config``.
SettingsFromDict: TypeAlias = Callable[[SettingsRaw], object]

#: Callable that constructs a concrete
#: :class:`~eleanor.kernel.interface.AbstractKernel` from its Settings
#: (first positional argument) plus any extra CLI / caller-supplied args.
#: Typed as returning ``object`` to avoid importing the interface here.
KernelBuild: TypeAlias = Callable[..., object]


@dataclass(frozen=True)
class KernelSpec(object):
    """Descriptor object each kernel plugin registers.

    :param settings_from_dict: callable that parses a raw settings mapping
        (the value of ``kernel.args`` in an order file) into the kernel's
        ``Settings`` object. The return value is stored on the order and
        later passed to :attr:`build`.
    :param build: callable invoked as ``build(settings, *kernel_args)`` to
        construct the concrete :class:`~eleanor.kernel.interface.AbstractKernel`
        instance at run time.
    """
    settings_from_dict: SettingsFromDict
    build: KernelBuild


#: A factory is either a ready :class:`KernelSpec` or a zero-arg callable
#: returning one. Entry-point-loaded objects always start life typed as
#: ``object`` and are narrowed by :func:`_coerce_to_spec`.
KernelFactory: TypeAlias = KernelSpec | Callable[[], KernelSpec]


def _coerce_to_spec(name: str, factory: object) -> KernelSpec:
    """Accept a :class:`KernelSpec` directly or a zero-arg callable returning one."""
    if isinstance(factory, KernelSpec):
        return factory
    if callable(factory):
        try:
            produced = factory()
        except TypeError as e:
            raise EleanorException(
                f'kernel plugin "{name}" factory is not a zero-argument callable',
            ) from e
        if not isinstance(produced, KernelSpec):
            raise EleanorException(
                f'kernel plugin "{name}" factory must return a KernelSpec, '
                + f'got {type(produced).__name__}',
            )
        return produced
    raise EleanorException(
        f'kernel plugin "{name}" must be a KernelSpec or a zero-arg callable '
        + f'returning one (got {type(factory).__name__})',
    )


#: Canonical names of the kernels shipped inside the eleanor distribution.
#: The actual :class:`KernelSpec` for each built-in is registered by
#: :mod:`eleanor.kernel` at package import time; the names are hard-coded
#: here so overrides can be rejected even before ``eleanor.kernel`` has been
#: fully initialized.
BUILTIN_KERNELS: frozenset[str] = frozenset({'eq36'})

#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[KernelSpec] = PluginRegistry(
    kind='kernel',
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_KERNELS,
    validator=_coerce_to_spec,
)


def register_kernel(name: str, spec: KernelFactory) -> None:
    """Register ``spec`` under ``name`` in the kernel registry.

    See :meth:`PluginRegistry.register` for collision semantics. Both a
    :class:`KernelSpec` instance and a zero-arg callable returning one are
    accepted; :func:`_coerce_to_spec` narrows the value before storage.
    """
    registry.register(name, spec)


def available_kernels() -> frozenset[str]:
    """Return the set of currently-registered kernel names.

    The first call triggers entry-point discovery.
    """
    return registry.available()


def get_factory(name: str) -> KernelSpec:
    """Return the :class:`KernelSpec` registered under ``name``.

    Raises :class:`~eleanor.exceptions.EleanorException` if ``name`` is
    unknown.
    """
    return registry.get(name)
