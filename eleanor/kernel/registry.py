from eleanor.plugin import PluginRegistry, PluginSpec

registry: PluginRegistry = PluginRegistry(
    kind="kernel",
    builtin_names=frozenset({"eq36"}),
    api_version=1,
    min_api_version=1,
)


def register_kernel(name: str, spec: PluginSpec) -> None:
    registry.register(name, spec)


def available_kernels() -> frozenset[str]:
    return registry.available()


def get_factory(name: str) -> PluginSpec:
    return registry.get(name)


__all__ = [
    "available_kernels",
    "get_factory",
    "register_kernel",
]
