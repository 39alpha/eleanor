from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterator
from itertools import batched
from typing import TYPE_CHECKING, cast, override

import numpy as np

import eleanor.variable_space as vs
from eleanor.constraints.point_builder import PointBuilder
from eleanor.exceptions import EleanorError
from eleanor.navigator.interface import AbstractNavigator
from eleanor.navigator.settings import SeedableNavigatorSettings
from eleanor.parameters import Parameter, ValueParameter

if TYPE_CHECKING:
    from eleanor.kernel import AbstractKernel
    from eleanor.order import Order


class AbstractLatticeNavigator(AbstractNavigator, ABC):
    @override
    def navigate(
        self,
        order: Order,
        kernel: AbstractKernel,
        scale: int,
        batch_size: int,
        *args: object,
        **kwargs: object,
    ) -> Iterator[list[vs.Point]]:
        point_builder = PointBuilder(order)
        _ = kernel.constrain(point_builder)

        iterate = cast(Callable[..., Generator[vs.Point]], self.iterate)
        for batch in batched(
            iterate(order, point_builder, [], scale, *args, **kwargs),
            batch_size,
            strict=False,
        ):
            yield list(batch)

    def iterate(
        self,
        order: Order,
        point_builder: PointBuilder,
        parameters: list[Parameter],
        scale: int,
        *args: object,
        **kwargs: object,
    ) -> Generator[vs.Point]:
        if not parameters:
            parameters = point_builder.constrain()

        if parameters:
            parameter, *rest = parameters
            for value in self.generate(point_builder[parameter], scale, *args, rng=order.rng, **kwargs):
                point_builder[parameter] = value
                yield from self.iterate(order, point_builder, rest, scale, *args, **kwargs)
                point_builder.hardset(parameter, parameter)
        else:
            yield point_builder.generate_vs()

    @abstractmethod
    def generate(
        self, parameter: Parameter, scale: int, *args: object, rng: np.random.Generator | None, **kwargs: object
    ) -> list[ValueParameter]:
        pass

    @override
    def num_systems(self, order: Order, scale: int) -> int:
        return cast(int, scale ** len([1 for p in order.parameters() if not isinstance(p, ValueParameter)]))


class RandomLatticeNavigator(AbstractLatticeNavigator):
    _rng: np.random.Generator

    def __init__(self, settings: SeedableNavigatorSettings) -> None:
        super().__init__()
        self._rng = np.random.default_rng(seed=settings.seed)

    @override
    def generate(
        self,
        parameter: Parameter,
        scale: int,
        *_args: object,
        rng: np.random.Generator | None,
        **_kwargs: object,
    ) -> list[ValueParameter]:
        return parameter.random(size=scale, rng=rng)


_ = AbstractLatticeNavigator.register(RandomLatticeNavigator)


class LatticeNavigator(AbstractLatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        if scale < 1:
            msg = "cannot generate points when scale < 1"
            raise EleanorError(msg)

        return parameter.lattice(size=scale)


_ = AbstractLatticeNavigator.register(LatticeNavigator)

__all__ = [
    "AbstractLatticeNavigator",
    "LatticeNavigator",
    "RandomLatticeNavigator",
]
