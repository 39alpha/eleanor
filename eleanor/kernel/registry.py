"""
Registry and discovery for eleanor kernel plugins.

Each kernel plugin registers a :class:`KernelSpec` — a small dataclass that
bundles two callables: one that parses a raw settings dict into the kernel's
``Settings`` object, and one that instantiates the kernel from those settings
and any caller-supplied positional arguments.

Built-in kernels are declared as entry points in ``pyproject.toml`` and
discovered lazily on first registry access; their factories live in
:mod:`eleanor.kernel.factories` with deferred imports so that merely importing
the parent package does not drag in a built-in's heavy transitive
dependencies. Third-party kernels advertise themselves through the same
``eleanor.kernels`` entry-point group in their distribution metadata, e.g.::

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

Plugins also declare a kernel-plugin API version using
``KernelSpec.plugin_api_version``. Registration enforces compatibility against
this module's ``PLUGIN_API_VERSION`` and ``MIN_SUPPORTED_API_VERSION`` values.
See ``AGENTS.md`` for the versioning policy.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias, cast

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = "eleanor.kernels"

#: Environment variable that, when truthy, downgrades API-version mismatches
#: to warnings instead of hard errors. All other discovery and registration
#: errors are always hard errors regardless of this variable.
OVERRIDE_ENV_VAR = "ELEANOR_KERNEL_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

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
    :param plugin_api_version: kernel plugin API version this spec targets.
        Defaults to ``1`` for backward compatibility with existing built-ins.
    """

    settings_from_dict: SettingsFromDict
    build: KernelBuild
    plugin_api_version: int = 1


#: A factory is either a ready :class:`KernelSpec` or a zero-arg callable
#: returning one. Entry-point-loaded objects always start life typed as
#: ``object`` and are narrowed by :func:`_coerce_to_spec`.
KernelFactory: TypeAlias = KernelSpec | Callable[[], KernelSpec]


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
            raise EleanorException(
                f'kernel plugin "{name}" factory is not a zero-argument callable',
            ) from e
        if not isinstance(produced, KernelSpec):
            raise EleanorException(
                f'kernel plugin "{name}" factory must return a KernelSpec, ' + f"got {type(produced).__name__}",
            )
        spec = produced
    else:
        raise EleanorException(
            f'kernel plugin "{name}" must be a KernelSpec or a zero-arg callable '
            + f"returning one (got {type(factory).__name__})",
        )
    # ``KernelSpec.plugin_api_version`` is annotated ``int`` but the dataclass
    # does not enforce that at runtime, so a ``bool`` (which is a subclass of
    # ``int``) or any other type can be smuggled through.  ``cast(object, ...)``
    # forces basedpyright to treat the value as opaque so the runtime guard
    # actually inspects it rather than trusting the annotation.
    declared = cast(object, spec.plugin_api_version)
    if isinstance(declared, bool) or not isinstance(declared, int):
        raise EleanorException(
            f'kernel plugin "{name}" KernelSpec.plugin_api_version must be int, ' + f"got {type(declared).__name__}",
        )
    return spec


def _spec_api_version(spec: KernelSpec) -> int | None:
    """Resolver hook used by :class:`PluginRegistry` for the kernel registry.

    Reads :attr:`KernelSpec.plugin_api_version` directly rather than the
    ``__eleanor_api_version__`` dunder used for bare-callable registries.
    """
    return spec.plugin_api_version


#: Canonical names of the kernels shipped inside the eleanor distribution.
#: The names are hard-coded here so the registry can protect them from
#: override before entry-point discovery has run.
BUILTIN_KERNELS: frozenset[str] = frozenset({"eq36"})

#: The shared :class:`PluginRegistry` instance backing this module's helpers.
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
