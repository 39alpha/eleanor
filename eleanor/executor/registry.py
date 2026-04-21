"""
Registry and discovery for eleanor executor backends.

Built-in backends (``serial``, ``multiprocessing``) are registered at module
import time. Third-party backends advertise themselves through the
``eleanor.executors`` entry-point group in their distribution metadata, e.g.::

    [project.entry-points."eleanor.executors"]
    ray = "eleanor_ray.executor:build"
    dask = "eleanor_dask.executor:build"

Each entry point must resolve to an :data:`ExecutorFactory` — that is, a
callable with the signature ``Callable[[int | None], AbstractExecutor]``.

This module is a thin wrapper around :class:`eleanor.plugin.PluginRegistry`.
The public helpers (:func:`register_backend`, :func:`available_backends`,
:func:`get_factory`) bind to the registry's methods; the registry instance
itself is exposed as :data:`registry` for advanced introspection.
"""
import warnings
from collections.abc import Callable
from typing import TypeAlias

from eleanor.plugin import PluginRegistry

from .interface import AbstractExecutor

ExecutorFactory: TypeAlias = Callable[[int | None], AbstractExecutor]

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = 'eleanor.executors'

#: Environment variable users can set to allow third-party plugins to override
#: built-ins or already-registered plugins.
OVERRIDE_ENV_VAR = 'ELEANOR_EXECUTOR_OVERRIDES'


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


#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[ExecutorFactory] = PluginRegistry(
    kind='executor backend',
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={
        'serial': _build_serial,
        'multiprocessing': _build_multiprocessing,
    },
)

#: Canonical names of the backends shipped inside the eleanor distribution.
BUILTIN_BACKENDS: frozenset[str] = registry.builtins


def register_backend(name: str, factory: ExecutorFactory) -> None:
    """Register ``factory`` under ``name`` in the backend registry.

    See :meth:`PluginRegistry.register` for collision semantics.
    """
    registry.register(name, factory)


def available_backends() -> frozenset[str]:
    """Return the set of currently-registered backend names.

    The first call triggers entry-point discovery; subsequent calls return
    the cached registry contents.
    """
    return registry.available()


def get_factory(name: str) -> ExecutorFactory:
    """Return the :data:`ExecutorFactory` registered under ``name``.

    Raises :class:`~eleanor.exceptions.EleanorException` with a helpful
    ``choose from`` list if ``name`` is unknown.
    """
    return registry.get(name)
