from typing import TYPE_CHECKING, Protocol

from eleanor.plugin import PluginRegistry

ENTRY_POINT_GROUP = "eleanor.navigators"

OVERRIDE_ENV_VAR = "ELEANOR_NAVIGATOR_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

if TYPE_CHECKING:
    from eleanor.navigator.interface import AbstractNavigator


class NavigatorFactory(Protocol):
    def __call__(self, **kwargs: object) -> AbstractNavigator: ...


BUILTIN_NAVIGATORS: frozenset[str] = frozenset({"random", "random_lattice", "lattice"})

registry: PluginRegistry[NavigatorFactory] = PluginRegistry(
    kind="navigator",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_NAVIGATORS,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
)


def register_navigator(name: str, factory: NavigatorFactory) -> None:
    """Register ``factory`` under ``name`` in the navigator registry."""
    registry.register(name, factory)


def available_navigators() -> frozenset[str]:
    """Return the set of currently-registered navigator names."""
    return registry.available()


def get_factory(name: str) -> NavigatorFactory:
    """Return the :data:`NavigatorFactory` registered under ``name``."""
    return registry.get(name)


__all__ = [
    "ENTRY_POINT_GROUP",
    "OVERRIDE_ENV_VAR",
    "PLUGIN_API_VERSION",
    "MIN_SUPPORTED_API_VERSION",
    "BUILTIN_NAVIGATORS",
    "NavigatorFactory",
    "register_navigator",
    "available_navigators",
    "get_factory",
]
