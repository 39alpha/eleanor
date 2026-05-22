from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

ENTRY_POINT_GROUP = "eleanor.kernels"

OVERRIDE_ENV_VAR = "ELEANOR_KERNEL_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

type SettingsRaw = dict[str, object]

type SettingsFromDict = Callable[[SettingsRaw], object]

type KernelBuild = Callable[..., object]

type KernelFactory = KernelSpec | Callable[[], KernelSpec]


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
    :param plugin_api_version: kernel plugin API version this spec targets.
        Defaults to ``1`` for backward compatibility with existing built-ins.
    """

    settings_from_dict: SettingsFromDict
    build: KernelBuild
    plugin_api_version: int = 1


def _coerce_to_spec(name: str, factory: object) -> KernelSpec:
    """Accept a :class:`KernelSpec` directly or a zero-arg callable returning one.

    Also validates that :attr:`KernelSpec.plugin_api_version` is a real ``int``
    (rejecting ``bool``, which is a subtype of ``int`` in Python and would
    otherwise silently flow into the version comparison) before the registry
    runs its API-version check.
    """
    if isinstance(factory, KernelSpec):
        spec = factory
    elif callable(factory):
        try:
            produced = factory()
        except TypeError as e:
            msg = f"kernel plugin {name!r} factory is not a zero-argument callable"
            raise EleanorException(msg) from e
        if not isinstance(produced, KernelSpec):
            msg = f"kernel plugin {name!r} factory must return a KernelSpec, got {type(produced).__name__}"
            raise EleanorException(msg)
        spec = produced
    else:
        msg = f"kernel plugin {name!r} must be a KernelSpec or a zero-arg callable returning one (got {type(factory).__name__})"
        raise EleanorException(msg)

    declared = cast(object, spec.plugin_api_version)
    if isinstance(declared, bool) or not isinstance(declared, int):
        msg = f"kernel plugin {name!r} KernelSpec.plugin_api_version must be int, got {type(declared).__name__}"
        raise EleanorException(msg)

    return spec


def _spec_api_version(spec: KernelSpec) -> int | None:
    """Resolver hook used by :class:`PluginRegistry` for the kernel registry.

    Reads :attr:`KernelSpec.plugin_api_version` directly rather than the
    ``__eleanor_api_version__`` dunder used for bare-callable registries.
    """
    return spec.plugin_api_version


BUILTIN_KERNELS: frozenset[str] = frozenset({"eq36"})

registry: PluginRegistry[KernelSpec] = PluginRegistry(
    kind="kernel",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_KERNELS,
    validator=_coerce_to_spec,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
    api_version_resolver=_spec_api_version,
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


__all__ = [
    "ENTRY_POINT_GROUP",
    "OVERRIDE_ENV_VAR",
    "PLUGIN_API_VERSION",
    "MIN_SUPPORTED_API_VERSION",
    "BUILTIN_KERNELS",
    "KernelSpec",
    "KernelFactory",
    "SettingsRaw",
    "SettingsFromDict",
    "KernelBuild",
    "register_kernel",
    "available_kernels",
    "get_factory",
]
