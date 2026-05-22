import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eleanor.kernel.interface import AbstractKernel
    from eleanor.navigator.interface import AbstractNavigator
    from eleanor.order import Order


def build_random(order: Order, kernel: AbstractKernel, **kwargs: object) -> AbstractNavigator:
    if kwargs:
        warnings.warn(
            f'built-in navigator "random" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=2,
        )
    from eleanor.navigator.random import Random

    return Random(order, kernel)


def build_random_lattice(order: Order, kernel: AbstractKernel, **kwargs: object) -> AbstractNavigator:
    if kwargs:
        warnings.warn(
            f'built-in navigator "random_lattice" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=2,
        )
    from eleanor.navigator.lattice import RandomLattice

    return RandomLattice(order, kernel)


def build_lattice(order: Order, kernel: AbstractKernel, **kwargs: object) -> AbstractNavigator:
    if kwargs:
        warnings.warn(
            f'built-in navigator "lattice" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=2,
        )
    from eleanor.navigator.lattice import Lattice

    return Lattice(order, kernel)


build_random.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_random_lattice.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_lattice.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]

__all__ = [
    "build_random",
    "build_random_lattice",
    "build_lattice",
]
