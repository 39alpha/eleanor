from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorException
from eleanor.kernel.interface import AbstractKernel
from eleanor.kernel.registry import get_factory
from eleanor.plugin import is_abstract_instantiation_error

if TYPE_CHECKING:
    from eleanor.order import Order
    from eleanor.typing import EleanorKwargs, Unpack


def load_kernel(order: Order, kernel_args: list[object], **kwargs: Unpack[EleanorKwargs]) -> AbstractKernel:
    kind = order.kernel.type

    spec = get_factory(kind)
    settings = order.kernel.resolved_settings()
    try:
        kernel = spec.build(settings, *kernel_args)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        msg = f"kernel plugin {kind!r} failed to instantiate (API v{spec.plugin_api_version}): {e}"
        raise EleanorException(msg) from e

    if not isinstance(kernel, AbstractKernel):
        msg = f"kernel plugin {kind!r} returned {type(kernel).__name__}, expected an AbstractKernel"
        raise EleanorException(msg)

    kernel.setup(order, **kwargs)
    kernel.validate_order(order)

    return kernel


__all__ = [
    "AbstractKernel",
    "load_kernel",
]
