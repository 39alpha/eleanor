from typing import TYPE_CHECKING, Protocol

from eleanor.plugin import PluginRegistry

if TYPE_CHECKING:
    from eleanor.executor.interface import AbstractExecutor


class ExecutorFactory(Protocol):
    def __call__(self, *, num_workers: int | None = None, **kwargs: object) -> AbstractExecutor: ...


ENTRY_POINT_GROUP = "eleanor.executors"

OVERRIDE_ENV_VAR = "ELEANOR_EXECUTOR_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

BUILTIN_EXECUTORS: frozenset[str] = frozenset({"serial", "multiprocessing"})

registry: PluginRegistry[ExecutorFactory] = PluginRegistry(
    kind="executor",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_EXECUTORS,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
)


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


__all__ = [
    "BUILTIN_EXECUTORS",
    "ENTRY_POINT_GROUP",
    "ExecutorFactory",
    "MIN_SUPPORTED_API_VERSION",
    "OVERRIDE_ENV_VAR",
    "PLUGIN_API_VERSION",
    "available_executors",
    "get_factory",
    "register_executor",
]
