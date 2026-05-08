"""
Generic plugin registry shared by all of eleanor's extension points.

Each extension point (executor, kernel, navigator, output)
instantiates a :class:`PluginRegistry` seeded with the built-in factories it
ships with, and consumers go through the registry instead of importing
implementations directly. Third-party plugins advertise themselves through a
per-extension ``eleanor.<kinds>`` entry-point group; see
:mod:`eleanor.executor.registry`, :mod:`eleanor.kernel.registry`,
:mod:`eleanor.navigator.registry`, and :mod:`eleanor.output.registry` for the
concrete wiring.

The registry is generic over the factory shape of each extension point. The
shared behaviour is:

* Lazy, at-most-once entry-point discovery on first :meth:`get` or
  :meth:`available`.
* Built-in names always win on collision.
* Plugin-vs-plugin collisions emit :class:`RuntimeWarning` and keep the first
  registration, unless an override environment variable is set.
* Failed entry-point loads emit :class:`RuntimeWarning` and do not abort
  discovery of the remaining entries.
* An optional ``validator`` callback can reject ill-shaped factories at
  registration time.
* Each registration is checked against a per-registry ``api_version`` /
  ``min_api_version`` pair. Plugins targeting an unsupported version are
  rejected (or downgraded to a :class:`OverrideWarning` when the override
  env var is set).
"""

import os
import sys
import warnings
from collections.abc import Callable, Mapping
from importlib.metadata import entry_points
from typing import Generic, TypeVar, cast, final

from eleanor.exceptions import EleanorException

#: Generic parameter for the per-extension factory callable (or spec object).
F = TypeVar("F")

#: Module-level dunder a plugin's factory (or its module) may set to declare
#: the API version it targets.
_API_VERSION_DUNDER = "__eleanor_api_version__"

#: Public registry of ``kind -> (current_api_version, min_supported_api_version)``.
#: Populated as each :class:`PluginRegistry` is constructed; intended for
#: diagnostic tooling (e.g. ``eleanor diagnose``) and tests. Read-only by
#: convention; mutating it from outside :mod:`eleanor.plugin` is unsupported.
PLUGIN_API_VERSIONS: dict[str, tuple[int, int]] = {}


class OverrideWarning(RuntimeWarning):
    """:class:`RuntimeWarning` subclass for plugin-version override notifications.

    When ``ELEANOR_<KIND>_OVERRIDES`` is truthy, a hard API-version mismatch
    is downgraded to a warning rather than raising. Using a dedicated subclass
    makes those warnings harder to mute by accident with a blanket
    ``filterwarnings('ignore', RuntimeWarning)`` and easier to grep for in CI
    logs.
    """


def resolve_api_version(factory: object) -> int | None:
    """Return the API version declared by ``factory``, or ``None``.

    Looks for :data:`_API_VERSION_DUNDER` first on ``factory`` and then on the
    module that defines ``factory``. ``bool`` values and non-``int`` payloads
    are rejected (the function returns ``None`` for them); ``True``/``False``
    are a common mistake and almost never the intended declaration.
    """
    declared = getattr(factory, _API_VERSION_DUNDER, None)
    if declared is None:
        module_name = getattr(factory, "__module__", None)
        if isinstance(module_name, str):
            module = sys.modules.get(module_name)
            if module is not None:
                declared = getattr(module, _API_VERSION_DUNDER, None)
    if isinstance(declared, bool) or not isinstance(declared, int):
        return None
    return declared


def is_abstract_instantiation_error(exc: TypeError) -> bool:
    """Return ``True`` when ``exc`` is Python's abstract-class instantiation error.

    ``ABCMeta.__call__`` raises :class:`TypeError` with a message starting with
    ``"Can't instantiate abstract class"`` when a subclass fails to override
    one of its bases' ``@abstractmethod`` declarations. Use-site wrappers
    reach for this to distinguish between "plugin built against a stale API
    contract" — worth re-raising as :class:`EleanorException` with the plugin
    name — and any other :class:`TypeError`, which should propagate unchanged
    so the original traceback survives.
    """
    return "Can't instantiate abstract class" in str(exc)


def _overrides_allowed(override_env_var: str) -> bool:
    value = os.environ.get(override_env_var, "").strip().lower()
    return value not in ("", "0", "false", "no", "off")


