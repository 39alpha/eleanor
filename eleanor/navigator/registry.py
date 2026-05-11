"""
Registry and discovery for eleanor navigator plugins.

Built-in navigators (``random``, ``random_lattice``, ``lattice``) are declared
as entry points in ``pyproject.toml`` and discovered lazily on first registry
access. Third-party navigators advertise themselves through the same
``eleanor.navigators`` entry-point group.

Each registered factory is a callable invoked as
``factory(order, kernel, **args)`` where ``args`` is the optional ``args``
block from the order file's ``navigator`` section. ``NavigatorFactory`` is a
``Protocol`` that pins the leading positional parameters and return type while
keeping plugin-specific keyword arguments open; callers still validate the
returned navigator against :class:`~eleanor.navigator.AbstractNavigator`
before use.

Navigator plugins declare API compatibility via a module- or function-level
``__eleanor_api_version__`` attribute. Registration checks this against this
module's ``PLUGIN_API_VERSION``/``MIN_SUPPORTED_API_VERSION`` policy; see
``AGENTS.md`` for details.
"""

from typing import TYPE_CHECKING, Protocol

from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = "eleanor.navigators"

#: Environment variable that, when truthy, downgrades API-version mismatches
#: to warnings instead of hard errors. All other discovery and registration
#: errors are always hard errors regardless of this variable.
OVERRIDE_ENV_VAR = "ELEANOR_NAVIGATOR_OVERRIDES"
PLUGIN_API_VERSION: int = 1
MIN_SUPPORTED_API_VERSION: int = 1

if TYPE_CHECKING:
    from eleanor.kernel.interface import AbstractKernel
    from eleanor.navigator.interface import AbstractNavigator
    from eleanor.order import Order


class NavigatorFactory(Protocol):
    def __call__(
        self,
        order: "Order",
        kernel: "AbstractKernel",
        /,
        **kwargs: object,
    ) -> "AbstractNavigator": ...


#: Canonical names of the navigators shipped inside the eleanor distribution.
#: Their concrete factories live in :mod:`eleanor.navigator.factories` and are
#: discovered via entry points.
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
