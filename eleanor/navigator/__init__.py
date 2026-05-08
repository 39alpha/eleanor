import warnings
from abc import ABC, abstractmethod
from collections.abc import Iterator
from itertools import batched
from typing import override

import eleanor.variable_space as vs

from ..constraints import Boatswain
from ..exceptions import EleanorException
from ..kernel.interface import AbstractKernel
from ..order import Order
from ..parameters import Parameter, ValueParameter
from ..plugin import is_abstract_instantiation_error, resolve_api_version
from ..typing import Callable, Generator, cast


class AbstractNavigator(ABC):
    order: Order
    kernel: AbstractKernel

    def __init__(self, order: Order, kernel: AbstractKernel):
        self.order = order
        self.kernel = kernel

    @abstractmethod
    def navigate(self, scale: int, batch_size: int, *args: object, **kwargs: object) -> Iterator[list[vs.Point]]:
        pass

    def num_systems(self, scale: int) -> int:
        return scale


class Random(AbstractNavigator):
    @override
    def navigate(self, scale: int, batch_size: int, *args: object, **kwargs: object) -> Iterator[list[vs.Point]]:
        generate = cast(Callable[..., vs.Point], self.generate)
        for batch in batched((generate(*args, **kwargs) for _ in range(scale)), batch_size):
            yield list(batch)

    def generate(self, *_args: object, order_id: int | None = None, **kwargs: object) -> vs.Point:
        max_attempts: object = kwargs.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
            raise EleanorException(f"max_attempts must be an integer, got {type(max_attempts).__name__}")
        elif max_attempts < 1:
            raise EleanorException(f"max_attempts must be at least one, got {max_attempts}")

        last_exception: Exception | None = None
        while max_attempts > 0:
            try:
                boatswain = Boatswain(self.order)
                _ = self.kernel.constrain(boatswain)

                parameters = boatswain.constrain()
                while parameters:
                    for parameter in parameters:
                        boatswain[parameter] = boatswain[parameter].random()[0]
                    parameters = boatswain.constrain()

                return boatswain.generate_vs(order_id)
            except Exception as e:
                last_exception = e
                max_attempts -= 1

        raise EleanorException("failed to select VS point") from last_exception

    @override
    def num_systems(self, scale: int) -> int:
        return scale


_ = AbstractNavigator.register(Random)


class LatticeNavigator(AbstractNavigator, ABC):
    @override
    def navigate(self, scale: int, batch_size: int, *args: object, **kwargs: object) -> Iterator[list[vs.Point]]:
        boatswain = Boatswain(self.order)
        _ = self.kernel.constrain(boatswain)
        iterate = cast(Callable[..., Generator[vs.Point, None, None]], self.iterate)
        for batch in batched(iterate(boatswain, [], scale, *args, **kwargs), batch_size):
            yield list(batch)

    def iterate(
        self,
        boatswain: Boatswain,
        parameters: list[Parameter],
        scale: int,
        *args: object,
        order_id: int | None = None,
        **kwargs: object,
    ) -> Generator[vs.Point, None, None]:
        if not parameters:
            parameters = boatswain.constrain()

        if parameters:
            parameter, *rest = parameters
            for value in self.generate(boatswain[parameter], scale, *args, **kwargs):
                boatswain[parameter] = value
                for point in self.iterate(boatswain, rest, scale, *args, order_id=order_id, **kwargs):
                    yield point
                boatswain.hardset(parameter, parameter)
        else:
            yield boatswain.generate_vs(order_id)

    @abstractmethod
    def generate(self, parameter: Parameter, scale: int, *args: object, **kwargs: object) -> list[ValueParameter]:
        pass

    @override
    def num_systems(self, scale: int) -> int:
        return cast(int, scale ** len([1 for p in self.order.parameters() if not isinstance(p, ValueParameter)]))


class RandomLattice(LatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        return parameter.random(size=scale)


_ = LatticeNavigator.register(RandomLattice)


class Lattice(LatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        if scale < 1:
            raise ValueError("")

        return parameter.lattice(size=scale)


_ = LatticeNavigator.register(Lattice)


from .registry import (  # noqa: E402
    BUILTIN_NAVIGATORS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    NavigatorFactory,
    available_navigators,
    get_factory,
    register_navigator,
)


# Seed the registry with the built-in navigator factories. The class bodies
# accept ``(order, kernel)`` positionally, which matches the plugin factory
# signature; extra keyword args coming from the order file are intentionally
# ignored since none of the built-ins consume them.
def _builtin_navigator(cls: type[AbstractNavigator]) -> NavigatorFactory:
    def factory(order: Order, kernel: AbstractKernel, **_args: object) -> AbstractNavigator:
        if _args:
            warnings.warn(
                f'built-in navigator "{cls.__name__}" does not accept keyword ' + f"arguments; ignoring: {list(_args)}",
                RuntimeWarning,
                stacklevel=2,
            )
        return cls(order, kernel)

    factory.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]

    return factory


register_navigator("random", _builtin_navigator(Random))
register_navigator("random_lattice", _builtin_navigator(RandomLattice))
register_navigator("lattice", _builtin_navigator(Lattice))


def load_navigator(order: Order, kernel: AbstractKernel) -> AbstractNavigator:
    navigator_factory = get_factory(order.navigator.type)
    version = resolve_api_version(navigator_factory)
    try:
        built = navigator_factory(order, kernel, **order.navigator.args)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        raise EleanorException(
            f'navigator plugin "{order.navigator.type}" failed to instantiate{version_suffix}: {e}',
        ) from e
    if not isinstance(built, AbstractNavigator):
        raise EleanorException(
            f'navigator plugin "{order.navigator.type}" returned '
            + f"{type(built).__name__}, expected an AbstractNavigator",
        )
    return built


__all__ = [
    "AbstractNavigator",
    "BUILTIN_NAVIGATORS",
    "ENTRY_POINT_GROUP",
    "Lattice",
    "LatticeNavigator",
    "NavigatorFactory",
    "OVERRIDE_ENV_VAR",
    "Random",
    "RandomLattice",
    "available_navigators",
    "get_factory",
    "load_navigator",
    "register_navigator",
]
