from abc import ABC, abstractmethod
from dataclasses import dataclass

from eleanor.typing import Self, Species


@dataclass
class Config(object):
    type: str

    @property
    def is_fully_specified(self) -> bool:
        return True

    def mean(self) -> Self:
        return self


class AbstractKernel(ABC):

    @abstractmethod
    def setup(self, *args, **kwargs):
        pass

    @abstractmethod
    def prime(self, *args, **kwargs) -> Species:
        pass

    @abstractmethod
    def get_species(self) -> Species:
        pass