def check_api_version(
    *,
    kind: str,
    name: str,
    declared: int | None,
    current: int,
    floor: int,
    override_env_var: str,
    warned: set[str] | None = None,
) -> int:
    """Validate a plugin's declared API version against the core's contract.

    :param warned: optional bookkeeping set used to de-duplicate the
        "did not declare an API version" warning. Each :class:`PluginRegistry`
        owns one such set; tests typically pass a fresh ``set()`` to keep
        cases independent.
    :returns: the effective declared version (``floor`` for unversioned
        plugins, ``declared`` otherwise).
    :raises EleanorException: when ``declared`` is outside the supported
        range and the override env var is unset.
    """
    if declared is None:
        if warned is None or name not in warned:
            if warned is not None:
                warned.add(name)
            warnings.warn(
                f'plugin "{name}" did not declare an API version; '
                + f"assuming {kind} v{floor}. Set "
                + f"``{_API_VERSION_DUNDER} = <int>`` on the factory or its "
                + "module to silence this warning.",
                RuntimeWarning,
                stacklevel=2,
            )
        return floor
    if declared > current:
        msg = f'plugin "{name}" targets {kind} API v{declared}; this eleanor supports up to v{current}'
    elif declared < floor:
        msg = f'plugin "{name}" targets {kind} API v{declared}; this eleanor requires v{floor}+'
    else:
        return declared
    if _overrides_allowed(override_env_var):
        warnings.warn(
            msg + f"; loading anyway because {override_env_var} is set",
            OverrideWarning,
            stacklevel=2,
        )
        return declared
    raise EleanorException(msg)


