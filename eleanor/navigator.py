import random
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from itertools import cycle, islice

import numpy as np

import eleanor.variable_space as vs

from .constraints import Boatswain
from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .order import Order
from .parameters import ListParameter, Parameter, RangeParameter, ValueParameter
from .typing import Number, Optional, cast


class AbstractNavigator(ABC):
    order: Order
    kernel: AbstractKernel

    def __init__(self, order: Order, kernel: AbstractKernel):
        self.order = order
        self.kernel = kernel

    def navigate(self, n: int, order_id: Optional[int] = None, max_attempts: int = 1) -> list[vs.Point]:
        return [self.select(order_id, max_attempts) for _ in range(n)]

    def select(self, order_id: Optional[int] = None, max_attempts: int = 1) -> vs.Point:
        last_exception: Optional[Exception] = None
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            try:
                boatswain = Boatswain(self.order)
                self.kernel.constrain(boatswain)

                parameters = boatswain.constrain()
                while parameters:
                    for parameter in parameters:
                        boatswain[parameter] = self.fix(boatswain[parameter])
                    parameters = boatswain.constrain()

                return boatswain.generate_vs(order_id)
            except Exception as e:
                last_exception = e

        raise Exception('failed to select VS point') from last_exception

    def num_systems(self, n: int) -> int:
        return n

    @abstractmethod
    def fix(self, parameter: Parameter) -> Parameter:
        pass


class Uniform(AbstractNavigator):

    def fix(self, parameter: Parameter) -> ValueParameter:
        return parameter.random()


AbstractNavigator.register(Uniform)


class Lattice(AbstractNavigator):

    def navigate(self, n: int, order_id: Optional[int] = None, max_attempts: int = 1) -> list[vs.Point]:
        boatswain = Boatswain(self.order)
        self.kernel.constrain(boatswain)
        return list(self.iterate(boatswain, [], n, order_id=order_id))

    def iterate(self, boatswain: Boatswain, parameters: list[Parameter], steps: int, order_id: Optional[int] = None):
        if not parameters:
            parameters = boatswain.constrain()

        if parameters:
            parameter, *rest = parameters
            try:
                for value in self.lattice(boatswain[parameter], steps):
                    boatswain[parameter] = value
                    for point in self.iterate(boatswain, rest, steps, order_id=order_id):
                        yield point
                    boatswain.hardset(parameter, parameter)
            except Exception:
                pass
        else:
            yield boatswain.generate_vs(order_id)

    def fix(self, parameter: Parameter) -> ValueParameter:
        if isinstance(parameter, ValueParameter):
            return parameter
        elif isinstance(parameter, RangeParameter):
            value = random.uniform(parameter.min, parameter.max)
            return parameter.fix(value)
        elif isinstance(parameter, ListParameter):
            value = random.choice(parameter.values)
            return parameter.fix(value)
        else:
            raise EleanorException(f'unexpected parameter type "{type(parameter)}"')

    def lattice(self, parameter: Parameter, steps: int):
        if isinstance(parameter, ValueParameter):
            yield parameter
        elif isinstance(parameter, RangeParameter):
            for value in np.linspace(parameter.min, parameter.max, num=steps):
                yield parameter.fix(float(value))
        elif isinstance(parameter, ListParameter):
            for value in islice(cycle(parameter.values), steps):
                yield parameter.fix(value)
        else:
            raise EleanorException(f'unexpected parameter type "{type(parameter)}"')

    def num_systems(self, n: int) -> int:
        return n**len([1 for p in self.order.parameters() if not isinstance(p, ValueParameter)])


AbstractNavigator.register(Lattice)
