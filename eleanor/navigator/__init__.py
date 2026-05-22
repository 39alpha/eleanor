from typing import TYPE_CHECKING, cast

from eleanor.exceptions import EleanorException
from eleanor.navigator.interface import AbstractNavigator
from eleanor.navigator.registry import get_factory
from eleanor.plugin import is_abstract_instantiation_error, resolve_api_version

if TYPE_CHECKING:
    from eleanor.kernel.interface import AbstractKernel
    from eleanor.order import Order


def load_navigator(order: Order, kernel: AbstractKernel) -> AbstractNavigator:
    kind = order.navigator.type
    args = order.navigator.args

    navigator_factory = get_factory(kind)
    version = resolve_api_version(navigator_factory)
    try:
        built = navigator_factory(order, kernel, **args)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        msg = f"navigator plugin {kind!r} failed to instantiate{version_suffix}: {e}"
        raise EleanorException(msg) from e

    if not isinstance(cast(object, built), AbstractNavigator):
        msg = f"navigator plugin {kind!r} returned {type(built).__name__}, expected an AbstractNavigator"
        raise EleanorException(msg)

    return built


__all__ = [
    "AbstractNavigator",
    "load_navigator",
]
