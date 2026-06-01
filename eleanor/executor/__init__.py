from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.registry import registry
from eleanor.executor.settings import Settings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_executor_settings(kind: str, raw: dict[str, object]) -> Settings:
    return load_plugin_settings(registry, Settings, kind, raw) or Settings()


def load_executor(kind: str, settings: Settings) -> AbstractExecutor:
    return load_plugin(registry, AbstractExecutor, kind, settings)


__all__ = [
    "AbstractExecutor",
    "AbstractFuture",
    "load_executor",
    "load_executor_settings",
]
