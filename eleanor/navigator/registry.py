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
"""
from collections.abc import Callable

from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = 'eleanor.navigators'

#: Environment variable that allows plugin registrations to override built-ins
#: or previously-registered plugins.
OVERRIDE_ENV_VAR = 'ELEANOR_NAVIGATOR_OVERRIDES'

#: Factory callable shape. Each registered navigator is invoked with the
#: current order, kernel, and keyword args from the order file.
NavigatorFactory = Callable[..., object]

#: Canonical names of the navigators shipped inside the eleanor distribution.
#: Built-ins register their concrete factories from
#: :mod:`eleanor.navigator`'s package ``__init__``.
BUILTIN_NAVIGATORS: frozenset[str] = frozenset({'random', 'random_lattice', 'lattice'})

#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[NavigatorFactory] = PluginRegistry(
    kind='navigator',
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_NAVIGATORS,
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
