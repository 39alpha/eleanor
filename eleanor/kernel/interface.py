from abc import ABC, abstractmethod

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.typing import Species


class AbstractKernel(ABC):

    @abstractmethod
    def version(self) -> str:
        pass

    @abstractmethod
    def setup(self, *args, **kwargs):
        pass

    @abstractmethod
    def run(self, vs_point: vs.Point, *args, **kwargs) -> list[es.Point]:
        pass

    @abstractmethod
    def get_species(self) -> Species:
        pass

    def constrain(self, boatswain: Boatswain) -> Boatswain:
        return boatswain
