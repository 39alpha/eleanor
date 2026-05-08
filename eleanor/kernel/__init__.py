"""Public surface of the ``eleanor.kernel`` extension point.

The registry API (:func:`available_kernels`, :func:`get_factory`,
:func:`register_kernel`) is re-exported from :mod:`eleanor.kernel.registry`.

Built-in kernel factories are defined and registered **here**, in the parent
package, so registration is triggered by any import that reaches into
``eleanor.kernel`` (every CLI entry point already does, transitively through
``eleanor.order``, ``eleanor.eleanor``, etc.). This matches the pattern used
by :mod:`eleanor.executor` and :mod:`eleanor.output` and replaces the older
arrangement that relied on some unrelated module pre-importing
``eleanor.kernel.eq36`` for its registration side effect.

:class:`~eleanor.kernel.interface.AbstractKernel` is loaded on demand through
:pep:`562`'s ``__getattr__`` hook so importing :mod:`eleanor.kernel` does not
pull in numpy or the Fortran data1 loader. A matching ``TYPE_CHECKING`` block
keeps static type checkers seeing it as a regular re-export.

The heavy dependencies of each built-in (for example eq36's numpy / Fortran
/ ORM imports) are deferred inside the factory bodies, so merely touching
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


def _build_eq36_settings(raw: dict[str, object]) -> object:
    """Parse a raw ``kernel.args`` mapping into an eq36 :class:`Settings`.

    Imported lazily so :mod:`eleanor.kernel` can register the ``eq36`` factory
    without eagerly pulling in ``eleanor.kernel.eq36``'s heavy transitive
    dependencies.
    """
    from .eq36.settings import Settings  # noqa: PLC0415

    return Settings.from_dict(raw)


def _build_eq36(settings: object, *args: object) -> object:
    """Construct the eq36 :class:`Kernel` from its typed settings + CLI args.

    Deferred eq36 imports mirror :func:`_build_eq36_settings`; invoking the
    factory is what pays for the subpackage's transitive imports (numpy,
    the Fortran data1 loader, constraint helpers, etc.).
    """
    from .eq36.kernel import Kernel  # noqa: PLC0415
    from .eq36.settings import Settings  # noqa: PLC0415

    if not isinstance(settings, Settings):
        raise EleanorException(
            f"eq36 kernel requires eq36 Settings, got {type(settings).__name__}",
        )
    if not args:
        raise EleanorException("eq36 kernel requires a data1_dir argument")
    data1_dir, *rest = args
    if not isinstance(data1_dir, str):
        raise EleanorException(
            f"eq36 kernel requires a string data1_dir, got {type(data1_dir).__name__}",
        )
    # ``rest`` contains any additional positional arguments supplied by the
    # caller (e.g. extra CLI arguments passed via ``Eleanor.kernel_args``).
    # They are forwarded to ``Kernel.__init__`` unvalidated; ``Kernel`` is
    # responsible for rejecting unexpected arguments.
    return Kernel(settings, data1_dir, *rest)


register_kernel(
    "eq36",
    KernelSpec(
        settings_from_dict=_build_eq36_settings,
        build=_build_eq36,
        plugin_api_version=1,
    ),
)


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
