"""
Registry and discovery for eleanor navigator plugins.

Built-in navigators (``random``, ``random_lattice``, ``lattice``) register
themselves from :mod:`eleanor.navigator` at package import time. Third-party
navigators advertise themselves through the ``eleanor.navigators``
entry-point group.

Each registered factory is a callable invoked as
``factory(order, kernel, **args)`` where ``args`` is the optional ``args``
block from the order file's ``navigator`` section. Factories are typed as
``Callable[..., object]`` so this module has no structural dependency on
:mod:`eleanor.navigator` itself; callers validate the returned navigator
against :class:`~eleanor.navigator.AbstractNavigator` (or the
:class:`~eleanor.order.NavigatorProtocol` structural alternative) before use.

Navigator plugins declare API compatibility via a module- or function-level
``__eleanor_api_version__`` attribute. Registration checks this against this
module's ``PLUGIN_API_VERSION``/``MIN_SUPPORTED_API_VERSION`` policy; see
``AGENTS.md`` for details.
"""

from collections.abc import Callable
from typing import TypeAlias

from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = "eleanor.navigators"

#: Environment variable that allows plugin registrations to override built-ins
#: or previously-registered plugins.
OVERRIDE_ENV_VAR = "ELEANOR_NAVIGATOR_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

#: Factory callable shape. Each registered navigator is invoked with the
#: current order, kernel, and keyword args from the order file.
NavigatorFactory: TypeAlias = Callable[..., object]

#: Canonical names of the navigators shipped inside the eleanor distribution.
#: Built-ins register their concrete factories from
#: :mod:`eleanor.navigator`'s package ``__init__``.
BUILTIN_NAVIGATORS: frozenset[str] = frozenset({"random", "random_lattice", "lattice"})

#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[NavigatorFactory] = PluginRegistry(
    kind="navigator",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_NAVIGATORS,
    api_version=PLUGIN_API_VERSION,
    min_api_version=MIN_SUPPORTED_API_VERSION,
)


def register_navigator(name: str, factory: NavigatorFactory) -> None:
    """Register ``factory`` under ``name`` in the navigator registry."""
    registry.register(name, factory)


def available_navigators() -> frozenset[str]:
    """Return the set of currently-registered navigator names."""
    return registry.available()


def get_factory(name: str) -> NavigatorFactory:
    """Return the :data:`NavigatorFactory` registered under ``name``."""
    return registry.get(name)
