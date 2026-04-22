"""
Generic plugin registry shared by all of eleanor's extension points.

Each extension point (executor, kernel, navigator, output, transformer)
instantiates a :class:`PluginRegistry` seeded with the built-in factories it
ships with, and consumers go through the registry instead of importing
implementations directly. Third-party plugins advertise themselves through a
per-extension ``eleanor.<kinds>`` entry-point group; see
:mod:`eleanor.executor.registry`, :mod:`eleanor.kernel.registry`,
:mod:`eleanor.navigator.registry`, :mod:`eleanor.output.registry`, and
:mod:`eleanor.transformer.registry` for the concrete wiring.

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
"""
import os
import warnings
from collections.abc import Callable, Mapping
from importlib.metadata import entry_points
from typing import Generic, TypeVar, cast, final

from eleanor.exceptions import EleanorException

#: Generic parameter for the per-extension factory callable (or spec object).
F = TypeVar('F')


@final
class PluginRegistry(Generic[F]):
    """Registry of named plugin factories for a single extension point.

    :param kind: short human-readable name of the extension point (``executor``,
        ``kernel``, etc.) used in error and warning messages.
    :param entry_point_group: the entry-point group discovered lazily on first
        access, e.g. ``eleanor.executors``.
    :param override_env_var: environment variable that, when set to a truthy
        value, allows plugin registrations to override built-ins and each
        other. Intended for development/debugging only.
    :param builtins: mapping of built-in name to factory. The keys are recorded
        as :attr:`BUILTINS` and are protected against override by default.
    :param validator: optional callable invoked as ``validator(name, factory)``
        at registration time. It may raise :class:`EleanorException` to reject
        the registration, or coerce a factory in-place. Built-in factories are
        validated once at construction.
    """

    _kind: str
    _entry_point_group: str
    _override_env_var: str
    _validator: Callable[[str, object], F] | None
    _registry: dict[str, F]
    _builtins: frozenset[str]
    _discovered: bool

    def __init__(
        self,
        *,
        kind: str,
        entry_point_group: str,
        override_env_var: str,
        builtins: Mapping[str, F],
        builtin_names: frozenset[str] | None = None,
        validator: Callable[[str, object], F] | None = None,
    ) -> None:
        self._kind = kind
        self._entry_point_group = entry_point_group
        self._override_env_var = override_env_var
        self._validator = validator
        self._registry = {}
        self._builtins = (
            builtin_names if builtin_names is not None else frozenset(builtins.keys())
        )
        self._discovered = False

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

        Raises :class:`EleanorException` with a helpful ``choose from`` list
        if the name is unknown.
        """
        self._discover_entry_points()
        try:
            return self._registry[name]
        except KeyError as e:
            choices = ', '.join(sorted(self._registry))
            raise EleanorException(
                f'unsupported {self._kind} "{name}"; choose from {choices}',
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
            raise EleanorException(f'{self._kind} plugin name must be a non-empty string')

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
                        + f'set {self._override_env_var}=1 to override',
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    return
            elif not overrides:
                warnings.warn(
                    f'{self._kind} "{name}" is already registered; '
                    + f'set {self._override_env_var}=1 to override',
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
            return cast(F, factory)
        return self._validator(name, factory)

    def _overrides_allowed(self) -> bool:
        value = os.environ.get(self._override_env_var, '').strip().lower()
        return value not in ('', '0', 'false', 'no', 'off')

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
                    f'failed to load {self._kind} entry point "{ep.name}" '
                    + f'from "{ep.value}": {e}',
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            try:
                self.register(ep.name, loaded)
            except EleanorException as e:
                warnings.warn(
                    f'{self._kind} entry point "{ep.name}" from "{ep.value}" '
                    + f'is invalid: {e}',
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
