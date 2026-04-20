from abc import ABC, abstractmethod
from typing import override

import eleanor.variable_space as vs

from .constraints import Boatswain
from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .order import Order
from .parameters import Parameter, ValueParameter
from .typing import Callable, Generator, cast


class AbstractNavigator(ABC):
    order: Order
    kernel: AbstractKernel

    def __init__(self, order: Order, kernel: AbstractKernel):
        self.order = order
        self.kernel = kernel

    @abstractmethod
    def navigate(self, scale: int, *args: object, **kwargs: object) -> list[vs.Point]:
        pass

    def num_systems(self, scale: int) -> int:
        return scale

    def huffer_problem(self, *args: object, **kwargs: object) -> vs.Point:
        points = self.navigate(1, *args, **kwargs)
        if not points:
            raise EleanorException('navigator failed to generate a point')
        return points[0]

    def supports_success_sampling(self) -> bool:
        return True

    def is_complete(self, _batch: list[int]) -> bool:
        return True


class Random(AbstractNavigator):
    @override
    def navigate(self, scale: int, *args: object, **kwargs: object) -> list[vs.Point]:
        generate = cast(Callable[..., vs.Point], self.generate)
        return [generate(*args, **kwargs) for _ in range(scale)]

    def generate(self, *_args: object, order_id: int | None = None, **_kwargs: object) -> vs.Point:
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
            raise Exception('failed to select VS point') from e

    @override
    def num_systems(self, scale: int) -> int:
        return scale


_ = AbstractNavigator.register(Random)


class LatticeNavigator(AbstractNavigator, ABC):
    @override
    def navigate(self, scale: int, *args: object, **kwargs: object) -> list[vs.Point]:
        boatswain = Boatswain(self.order)
        _ = self.kernel.constrain(boatswain)
        iterate = cast(Callable[..., Generator[vs.Point, None, None]], self.iterate)
        return list(iterate(boatswain, [], scale, *args, **kwargs))

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
            try:
                for value in self.generate(boatswain[parameter], scale, *args, **kwargs):
                    boatswain[parameter] = value
                    for point in self.iterate(boatswain, rest, scale, *args, order_id=order_id, **kwargs):
                        yield point
                    boatswain.hardset(parameter, parameter)
            except Exception:
                pass
        else:
            yield boatswain.generate_vs(order_id)

    @abstractmethod
    def generate(self, parameter: Parameter, scale: int, *args: object, **kwargs: object) -> list[ValueParameter]:
        pass

    @override
    def num_systems(self, scale: int) -> int:
        return cast(int, scale**len([1 for p in self.order.parameters() if not isinstance(p, ValueParameter)]))


class RandomLattice(LatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        return parameter.random(size=scale)


_ = LatticeNavigator.register(RandomLattice)


class Lattice(LatticeNavigator):
    @override
    def generate(self, parameter: Parameter, scale: int, *_args: object, **_kwargs: object) -> list[ValueParameter]:
        if scale < 1:
            raise ValueError('')

        return parameter.lattice(size=scale)

    @override
    def supports_success_sampling(self) -> bool:
        return False


_ = LatticeNavigator.register(Lattice)
