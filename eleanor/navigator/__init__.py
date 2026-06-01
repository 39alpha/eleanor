from eleanor.navigator.interface import AbstractNavigator
from eleanor.navigator.registry import registry
from eleanor.navigator.settings import Settings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_navigator_settings(kind: str, raw: dict[str, object]) -> Settings:
    return load_plugin_settings(registry, Settings, kind, raw) or Settings()


def load_navigator(kind: str, settings: Settings | None = None) -> AbstractNavigator:
    return load_plugin(registry, AbstractNavigator, kind, settings)


__all__ = [
    "AbstractNavigator",
    "load_navigator",
    "load_navigator_settings",
]
