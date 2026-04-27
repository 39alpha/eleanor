"""
Registry and discovery for eleanor executors.

Built-in executors (``serial``, ``multiprocessing``) are pre-announced here
and registered from :mod:`eleanor.executor` at package import time.
Third-party executors advertise themselves through the
``eleanor.executors`` entry-point group in their distribution metadata, e.g.::

    [project.entry-points."eleanor.executors"]
    ray = "eleanor_ray.executor:build"
    dask = "eleanor_dask.executor:build"

Each entry point must resolve to an :data:`ExecutorFactory` — that is, a
callable with the signature ``Callable[[int | None], AbstractExecutor]``.

This module is a thin wrapper around :class:`eleanor.plugin.PluginRegistry`.
The public helpers (:func:`register_executor`, :func:`available_executors`,
:func:`get_factory`) bind to the registry's methods; the registry instance
itself is exposed as :data:`registry` for advanced introspection.

Executor plugins declare API compatibility via a module- or function-level
``__eleanor_api_version__`` attribute. Registration checks this against this
module's ``PLUGIN_API_VERSION``/``MIN_SUPPORTED_API_VERSION`` policy; see
``AGENTS.md`` for details.
"""

from collections.abc import Callable
from typing import TypeAlias

from eleanor.plugin import PluginRegistry

from .interface import AbstractExecutor

ExecutorFactory: TypeAlias = Callable[[int | None], AbstractExecutor]

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = "eleanor.executors"

#: Environment variable users can set to allow third-party plugins to override
#: built-ins or already-registered plugins.
OVERRIDE_ENV_VAR = "ELEANOR_EXECUTOR_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1


#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[ExecutorFactory] = PluginRegistry(
    kind="executor",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=frozenset({"serial", "multiprocessing"}),
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
)

#: Canonical names of the executors shipped inside the eleanor distribution.
BUILTIN_EXECUTORS: frozenset[str] = registry.builtins


def register_executor(name: str, factory: ExecutorFactory) -> None:
    """Register ``factory`` under ``name`` in the executor registry.

    See :meth:`PluginRegistry.register` for collision semantics.
    """
    registry.register(name, factory)


def available_executors() -> frozenset[str]:
    """Return the set of currently-registered executor names.

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
