import warnings

from ..exceptions import EleanorException
from ..kernel.interface import AbstractKernel
from ..order import Order
from ..plugin import is_abstract_instantiation_error, resolve_api_version
from ..typing import cast
from .interface import AbstractNavigator
from .lattice import Lattice, LatticeNavigator, RandomLattice
from .random import Random
from .registry import (
    BUILTIN_NAVIGATORS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    NavigatorFactory,
    available_navigators,
    get_factory,
    register_navigator,
)


# Seed the registry with the built-in navigator factories. The class bodies
# accept ``(order, kernel)`` positionally, which matches the plugin factory
# signature; extra keyword args coming from the order file are intentionally
# ignored since none of the built-ins consume them.
def _builtin_navigator(cls: type[AbstractNavigator]) -> NavigatorFactory:
    def factory(order: Order, kernel: AbstractKernel, **_args: object) -> AbstractNavigator:
        if _args:
            warnings.warn(
                f'built-in navigator "{cls.__name__}" does not accept keyword ' + f"arguments; ignoring: {list(_args)}",
                RuntimeWarning,
                stacklevel=2,
            )
        return cls(order, kernel)

    factory.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]

    return factory


register_navigator("random", _builtin_navigator(Random))
register_navigator("random_lattice", _builtin_navigator(RandomLattice))
register_navigator("lattice", _builtin_navigator(Lattice))


def load_navigator(order: Order, kernel: AbstractKernel) -> AbstractNavigator:
    navigator_factory = get_factory(order.navigator.type)
    version = resolve_api_version(navigator_factory)
    try:
        built = navigator_factory(order, kernel, **order.navigator.args)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        raise EleanorException(
            f'navigator plugin "{order.navigator.type}" failed to instantiate{version_suffix}: {e}',
        ) from e

    # The protocol is strong, but we want to retain the runtime check because
    # protocols are discarded at runtime. The case here is necessary to satisfy
    # the typechecker (which will thing the conditional is always true).
    built_obj = cast(object, built)
    if not isinstance(built_obj, AbstractNavigator):
        raise EleanorException(
            f'navigator plugin "{order.navigator.type}" returned '
            + f"{type(built).__name__}, expected an AbstractNavigator",
        )
    return built


__all__ = [
    "AbstractNavigator",
    "BUILTIN_NAVIGATORS",
    "ENTRY_POINT_GROUP",
    "Lattice",
    "LatticeNavigator",
    "NavigatorFactory",
    "OVERRIDE_ENV_VAR",
    "Random",
    "RandomLattice",
    "available_navigators",
    "get_factory",
    "load_navigator",
    "register_navigator",
]
