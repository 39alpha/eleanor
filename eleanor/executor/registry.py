"""
Registry and discovery for eleanor executor backends.

Built-in backends (``serial``, ``multiprocessing``) are registered at module
import time. Third-party backends advertise themselves through the
``eleanor.executors`` entry-point group in their distribution metadata, e.g.::

    [project.entry-points."eleanor.executors"]
    mpi = "eleanor_mpi.executor:build"
    dask = "eleanor_dask.executor:build"

Each entry point must resolve to an :data:`ExecutorFactory` — that is, a
callable with the signature ``Callable[[int | None], AbstractExecutor]``.

Discovery is lazy: entry points are queried on the first call to
:func:`available_backends` or :func:`get_factory`. Failures to load a
particular plugin emit a :class:`RuntimeWarning` and skip that plugin, rather
than aborting discovery of the remaining plugins.

Collision policy: built-in names always win. A third-party name that
collides with a built-in or with another already-registered plugin triggers a
:class:`RuntimeWarning` and is ignored — unless the
``ELEANOR_EXECUTOR_OVERRIDES`` environment variable is set to a truthy value,
in which case the new registration wins (use at your own risk).
"""
import os
import warnings
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import TypeAlias

from eleanor.exceptions import EleanorException

from .interface import AbstractExecutor

ExecutorFactory: TypeAlias = Callable[[int | None], AbstractExecutor]

#: Name of the entry-point group inspected by :func:`_discover_entry_points`.
ENTRY_POINT_GROUP = 'eleanor.executors'

#: Environment variable users can set to allow third-party plugins to override
#: built-ins or already-registered plugins.
OVERRIDE_ENV_VAR = 'ELEANOR_EXECUTOR_OVERRIDES'

#: Canonical names of the backends shipped inside the eleanor distribution.
BUILTIN_BACKENDS: frozenset[str] = frozenset({'serial', 'multiprocessing'})

_BACKEND_REGISTRY: dict[str, ExecutorFactory] = {}
_DISCOVERED: bool = False


def _normalize_num_workers(num_workers: int | None) -> int | None:
    """Clamp ``num_workers`` to ``>= 1``, preserving ``None`` as the default sentinel."""
    if num_workers is None:
        return None
    if num_workers <= 0:
        return 1
    return num_workers


def _build_serial(num_workers: int | None) -> AbstractExecutor:
    from .serial import SerialExecutor

    if num_workers is not None:
        warnings.warn(
            'num_workers is ignored for serial backend',
            RuntimeWarning,
            stacklevel=3,
        )
    return SerialExecutor()


def _build_multiprocessing(num_workers: int | None) -> AbstractExecutor:
    from .multiprocessing import MultiprocessingExecutor

    return MultiprocessingExecutor(num_workers=_normalize_num_workers(num_workers))


# Seed the registry with the built-in factories.
_BACKEND_REGISTRY['serial'] = _build_serial
_BACKEND_REGISTRY['multiprocessing'] = _build_multiprocessing


def _overrides_allowed() -> bool:
    value = os.environ.get(OVERRIDE_ENV_VAR, '').strip().lower()
    return value not in ('', '0', 'false', 'no', 'off')


def register_backend(name: str, factory: ExecutorFactory) -> None:
    """Register ``factory`` under ``name`` in the backend registry.

    Calling this with the same ``(name, factory)`` pair more than once is a
    no-op. If ``name`` is already registered to a *different* factory, a
    :class:`RuntimeWarning` is emitted and the existing registration is
    preserved — unless the :data:`OVERRIDE_ENV_VAR` environment variable is
    set to a truthy value, in which case the new factory wins.
    """
    if not isinstance(name, str) or not name:
        raise EleanorException('executor backend name must be a non-empty string')
    if not callable(factory):
        raise EleanorException(
            f'executor backend factory for "{name}" must be callable',
        )

    existing = _BACKEND_REGISTRY.get(name)
    if existing is factory:
        return
    if existing is not None:
        overrides = _overrides_allowed()
        if name in BUILTIN_BACKENDS:
            if not overrides:
                warnings.warn(
                    f'refusing to override built-in executor backend "{name}"; '
                    f'set {OVERRIDE_ENV_VAR}=1 to override',
                    RuntimeWarning,
                    stacklevel=2,
                )
                return
        elif not overrides:
            warnings.warn(
                f'executor backend "{name}" is already registered; '
                f'set {OVERRIDE_ENV_VAR}=1 to override',
                RuntimeWarning,
                stacklevel=2,
            )
            return
    _BACKEND_REGISTRY[name] = factory


def _discover_entry_points() -> None:
    """Populate the registry from the :data:`ENTRY_POINT_GROUP` entry-point group.

    This function runs at most once per interpreter — subsequent calls are
    no-ops. Individual entry-point failures are reported via
    :class:`RuntimeWarning` and do not abort discovery of the remaining
    entries.
    """
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True

    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception as e:  # pragma: no cover - defensive
        warnings.warn(
            f'failed to query entry points for group "{ENTRY_POINT_GROUP}": {e}',
            RuntimeWarning,
            stacklevel=2,
        )
        return

    for ep in eps:
        try:
            factory = ep.load()
        except Exception as e:
            warnings.warn(
                f'failed to load executor entry point "{ep.name}" '
                f'from "{ep.value}": {e}',
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        if not callable(factory):
            warnings.warn(
                f'executor entry point "{ep.name}" from "{ep.value}" '
                'did not resolve to a callable; skipping',
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        register_backend(ep.name, factory)


def available_backends() -> frozenset[str]:
    """Return the set of currently-registered backend names.

    The first call triggers entry-point discovery; subsequent calls return
    the cached registry contents.
    """
    _discover_entry_points()
    return frozenset(_BACKEND_REGISTRY)


def get_factory(name: str) -> ExecutorFactory:
    """Return the :data:`ExecutorFactory` registered under ``name``.

    Raises :class:`EleanorException` if ``name`` is not a known backend,
    including any names contributed by ``eleanor.executors`` entry points.
    """
    _discover_entry_points()
    try:
        return _BACKEND_REGISTRY[name]
    except KeyError as e:
        choices = ', '.join(sorted(_BACKEND_REGISTRY))
        raise EleanorException(
            f'unsupported executor backend "{name}"; choose from {choices}',
        ) from e
