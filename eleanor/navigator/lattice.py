from abc import ABC, abstractmethod
from collections.abc import Iterator
from itertools import batched
from typing import TYPE_CHECKING, override

import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.exceptions import EleanorException
from eleanor.navigator.interface import AbstractNavigator
from eleanor.parameters import Parameter, ValueParameter
from eleanor.typing import Callable, Generator, cast

if TYPE_CHECKING:
    from eleanor.kernel import AbstractKernel
    from eleanor.order import Order


class LatticeNavigator(AbstractNavigator, ABC):
    @override
    def navigate(
        self,
        order: Order,
        kernel: AbstractKernel,
        scale: int,
        batch_size: int,
        *args: object,
        order_id: int | None = None,
        **kwargs: object,
    ) -> Iterator[list[vs.Point]]:
        boatswain = Boatswain(order)
        _ = kernel.constrain(boatswain)

        iterate = cast(Callable[..., Generator[vs.Point, None, None]], self.iterate)
        for batch in batched(iterate(order, boatswain, [], scale, *args, order_id=order_id, **kwargs), batch_size):
            yield list(batch)

    def iterate(
        self,
        order: Order,
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
                for point in self.iterate(order, boatswain, rest, scale, *args, order_id=order_id, **kwargs):
                    yield point
                boatswain.hardset(parameter, parameter)
        else:
            yield boatswain.generate_vs(order_id if order_id is not None else order.id)

    @abstractmethod
    def generate(self, parameter: Parameter, scale: int, *args: object, **kwargs: object) -> list[ValueParameter]:
        pass

    @override
    def num_systems(self, order: Order, scale: int) -> int:
        return cast(int, scale ** len([1 for p in order.parameters() if not isinstance(p, ValueParameter)]))


class RandomLattice(LatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        return parameter.random(size=scale)


_ = LatticeNavigator.register(RandomLattice)


class Lattice(LatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        if scale < 1:
            msg = "cannot generate points when scale < 1"
            raise EleanorException(msg)

        return parameter.lattice(size=scale)


_ = LatticeNavigator.register(Lattice)

__all__ = [
    "LatticeNavigator",
    "RandomLattice",
    "Lattice",
]
