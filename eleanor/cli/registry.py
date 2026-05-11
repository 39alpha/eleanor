"""
Registry and discovery for eleanor CLI subcommand plugins.

Each CLI plugin contributes a :class:`CliCommandSpec` whose ``commands``
tuple is attached beneath an auto-generated ``click.Group`` named after
the plugin's registration name. So a plugin registered under ``"foo"``
that ships a ``bar`` command is invoked as ``eleanor foo bar``. Plugins
may nest further by passing :class:`click.Group` instances as members of
``commands``.

Built-in CLI specs (currently just ``postgres``) are declared as entry
points in ``pyproject.toml`` and discovered lazily on first registry
access, matching the pattern used by the other plugin registries.
Third-party plugins advertise themselves through the ``eleanor.cli_commands``
entry-point group in their distribution metadata, e.g.::

    [project.entry-points."eleanor.cli_commands"]
    my_plugin = "my_plugin.cli:cli_spec"

An entry point may resolve to either a :class:`CliCommandSpec` instance
or a zero-argument callable returning one (the second form lets plugin
authors defer expensive imports until their commands are actually
requested).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias, cast

import click

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

ENTRY_POINT_GROUP = "eleanor.cli_commands"
OVERRIDE_ENV_VAR = "ELEANOR_CLI_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1


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


CliCommandFactory: TypeAlias = CliCommandSpec | Callable[[], CliCommandSpec]


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
            raise EleanorException(
                f'cli plugin "{name}" factory is not a zero-argument callable',
            ) from e
        if not isinstance(produced, CliCommandSpec):
            raise EleanorException(
                f'cli plugin "{name}" factory must return a CliCommandSpec, ' + f"got {type(produced).__name__}",
            )
        spec = produced
    else:
        raise EleanorException(
            f'cli plugin "{name}" must be a CliCommandSpec or a zero-arg callable '
            + f"returning one (got {type(factory).__name__})",
        )

    declared = cast(object, spec.plugin_api_version)
    if isinstance(declared, bool) or not isinstance(declared, int):
        raise EleanorException(
            f'cli plugin "{name}" CliCommandSpec.plugin_api_version must be int, ' + f"got {type(declared).__name__}",
        )

    # Validate command shapes early so a malformed spec produces a useful
    # registration-time error rather than a confusing Click failure later.
    commands = cast(object, spec.commands)
    if not isinstance(commands, tuple):
        raise EleanorException(
            f'cli plugin "{name}" CliCommandSpec.commands must be a tuple of click.Command instances',
        )
    if not all(isinstance(c, click.Command) for c in cast(tuple[object, ...], commands)):
        raise EleanorException(
            f'cli plugin "{name}" CliCommandSpec.commands must be a tuple of click.Command instances',
        )
    return spec


def _spec_api_version(spec: CliCommandSpec) -> int | None:
    """Resolver hook used by :class:`PluginRegistry` for the CLI registry.

    Reads :attr:`CliCommandSpec.plugin_api_version` directly rather than the
    ``__eleanor_api_version__`` dunder used for bare-callable registries.
    """
    return spec.plugin_api_version


#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[CliCommandSpec] = PluginRegistry(
    kind="cli",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=frozenset({"postgres"}),
    validator=_coerce_to_spec,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
    api_version_resolver=_spec_api_version,
)

#: Canonical names of the CLI commands shipped inside the eleanor distribution.
BUILTIN_CLI_COMMANDS: frozenset[str] = registry.builtins


def register_cli_commands(name: str, spec: CliCommandFactory) -> None:
    """Register ``spec`` under ``name`` in the CLI command registry."""
    registry.register(name, spec)


def available_cli_commands() -> frozenset[str]:
    """Return the set of currently-registered CLI plugin names."""
    return registry.available()


def get_factory(name: str) -> CliCommandSpec:
    """Return the :class:`CliCommandSpec` registered under ``name``."""
    return registry.get(name)
