"""
Registry and discovery for eleanor navigator plugins.

Built-in navigators (``random``, ``random_lattice``, ``lattice``) are
registered at module import time. Third-party navigators advertise themselves
through the ``eleanor.navigators`` entry-point group.

Each registered factory is a callable invoked as
``factory(order, kernel, **args)`` where ``args`` is the optional ``args``
block from the order file's ``navigator`` section. Any
:class:`~eleanor.navigator.AbstractNavigator` subclass whose ``__init__``
accepts ``(order, kernel, **kwargs)`` can be registered directly as its own
factory.
"""
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from eleanor.plugin import PluginRegistry

if TYPE_CHECKING:
    from . import AbstractNavigator

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = 'eleanor.navigators'

#: Environment variable that allows plugin registrations to override built-ins
#: or previously-registered plugins.
OVERRIDE_ENV_VAR = 'ELEANOR_NAVIGATOR_OVERRIDES'

#: Factory callable shape. Each registered navigator is invoked with the
#: current order, kernel, and keyword args from the order file.
NavigatorFactory = Callable[..., 'AbstractNavigator']


def _build_random(order: Any, kernel: Any, **args: Any) -> 'AbstractNavigator':
    from . import Random

    return Random(order, kernel, **args)


def _build_random_lattice(order: Any, kernel: Any, **args: Any) -> 'AbstractNavigator':
    from . import RandomLattice

    return RandomLattice(order, kernel, **args)


def _build_lattice(order: Any, kernel: Any, **args: Any) -> 'AbstractNavigator':
    from . import Lattice

    return Lattice(order, kernel, **args)


#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[NavigatorFactory] = PluginRegistry(
    kind='navigator',
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={
        'random': _build_random,
        'random_lattice': _build_random_lattice,
        'lattice': _build_lattice,
    },
)

#: Canonical names of the navigators shipped inside the eleanor distribution.
BUILTIN_NAVIGATORS: frozenset[str] = registry.builtins


def register_navigator(name: str, factory: NavigatorFactory) -> None:
    """Register ``factory`` under ``name`` in the navigator registry."""
    registry.register(name, factory)


def available_navigators() -> frozenset[str]:
    """Return the set of currently-registered navigator names."""
    return registry.available()


def get_factory(name: str) -> NavigatorFactory:
    """Return the :data:`NavigatorFactory` registered under ``name``."""
    return registry.get(name)
