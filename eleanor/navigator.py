import random
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass

import numpy as np

import eleanor.variable_space as vs

from .constraints import Boatswain
from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .order import Order
from .parameters import ListParameter, Parameter, RangeParameter, ValueParameter
from .typing import Generator, Number, Optional, cast


class AbstractNavigator(ABC):
    order: Order
    kernel: AbstractKernel

    def __init__(self, order: Order, kernel: AbstractKernel):
        self.order = order
        self.kernel = kernel

    @abstractmethod
    def navigate(self, scale: int, *args, **kwargs) -> list[vs.Point]:
        pass

    def num_systems(self, scale: int) -> int:
        return scale

    def huffer_problem(self, *args, **kwargs) -> vs.Point:
        return self.navigate(1, *args, **kwargs)[0]

    def supports_success_sampling(self) -> bool:
        return True


class Random(AbstractNavigator):

    def navigate(self, scale: int, *args, **kwargs) -> list[vs.Point]:
        return [self.generate(*args, **kwargs) for _ in range(scale)]

    def generate(self, *args, order_id: Optional[int] = None, **kwargs) -> vs.Point:
        try:
            boatswain = Boatswain(self.order)
            self.kernel.constrain(boatswain)

            parameters = boatswain.constrain()
            while parameters:
                for parameter in parameters:
                    boatswain[parameter] = boatswain[parameter].random()[0]
                parameters = boatswain.constrain()

            return boatswain.generate_vs(order_id)
        except Exception as e:
            raise Exception('failed to select VS point') from e

    def num_systems(self, scale: int) -> int:
        return scale


AbstractNavigator.register(Random)


class LatticeNavigator(AbstractNavigator):

    def navigate(self, scale: int, *args, **kwargs) -> list[vs.Point]:
        boatswain = Boatswain(self.order)
        self.kernel.constrain(boatswain)
        return list(self.iterate(boatswain, [], scale, *args, **kwargs))

    def iterate(
        self,
        boatswain: Boatswain,
        parameters: list[Parameter],
        scale: int,
        *args,
        order_id: Optional[int] = None,
        **kwargs,
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
    def generate(self, parameter: Parameter, scale: int, *args, **kwargs) -> list[ValueParameter]:
        pass

    def num_systems(self, scale: int) -> int:
        return scale**len([1 for p in self.order.parameters() if not isinstance(p, ValueParameter)])


class RandomLattice(LatticeNavigator):

    def generate(self, parameter: Parameter, scale: int, *args, **kwargs) -> list[ValueParameter]:
        return parameter.random(size=scale)


LatticeNavigator.register(RandomLattice)


class Lattice(LatticeNavigator):

    def generate(self, parameter: Parameter, scale: int, *args, **kwargs) -> list[ValueParameter]:
        if scale < 1:
            raise ValueError('')

        return parameter.lattice(size=scale)

    def supports_success_sampling(self) -> bool:
        return False


LatticeNavigator.register(Lattice)
