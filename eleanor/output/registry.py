"""
Registry and discovery for eleanor output sink plugins.

Built-in sinks (currently ``postgres``) are registered at module import time.
Third-party sinks advertise themselves through the ``eleanor.outputs``
entry-point group.

Each registered factory is a callable invoked as
``factory(config, verbose=<bool>, **args)``, where ``config`` is the loaded
:class:`~eleanor.config.Config` object and ``args`` comes from the optional
``output.args`` block in the configuration file. ``OutputFactory`` is typed
as ``Callable[..., object]`` so this module has no structural dependency on
:mod:`eleanor.output.interface` or :mod:`eleanor.config` — keeping the
dependency graph acyclic for static analysis. Callers validate the returned
sink against :class:`~eleanor.output.OutputSink` at use sites.
"""
import warnings
from collections.abc import Callable
from importlib import import_module
from typing import cast

from eleanor.exceptions import EleanorException
from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = 'eleanor.outputs'

#: Environment variable that allows plugin registrations to override built-ins
#: or previously-registered plugins.
OVERRIDE_ENV_VAR = 'ELEANOR_OUTPUT_OVERRIDES'

#: Factory callable shape for output sink builders.
OutputFactory = Callable[..., object]


def _build_postgres(config: object, *, verbose: bool = False, **args: object) -> object:
    database = getattr(config, 'database', None)
    if database is None:
        raise EleanorException('postgres output sink requires config.database')

    if args:
        warnings.warn(
            'built-in output sink "postgres" does not accept keyword arguments; '
            + f'ignoring: {list(args)}',
            RuntimeWarning,
            stacklevel=2,
        )
    # Resolved through :func:`importlib.import_module` so the static import
    # graph stays acyclic: a direct ``from .postgres import PostgresSink``
    # here would chain to ``eleanor.config`` (via ``eleanor.output.postgres``
    # -> ``eleanor.yeoman`` -> ``eleanor.config``), and ``eleanor.config``
    # already depends on this module for sink-name validation.
    postgres_module = import_module('eleanor.output.postgres')
    postgres_sink_cls = cast(Callable[..., object], getattr(postgres_module, 'PostgresSink'))
    return postgres_sink_cls(database, verbose=verbose)


#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[OutputFactory] = PluginRegistry(
    kind='output sink',
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={
        'postgres': _build_postgres,
    },
)

#: Canonical names of the sink backends shipped inside the eleanor
#: distribution.
BUILTIN_OUTPUT_SINKS: frozenset[str] = registry.builtins


def register_output_sink(name: str, factory: OutputFactory) -> None:
    """Register ``factory`` under ``name`` in the output sink registry."""
    registry.register(name, factory)


def available_output_sinks() -> frozenset[str]:
    """Return the set of currently-registered output sink names."""
    return registry.available()


def get_factory(name: str) -> OutputFactory:
    """Return the :data:`OutputFactory` registered under ``name``."""
    return registry.get(name)
