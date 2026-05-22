from typing import TYPE_CHECKING, Protocol

from eleanor.plugin import PluginRegistry

ENTRY_POINT_GROUP = "eleanor.outputs"

OVERRIDE_ENV_VAR = "ELEANOR_OUTPUT_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

if TYPE_CHECKING:
    from eleanor.output.interface import OutputSink


class OutputFactory(Protocol):
    def __call__(self, *, verbose: bool = ..., **kwargs: object) -> OutputSink: ...


BUILTIN_OUTPUTS: frozenset[str] = frozenset({"csv", "memory", "null", "postgres"})

registry: PluginRegistry[OutputFactory] = PluginRegistry(
    kind="output",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_OUTPUTS,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
)


def register_output_sink(name: str, factory: OutputFactory) -> None:
    """Register ``factory`` under ``name`` in the output registry."""
    registry.register(name, factory)


def available_output_sinks() -> frozenset[str]:
    """Return the set of currently-registered output names."""
    return registry.available()


def get_factory(name: str) -> OutputFactory:
    """Return the :data:`OutputFactory` registered under ``name``."""
    return registry.get(name)


__all__ = [
    "BUILTIN_OUTPUTS",
    "ENTRY_POINT_GROUP",
    "MIN_SUPPORTED_API_VERSION",
    "OVERRIDE_ENV_VAR",
    "OutputFactory",
    "PLUGIN_API_VERSION",
    "available_output_sinks",
    "get_factory",
    "register_output_sink",
]
