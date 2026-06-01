from eleanor.plugin import PluginRegistry, PluginSpec

registry: PluginRegistry = PluginRegistry(
    kind="executor",
    builtin_names=frozenset({"serial", "multiprocessing"}),
    api_version=1,
    min_api_version=1,
)


def register_executor(name: str, factory: PluginSpec) -> None:
    registry.register(name, factory)


def available_executors() -> frozenset[str]:
    return registry.available()


def get_factory(name: str) -> PluginSpec:
    return registry.get(name)


__all__ = [
    "register_executor",
    "available_executors",
    "get_factory",
]
