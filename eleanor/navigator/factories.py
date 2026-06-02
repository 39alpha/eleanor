from typing import TYPE_CHECKING

from eleanor.plugin import SimplePluginSpec

if TYPE_CHECKING:
    from eleanor.navigator.lattice import LatticeNavigator, RandomLatticeNavigator
    from eleanor.navigator.random import RandomNavigator


def build_random() -> RandomNavigator:
    from eleanor.navigator.random import RandomNavigator

    return RandomNavigator()


random_spec = SimplePluginSpec(
    build=build_random,
    plugin_api_version=1,
)


def build_random_lattice() -> RandomLatticeNavigator:
    from eleanor.navigator.lattice import RandomLatticeNavigator

    return RandomLatticeNavigator()


random_lattice_spec = SimplePluginSpec(
    build=build_random_lattice,
    plugin_api_version=1,
)


def build_lattice() -> LatticeNavigator:
    from eleanor.navigator.lattice import LatticeNavigator

    return LatticeNavigator()


lattice_spec = SimplePluginSpec(
    build=build_lattice,
    plugin_api_version=1,
)

__all__ = [
    "lattice_spec",
    "random_spec",
    "random_lattice_spec",
]
