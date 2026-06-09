from eleanor.plugin import PluginRegistry, PluginSpec

registry: PluginRegistry = PluginRegistry(
    kind="navigator",
    builtin_names=frozenset({"random", "lattice", "random_lattice"}),
    api_version=1,
    min_api_version=1,
)


def register_navigator(name: str, factory: PluginSpec) -> None:
    registry.register(name, factory)


def available_navigators() -> frozenset[str]:
    return registry.available()


def get_factory(name: str) -> PluginSpec:
    return registry.get(name)


__all__ = [
    "available_navigators",
    "get_factory",
    "register_navigator",
]
