from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import click

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

ENTRY_POINT_GROUP = "eleanor.cli_commands"

OVERRIDE_ENV_VAR = "ELEANOR_CLI_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

BUILTIN_CLI_COMMANDS: frozenset[str] = frozenset({"postgres"})


@dataclass(frozen=True)
class CliCommandSpec(object):
    """Descriptor each CLI plugin registers.

    :param commands: commands attached beneath the auto-generated parent
        group. Items may be :class:`click.Group` for arbitrary nesting.
    :param help: optional help text for the auto-generated parent group.
    :param plugin_api_version: CLI plugin API version this spec targets.
    """

    commands: tuple[click.Command, ...]
    help: str | None = None
    plugin_api_version: int = 1


type CliCommandFactory = CliCommandSpec | Callable[[], CliCommandSpec]


def _coerce_to_spec(name: str, factory: object) -> CliCommandSpec:
    """Accept a :class:`CliCommandSpec` directly or a zero-arg callable returning one.

    Also validates that :attr:`CliCommandSpec.plugin_api_version` is a real
    ``int`` (rejecting ``bool``, which is a subtype of ``int`` in Python and
    would otherwise silently flow into the version comparison) and that
    :attr:`CliCommandSpec.commands` is a tuple of :class:`click.Command`
    instances.  The extra ``commands`` check is an intentional divergence from
    the other spec-style registries: a malformed ``commands`` field would
    produce confusing Click-internal errors at dispatch time, so catching it
    at registration gives a much more useful message.
    """
    if isinstance(factory, CliCommandSpec):
        spec = factory
    elif callable(factory):
        try:
            produced = factory()
        except TypeError as e:
            msg = f"cli plugin {name!r} factory is not a zero-argument callable"
            raise EleanorException(msg) from e
        if not isinstance(produced, CliCommandSpec):
            msg = f"cli plugin {name!r} factory must return a CliCommandSpec, got {type(produced).__name__}"
            raise EleanorException(msg)
        spec = produced
    else:
        msg = f"cli plugin {name!r} must be a CliCommandSpec or a zero-arg callable returning one (got {type(factory).__name__})"
        raise EleanorException(msg)

    declared = cast(object, spec.plugin_api_version)
    if isinstance(declared, bool) or not isinstance(declared, int):
        msg = f"cli plugin {name!r} CliCommandSpec.plugin_api_version must be int, got {type(declared).__name__}"
        raise EleanorException(msg)

    if not isinstance(cast(object, spec.commands), tuple):
        msg = f"cli plugin {name!r} CliCommandSpec.commands must be a tuple of click.Command instances"
        raise EleanorException(msg)

    if not all(isinstance(c, click.Command) for c in cast(tuple[object, ...], spec.commands)):
        msg = f"cli plugin {name!r} CliCommandSpec.commands must be a tuple of click.Command instances"
        raise EleanorException(msg)

    return spec


def _spec_api_version(spec: CliCommandSpec) -> int | None:
    """Resolver hook used by :class:`PluginRegistry` for the CLI registry.

    Reads :attr:`CliCommandSpec.plugin_api_version` directly rather than the
    ``__eleanor_api_version__`` dunder used for bare-callable registries.
    """
    return spec.plugin_api_version


registry: PluginRegistry[CliCommandSpec] = PluginRegistry(
    kind="cli",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_CLI_COMMANDS,
    validator=_coerce_to_spec,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
    api_version_resolver=_spec_api_version,
)


def register_cli_command(name: str, spec: CliCommandFactory) -> None:
    """Register ``spec`` under ``name`` in the CLI command registry."""
    registry.register(name, spec)


def available_cli_commands() -> frozenset[str]:
    """Return the set of currently-registered CLI plugin names."""
    return registry.available()


def get_factory(name: str) -> CliCommandSpec:
    """Return the :class:`CliCommandSpec` registered under ``name``."""
    return registry.get(name)


__all__ = [
    "BUILTIN_CLI_COMMANDS",
    "CliCommandFactory",
    "CliCommandSpec",
    "ENTRY_POINT_GROUP",
    "MIN_SUPPORTED_API_VERSION",
    "OVERRIDE_ENV_VAR",
    "PLUGIN_API_VERSION",
    "available_cli_commands",
    "get_factory",
    "register_cli_command",
]
