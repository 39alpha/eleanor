from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.registry import registry
from eleanor.executor.settings import ExecutorSettings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_executor_settings(kind: str, raw: dict[str, object]) -> ExecutorSettings:
    return load_plugin_settings(registry, ExecutorSettings, kind, raw) or ExecutorSettings()


def load_executor(kind: str, settings: ExecutorSettings) -> AbstractExecutor:
    return load_plugin(registry, AbstractExecutor, kind, settings)


__all__ = [
    "AbstractExecutor",
    "AbstractFuture",
    "load_executor",
    "load_executor_settings",
]
