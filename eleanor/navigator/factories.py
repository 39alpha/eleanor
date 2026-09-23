from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorError
from eleanor.plugin import ConfigurablePluginSpec, SimplePluginSpec

if TYPE_CHECKING:
    from eleanor.navigator.lattice import LatticeNavigator, RandomLatticeNavigator
    from eleanor.navigator.random import RandomNavigator
    from eleanor.navigator.settings import SeedableNavigatorSettings


def build_seedable_settings(raw: dict[str, object]) -> SeedableNavigatorSettings:
    from eleanor.navigator.settings import SeedableNavigatorSettings

    return SeedableNavigatorSettings.from_dict(raw)


def build_random(settings: object) -> RandomNavigator:
    from eleanor.navigator.settings import SeedableNavigatorSettings

    if not isinstance(settings, SeedableNavigatorSettings):
        msg = f"random navigator requires {SeedableNavigatorSettings.__name__}, got {type(settings).__name__}"
        raise EleanorError(msg)

    from eleanor.navigator.random import RandomNavigator

    return RandomNavigator(settings)


random_spec = ConfigurablePluginSpec(
    parse_settings=build_seedable_settings,
    build=build_random,
    plugin_api_version=1,
)


def build_random_lattice(settings: object) -> RandomLatticeNavigator:
    from eleanor.navigator.settings import SeedableNavigatorSettings

    if not isinstance(settings, SeedableNavigatorSettings):
        msg = f"random lattice navigator requires {SeedableNavigatorSettings.__name__}, got {type(settings).__name__}"
        raise EleanorError(msg)

    from eleanor.navigator.lattice import RandomLatticeNavigator

    return RandomLatticeNavigator(settings)


random_lattice_spec = ConfigurablePluginSpec(
    parse_settings=build_seedable_settings,
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
    "random_lattice_spec",
    "random_spec",
]
