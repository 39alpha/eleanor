from abc import ABC, abstractmethod

from eleanor.constraints import Boatswain
from eleanor.models import ESPoint, VSPoint
from eleanor.typing import Species


class AbstractKernel(ABC):

    @abstractmethod
    def setup(self, *args, **kwargs):
        pass

    @abstractmethod
    def run(self, vs_point: VSPoint, *args, **kwargs) -> list[ESPoint]:
        pass

    @abstractmethod
    def get_species(self) -> Species:
        pass

    def constrain(self, boatswain: Boatswain) -> Boatswain:
        return boatswain
