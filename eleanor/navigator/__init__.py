"""Public surface of the ``eleanor.navigator`` extension point.

The registry API (:func:`available_navigators`, :func:`get_factory`,
:func:`register_navigator`) is re-exported eagerly.

:class:`~eleanor.navigator.interface.AbstractNavigator` and the built-in
navigator classes (:class:`Random`, :class:`Lattice`, :class:`RandomLattice`,
:class:`LatticeNavigator`) are loaded on demand through :pep:`562`'s
``__getattr__`` hook so importing :mod:`eleanor.navigator` does not pull in
numpy or the kernel interface graph. A matching ``TYPE_CHECKING`` block keeps
static type checkers seeing them as regular re-exports.

Built-in navigator factories live in :mod:`eleanor.navigator.factories`; heavy
concrete-class imports remain deferred inside factory callables and are
discovered via entry points.
"""

from typing import TYPE_CHECKING

from ..exceptions import EleanorException
from ..plugin import is_abstract_instantiation_error, resolve_api_version
from .registry import (
    BUILTIN_NAVIGATORS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    NavigatorFactory,
    available_navigators,
    get_factory,
    register_navigator,
)

if TYPE_CHECKING:
    from ..kernel.interface import AbstractKernel
    from ..order import Order
    from .interface import AbstractNavigator as AbstractNavigator
    from .lattice import Lattice as Lattice
    from .lattice import LatticeNavigator as LatticeNavigator
    from .lattice import RandomLattice as RandomLattice
    from .random import Random as Random


def __getattr__(name: str) -> object:
    if name == "AbstractNavigator":
        from .interface import AbstractNavigator

        return AbstractNavigator
    if name == "Random":
        from .random import Random

        return Random
    if name == "Lattice":
        from .lattice import Lattice

        return Lattice
    if name == "LatticeNavigator":
        from .lattice import LatticeNavigator

        return LatticeNavigator
    if name == "RandomLattice":
        from .lattice import RandomLattice

        return RandomLattice
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def load_navigator(order: "Order", kernel: "AbstractKernel") -> "AbstractNavigator":
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

    from ..typing import cast
    from .interface import AbstractNavigator

    # The protocol is strong, but we want to retain the runtime check because
    # protocols are discarded at runtime. The cast is necessary to satisfy
    # the typechecker (which will think the conditional is always true).
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
