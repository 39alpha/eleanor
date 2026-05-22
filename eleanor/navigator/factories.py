import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eleanor.navigator.interface import AbstractNavigator


def build_random(**kwargs: object) -> AbstractNavigator:
    if kwargs:
        warnings.warn(
            f'built-in navigator "random" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=2,
        )
    from eleanor.navigator.random import Random

    return Random()


def build_random_lattice(**kwargs: object) -> AbstractNavigator:
    if kwargs:
        warnings.warn(
            f'built-in navigator "random_lattice" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=2,
        )
    from eleanor.navigator.lattice import RandomLattice

    return RandomLattice()


def build_lattice(**kwargs: object) -> AbstractNavigator:
    if kwargs:
        warnings.warn(
            f'built-in navigator "lattice" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=2,
        )
    from eleanor.navigator.lattice import Lattice

    return Lattice()


build_random.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_random_lattice.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_lattice.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]

__all__ = [
    "build_random",
    "build_random_lattice",
    "build_lattice",
]
