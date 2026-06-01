from eleanor.plugin import PluginRegistry, PluginSpec, SimplePluginSpec

registry: PluginRegistry = PluginRegistry(
    kind="cli",
    entry_point_group="eleanor.cli_commands",
    builtin_names=frozenset({"postgres"}),
    api_version=1,
    min_api_version=1,
)


def register_cli_command(name: str, spec: SimplePluginSpec) -> None:
    """Register ``spec`` under ``name`` in the CLI command registry."""
    registry.register(name, spec)


def available_cli_commands() -> frozenset[str]:
    """Return the set of currently-registered CLI plugin names."""
    return registry.available()


def get_factory(name: str) -> PluginSpec:
    """Return the :class:`CliCommandSpec` registered under ``name``."""
    return registry.get(name)


__all__ = [
    "available_cli_commands",
    "get_factory",
    "register_cli_command",
]
