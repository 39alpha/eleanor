from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass

import numpy as np

from .exceptions import EleanorException
from .kernel.eq36.data0_tools import TPCurve
from .kernel.interface import AbstractKernel
from .problem import Problem
from .typing import Number


class AbstractNavigator(ABC):

    def __init__(self, kernel: AbstractKernel):
        self.kernel = kernel

    def navigate(self, problem: Problem, n: int) -> list[Problem]:
        return [self.fix(problem) for _ in range(n)]

    @abstractmethod
    def fix(self, problem: Problem) -> Problem:
        pass


class UniformNavigator(AbstractNavigator):

    def fix(self, problem: Problem) -> Problem:
        problem = deepcopy(problem)
        constrained = self.kernel.constrain(problem)
        independent_parameters = constrained.resolve()
        while independent_parameters:
            for parameter in independent_parameters:
                if parameter.value is not None:
                    pass
                elif parameter.min is not None and parameter.max is not None:
                    # DGM: The return type for np.random.uniform is wrong when size=None. MyPy thinks it always returns an
                    #      array, so we have to tell it to generate an array of 1 element and take that one element.
                    parameter.fix(np.random.uniform(parameter.min, parameter.max, size=1)[0])
                elif parameter.values is not None:
                    parameter.fix(np.random.choice(np.asarray(parameter.values)))
                else:
                    raise EleanorException('problem is in an unexpected state')

            independent_parameters = constrained.resolve()

        return problem


AbstractNavigator.register(UniformNavigator)
