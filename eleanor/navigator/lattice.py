from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterator
from itertools import batched
from typing import TYPE_CHECKING, cast, override

import eleanor.variable_space as vs
from eleanor.constraints.point_builder import PointBuilder
from eleanor.exceptions import EleanorError
from eleanor.navigator.interface import AbstractNavigator
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
        order_id: int | None = None,
        **kwargs: object,
    ) -> Iterator[list[vs.Point]]:
        point_builder = PointBuilder(order)
        _ = kernel.constrain(point_builder)

        iterate = cast(Callable[..., Generator[vs.Point]], self.iterate)
        for batch in batched(
            iterate(order, point_builder, [], scale, *args, order_id=order_id, **kwargs),
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
        order_id: int | None = None,
        **kwargs: object,
    ) -> Generator[vs.Point]:
        if not parameters:
            parameters = point_builder.constrain()

        if parameters:
            parameter, *rest = parameters
            for value in self.generate(point_builder[parameter], scale, *args, **kwargs):
                point_builder[parameter] = value
                yield from self.iterate(order, point_builder, rest, scale, *args, order_id=order_id, **kwargs)
                point_builder.hardset(parameter, parameter)
        else:
            yield point_builder.generate_vs(order_id if order_id is not None else order.id)

    @abstractmethod
    def generate(self, parameter: Parameter, scale: int, *args: object, **kwargs: object) -> list[ValueParameter]:
        pass

    @override
    def num_systems(self, order: Order, scale: int) -> int:
        return cast(int, scale ** len([1 for p in order.parameters() if not isinstance(p, ValueParameter)]))


class RandomLatticeNavigator(AbstractLatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        return parameter.random(size=scale)


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
