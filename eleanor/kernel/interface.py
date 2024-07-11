from abc import ABC, abstractmethod

from eleanor.models import Result
from eleanor.problem import Problem
from eleanor.typing import Float, Species


class AbstractKernel(ABC):

    @abstractmethod
    def setup(self, *args, **kwargs):
        pass

    @abstractmethod
    def run(self, problem: Problem, *args, **kwargs) -> tuple[Result, Result]:
        pass

    @abstractmethod
    def get_species(self) -> Species:
        pass

    def constrain(self, problem: Problem) -> Problem:
        return problem