@final
class PluginRegistry(Generic[F]):
    """Registry of named plugin factories for a single extension point.

    :param kind: short human-readable name of the extension point (``executor``,
        ``kernel``, etc.) used in error and warning messages.
    :param entry_point_group: the entry-point group discovered lazily on first
        access, e.g. ``eleanor.executors``.
    :param override_env_var: environment variable that, when set to a truthy
        value, allows plugin registrations to override built-ins and each
        other, and downgrades API-version rejections to
        :class:`OverrideWarning`. Intended for development/debugging only.
    :param builtins: mapping of built-in name to factory. The keys are recorded
        as :attr:`builtins` and are protected against override by default.
    :param validator: optional callable invoked as ``validator(name, factory)``
        at registration time, before the API-version check. It may raise
        :class:`EleanorException` to reject the registration outright, or
        coerce a factory in-place (for example, the kernel registry uses this
        to unwrap ``Callable[[], KernelSpec]`` factories into their
        :class:`KernelSpec`).
    :param api_version: the most recent contract version this eleanor knows
        how to drive. Plugins targeting a higher version are rejected.
    :param min_api_version: the oldest contract version still supported.
        Plugins targeting a lower version are rejected.
    :param api_version_resolver: how to extract the declared API version from
        a coerced factory. Defaults to :func:`resolve_api_version`, which
        reads :data:`_API_VERSION_DUNDER` from the factory or its module.
        Spec-style registries (e.g. kernel) override this to read a field on
        the spec instead.

    Plugin shape itself (e.g. accepted argument signature) is intentionally
    *not* validated at registration time: third-party factories include
    :class:`unittest.mock.Mock`, partial-applied wrappers, and C-implemented
    callables whose signatures are not introspectable. Instead, shape errors
    surface at use sites as :class:`TypeError`, which the helpers in
    :mod:`eleanor.eleanor` and :mod:`eleanor.executor` convert into
    informative :class:`EleanorException` messages via
    :func:`is_abstract_instantiation_error`.
    """

    _kind: str
    _entry_point_group: str
    _override_env_var: str
    _validator: Callable[[str, object], F] | None
    _api_version_resolver: Callable[[F], int | None]
    _registry: dict[str, F]
    _builtins: frozenset[str]
    _discovered: bool
    _current_api_version: int
    _min_api_version: int
    _unversioned_warned: set[str]

    def __init__(
        self,
        *,
        kind: str,
        entry_point_group: str,
        override_env_var: str,
        builtins: Mapping[str, F],
        builtin_names: frozenset[str] | None = None,
        validator: Callable[[str, object], F] | None = None,
        api_version: int = 1,
        min_api_version: int = 1,
        api_version_resolver: Callable[[F], int | None] | None = None,
    ) -> None:
        if min_api_version > api_version:
            raise EleanorException(
                f"{kind}: min_api_version v{min_api_version} cannot exceed api_version v{api_version}",
            )
        self._kind = kind
        self._entry_point_group = entry_point_group
        self._override_env_var = override_env_var
        self._validator = validator
        self._registry = {}
        self._builtins = builtin_names if builtin_names is not None else frozenset(builtins.keys())
        self._discovered = False
        self._current_api_version = api_version
        self._min_api_version = min_api_version
        # ``resolve_api_version`` is typed against ``object``; the registry
        # narrows ``F`` from there, so an explicit cast keeps the assignment
        # honest about callable contravariance.
        self._api_version_resolver = (
            api_version_resolver
            if api_version_resolver is not None
            else cast(Callable[[F], int | None], resolve_api_version)
        )
        self._unversioned_warned = set()

        PLUGIN_API_VERSIONS[kind] = (api_version, min_api_version)

        for name, factory in builtins.items():
            coerced = self._validate(name, factory)
            self._registry[name] = coerced

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def entry_point_group(self) -> str:
        return self._entry_point_group

    @property
    def override_env_var(self) -> str:
        return self._override_env_var

    @property
    def builtins(self) -> frozenset[str]:
        """Names that were seeded from :paramref:`PluginRegistry.builtins`."""
        return self._builtins

    @property
    def current_api_version(self) -> int:
        """The most recent API contract version this registry can drive."""
        return self._current_api_version

    @property
    def min_api_version(self) -> int:
        """The oldest API contract version this registry still accepts."""
        return self._min_api_version

    def is_builtin(self, name: str) -> bool:
        return name in self._builtins

    def available(self) -> frozenset[str]:
        """Return the set of currently-registered plugin names.

        The first call triggers entry-point discovery; subsequent calls return
        the cached registry contents.
        """
        self._discover_entry_points()
        return frozenset(self._registry)

    def get(self, name: str) -> F:
        """Return the factory registered under ``name``.

        Raises :class:`EleanorException` with a helpful ``choose one of`` list
        if the name is unknown.
        """
        self._discover_entry_points()
        try:
            return self._registry[name]
        except KeyError as e:
            choices = ", ".join(sorted(self._registry))
            raise EleanorException(
                f'the "{name}" {self._kind} is not supported; choose one of {choices}',
            ) from e

    def __contains__(self, name: object) -> bool:
        self._discover_entry_points()
        return name in self._registry

    def register(self, name: str, factory: object) -> None:
        """Register ``factory`` under ``name``.

        Calling this with the same ``(name, factory)`` pair more than once is
        a no-op. If ``name`` is already registered to a different factory, a
        :class:`RuntimeWarning` is emitted and the existing registration is
        preserved — unless the override environment variable is set to a
        truthy value.

        The ``factory`` parameter is typed ``object`` because callers include
        entry-point loaders whose return values start life untyped; the
        optional ``validator`` narrows it to :data:`F`.
        """
        # ``isinstance(name, str)`` is intentionally omitted: basedpyright
        # flags it as ``reportUnnecessaryIsInstance`` because ``name`` is
        # already typed ``str``.  The falsy check below still rejects the
        # empty-string case, which is the only runtime risk.
        if not name:
            raise EleanorException(f"{self._kind} plugin name must be a non-empty string")

        coerced = self._validate(name, factory)

        existing = self._registry.get(name)
        if existing is coerced or existing is factory:
            return
        if existing is not None:
            overrides = self._overrides_allowed()
            if name in self._builtins:
                if not overrides:
                    warnings.warn(
                        f'refusing to override built-in {self._kind} "{name}"; '
                        + f"set {self._override_env_var}=1 to override",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    return
            elif not overrides:
                warnings.warn(
                    f'{self._kind} "{name}" is already registered; ' + f"set {self._override_env_var}=1 to override",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return
        self._registry[name] = coerced

    def _validate(self, name: str, factory: object) -> F:
        if self._validator is None:
            if not callable(factory):
                raise EleanorException(
                    f'{self._kind} factory for "{name}" must be callable',
                )
            coerced: F = cast(F, factory)
        else:
            coerced = self._validator(name, factory)

        declared = self._api_version_resolver(coerced)
        _ = check_api_version(
            kind=self._kind,
            name=name,
            declared=declared,
            current=self._current_api_version,
            floor=self._min_api_version,
            override_env_var=self._override_env_var,
            warned=self._unversioned_warned,
        )
        return coerced

    def _overrides_allowed(self) -> bool:
        return _overrides_allowed(self._override_env_var)

    def _discover_entry_points(self) -> None:
        if self._discovered:
            return
        self._discovered = True

        try:
            eps = entry_points(group=self._entry_point_group)
        except Exception as e:  # pragma: no cover - defensive
            warnings.warn(
                f'failed to query entry points for group "{self._entry_point_group}": {e}',
                RuntimeWarning,
                stacklevel=2,
            )
            return

        for ep in eps:
            loaded: object
            try:
                loaded = cast(object, ep.load())
            except Exception as e:
                warnings.warn(
                    f'failed to load {self._kind} entry point "{ep.name}" ' + f'from "{ep.value}": {e}',
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            try:
                self.register(ep.name, loaded)
            except EleanorException as e:
                warnings.warn(
                    f'{self._kind} entry point "{ep.name}" from "{ep.value}" ' + f"is invalid: {e}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
