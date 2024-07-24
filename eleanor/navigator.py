import random
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass

import numpy as np

from .config import Config, ListParameter, Parameter, RangeParameter, ValueParameter
from .constraints import Boatswain
from .exceptions import EleanorException
from .kernel.eq36.data0_tools import TPCurve
from .kernel.interface import AbstractKernel
from .models import VSPoint
from .typing import Number, Optional, cast


class AbstractNavigator(ABC):
    config: Config
    kernel: AbstractKernel

    def __init__(self, config: Config, kernel: AbstractKernel):
        self.config = config
        self.kernel = kernel

    def navigate(self, n: int, max_attempts: int = 1) -> list[VSPoint]:
        return [self.select(max_attempts) for _ in range(n)]

    def select(self, max_attempts: int = 1) -> VSPoint:
        last_exception: Optional[Exception] = None
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            try:
                boatswain = Boatswain(self.config)
                self.kernel.constrain(boatswain)

                parameters = boatswain.constrain()
                while parameters:
                    for parameter in parameters:
                        boatswain[parameter] = self.fix(boatswain[parameter])
                    parameters = boatswain.constrain()

                return boatswain.generate_vs()
            except Exception as e:
                last_exception = e

        raise Exception('failed to select VS point') from last_exception

    @abstractmethod
    def fix(self, parameter: Parameter) -> Parameter:
        pass


class UniformNavigator(AbstractNavigator):

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


AbstractNavigator.register(UniformNavigator)
