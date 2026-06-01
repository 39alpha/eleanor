from eleanor.plugin import SimplePluginSpec


def build_random() -> object:
    from eleanor.navigator.random import Random

    return Random()


random_spec = SimplePluginSpec(
    build=build_random,
    plugin_api_version=1,
)


def build_random_lattice() -> object:
    from eleanor.navigator.lattice import RandomLattice

    return RandomLattice()


random_lattice_spec = SimplePluginSpec(
    build=build_random_lattice,
    plugin_api_version=1,
)


def build_lattice() -> object:
    from eleanor.navigator.lattice import Lattice

    return Lattice()


lattice_spec = SimplePluginSpec(
    build=build_lattice,
    plugin_api_version=1,
)

__all__ = [
    "lattice_spec",
    "random_spec",
    "random_lattice_spec",
]
