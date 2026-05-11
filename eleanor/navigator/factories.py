"""Built-in navigator factories used by entry-point discovery."""

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..kernel.interface import AbstractKernel
    from ..order import Order
    from .interface import AbstractNavigator


def build_random(order: "Order", kernel: "AbstractKernel", **_args: object) -> "AbstractNavigator":
    if _args:
        warnings.warn(
            'built-in navigator "random" does not accept keyword arguments; ' + f"ignoring: {list(_args)}",
            RuntimeWarning,
            stacklevel=2,
        )
    from .random import Random

    return Random(order, kernel)


def build_random_lattice(order: "Order", kernel: "AbstractKernel", **_args: object) -> "AbstractNavigator":
    if _args:
        warnings.warn(
            'built-in navigator "random_lattice" does not accept keyword arguments; ' + f"ignoring: {list(_args)}",
            RuntimeWarning,
            stacklevel=2,
        )
    from .lattice import RandomLattice

    return RandomLattice(order, kernel)


def build_lattice(order: "Order", kernel: "AbstractKernel", **_args: object) -> "AbstractNavigator":
    if _args:
        warnings.warn(
            'built-in navigator "lattice" does not accept keyword arguments; ' + f"ignoring: {list(_args)}",
            RuntimeWarning,
            stacklevel=2,
        )
    from .lattice import Lattice

    return Lattice(order, kernel)


build_random.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_random_lattice.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_lattice.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
