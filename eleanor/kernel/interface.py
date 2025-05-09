from abc import ABC, abstractmethod

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.typing import Species


class AbstractKernel(ABC):

    @abstractmethod
    def setup(self, *args, **kwargs):
        pass

    @abstractmethod
    def run(self, vs_point: vs.Point, *args, **kwargs) -> list[es.Point]:
        pass

    def is_soft_exit(self, code: int) -> bool:
        return code in [0]

    def constrain(self, boatswain: Boatswain) -> Boatswain:
        return boatswain

    def copy_data(self, vs_point: vs.Point, *args, dir: str = '.', **kwargs):
        pass
