from eleanor.plugin import PluginRegistry, PluginSpec

registry: PluginRegistry = PluginRegistry(
    kind="output",
    builtin_names=frozenset({"csv", "memory", "null", "postgres"}),
    api_version=1,
    min_api_version=1,
)


def register_output_sink(name: str, factory: PluginSpec) -> None:
    """Register ``factory`` under ``name`` in the output registry."""
    registry.register(name, factory)


def available_output_sinks() -> frozenset[str]:
    """Return the set of currently-registered output names."""
    return registry.available()


def get_factory(name: str) -> PluginSpec:
    """Return the :data:`OutputFactory` registered under ``name``."""
    return registry.get(name)


__all__ = [
    "available_output_sinks",
    "get_factory",
    "register_output_sink",
]
