"""
Registry and discovery for eleanor output plugins.

Built-in sinks (currently ``postgres``) are pre-announced here and registered
from :mod:`eleanor.output` at package import time. Third-party sinks advertise
themselves through the ``eleanor.outputs`` entry-point group.

Each registered factory is a callable invoked as
``factory(config, verbose=<bool>, **args)``, where ``config`` is the loaded
:class:`~eleanor.config.Config` object and ``args`` comes from the optional
``output.args`` block in the configuration file. ``OutputFactory`` is a
``Protocol`` that pins the first positional parameter and return type while
keeping plugin-specific keyword arguments open. Callers validate the returned
sink against :class:`~eleanor.output.OutputSink` at use sites.

Output plugins declare API compatibility via a module- or function-level
``__eleanor_api_version__`` attribute. Registration checks this against this
module's ``PLUGIN_API_VERSION``/``MIN_SUPPORTED_API_VERSION`` policy; see
``AGENTS.md`` for details.
"""

from typing import TYPE_CHECKING, Protocol

from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = "eleanor.outputs"

#: Environment variable that allows plugin registrations to override built-ins
#: or previously-registered plugins.
OVERRIDE_ENV_VAR = "ELEANOR_OUTPUT_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

if TYPE_CHECKING:
    from eleanor.output.interface import OutputSink


class OutputFactory(Protocol):
    def __call__(
        self,
        config: object,
        /,
        *,
        verbose: bool = ...,
        **kwargs: object,
    ) -> "OutputSink": ...


#: Canonical names of the output sinks shipped inside the eleanor distribution.
#: Built-ins register their concrete factories from
#: :mod:`eleanor.output`'s package ``__init__``.
BUILTIN_OUTPUTS: frozenset[str] = frozenset({"csv", "memory", "null", "postgres"})

#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[OutputFactory] = PluginRegistry(
    kind="output",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_OUTPUTS,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
)


def register_output(name: str, factory: OutputFactory) -> None:
    """Register ``factory`` under ``name`` in the output registry."""
    registry.register(name, factory)


def available_outputs() -> frozenset[str]:
    """Return the set of currently-registered output names."""
    return registry.available()


def get_factory(name: str) -> OutputFactory:
    """Return the :data:`OutputFactory` registered under ``name``."""
    return registry.get(name)
