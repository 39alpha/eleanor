"""Public surface of the ``eleanor.kernel`` extension point.

The registry API (:func:`available_kernels`, :func:`get_factory`,
:func:`register_kernel`) is re-exported from :mod:`eleanor.kernel.registry`.

Built-in kernel factories live in :mod:`eleanor.kernel.factories` and are
discovered via entry points declared in ``pyproject.toml``.

:class:`~eleanor.kernel.interface.AbstractKernel` is loaded on demand through
:pep:`562`'s ``__getattr__`` hook so importing :mod:`eleanor.kernel` does not
pull in numpy or the Fortran data1 loader. A matching ``TYPE_CHECKING`` block
keeps static type checkers seeing it as a regular re-export.

The heavy dependencies of each built-in (for example eq36's numpy / Fortran /
ORM imports) are deferred inside the factory bodies, so merely touching
:mod:`eleanor.kernel` does not drag them in.
"""

from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorException
from eleanor.plugin import is_abstract_instantiation_error

from .registry import (
    BUILTIN_KERNELS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    KernelFactory,
    KernelSpec,
    available_kernels,
    get_factory,
    register_kernel,
)

if TYPE_CHECKING:
    from eleanor.order import Order
    from eleanor.typing import EleanorKwargs, Unpack

    from .interface import AbstractKernel as AbstractKernel


def __getattr__(name: str) -> object:
    if name == "AbstractKernel":
        from .interface import AbstractKernel

        return AbstractKernel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def load_kernel(
    order: "Order",
    kernel_args: list[object],
    **kwargs: "Unpack[EleanorKwargs]",
) -> "AbstractKernel":
    spec = get_factory(order.kernel.type)
    settings = order.kernel.resolved_settings()
    try:
        kernel = spec.build(settings, *kernel_args)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        raise EleanorException(
            f'kernel plugin "{order.kernel.type}" failed to instantiate ' + f"(API v{spec.plugin_api_version}): {e}",
        ) from e
    from .interface import AbstractKernel

    if not isinstance(kernel, AbstractKernel):
        raise EleanorException(
            f'kernel plugin "{order.kernel.type}" returned ' + f"{type(kernel).__name__}, expected an AbstractKernel",
        )
    kernel.setup(order, **kwargs)
    kernel.validate_order(order)
    return kernel


__all__ = [
    "AbstractKernel",
    "BUILTIN_KERNELS",
    "ENTRY_POINT_GROUP",
    "KernelFactory",
    "KernelSpec",
    "OVERRIDE_ENV_VAR",
    "available_kernels",
    "get_factory",
    "load_kernel",
    "register_kernel",
]
