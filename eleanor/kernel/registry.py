"""
Registry and discovery for eleanor kernel plugins.

Each kernel plugin registers a :class:`KernelSpec` — a small dataclass that
bundles two callables: one that parses a raw settings dict into the kernel's
``Settings`` object, and one that instantiates the kernel from those settings
and any caller-supplied positional arguments.

Built-in kernels (``eq36``) are registered at module import time. Third-party
kernels advertise themselves through the ``eleanor.kernels`` entry-point group
in their distribution metadata, e.g.::

    [project.entry-points."eleanor.kernels"]
    my_kernel = "eleanor_my_kernel:kernel_spec"

An entry point may resolve to either:

* a :class:`KernelSpec` instance; or
* a zero-argument callable returning a :class:`KernelSpec`.

The second form lets plugin authors defer expensive imports until their
kernel is actually requested.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

if TYPE_CHECKING:
    from .interface import AbstractKernel

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = 'eleanor.kernels'

#: Environment variable that, when truthy, allows plugin registrations to
#: override built-in or previously-registered kernels.
OVERRIDE_ENV_VAR = 'ELEANOR_KERNEL_OVERRIDES'


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
    settings_from_dict: Callable[[dict[str, Any]], Any]
    build: Callable[..., 'AbstractKernel']


def _coerce_to_spec(name: str, factory: Any) -> KernelSpec:
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
                f'got {type(produced).__name__}',
            )
        return produced
    raise EleanorException(
        f'kernel plugin "{name}" must be a KernelSpec or a zero-arg callable '
        f'returning one (got {type(factory).__name__})',
    )


# --- Built-in eq36 kernel ---------------------------------------------------
def _eq36_settings_from_dict(raw: dict[str, Any]) -> Any:
    from .eq36 import Settings

    return Settings.from_dict(raw)


def _eq36_build(settings: Any, *args: Any) -> 'AbstractKernel':
    from .eq36 import Kernel

    return Kernel(settings, *args)


_EQ36_SPEC = KernelSpec(
    settings_from_dict=_eq36_settings_from_dict,
    build=_eq36_build,
)

#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[KernelSpec] = PluginRegistry(
    kind='kernel',
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={
        'eq36': _EQ36_SPEC,
    },
    validator=_coerce_to_spec,
)

#: Canonical names of the kernels shipped inside the eleanor distribution.
BUILTIN_KERNELS: frozenset[str] = registry.builtins


def register_kernel(name: str, spec: KernelSpec | Callable[[], KernelSpec]) -> None:
    """Register ``spec`` under ``name`` in the kernel registry.

    See :meth:`PluginRegistry.register` for collision semantics.
    """
    registry.register(name, spec)  # type: ignore[arg-type]


def available_kernels() -> frozenset[str]:
    """Return the set of currently-registered kernel names.

    The first call triggers entry-point discovery.
    """
    return registry.available()


def get_spec(name: str) -> KernelSpec:
    """Return the :class:`KernelSpec` registered under ``name``.

    Raises :class:`~eleanor.exceptions.EleanorException` if ``name`` is
    unknown.
    """
    return registry.get(name)
