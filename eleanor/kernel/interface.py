from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.typing import EleanorKwargs, Unpack

if TYPE_CHECKING:
    from eleanor.order import Order


class AbstractKernel(ABC):
    @abstractmethod
    def setup(
        self,
        order: "Order | None" = None,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> None:
        pass

    @abstractmethod
    def run(
        self,
        vs_point: vs.Point,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[es.Point]:
        pass

    def validate_order(self, order: "Order") -> None:
        _ = order

    def is_soft_exit(self, code: int) -> bool:
        return code in [0]

    def constrain(self, boatswain: Boatswain) -> Boatswain:
        return boatswain

    def copy_data(self, vs_point: vs.Point, *args: object, dir: str = ".", **kwargs: Unpack[EleanorKwargs]) -> None:
        _ = vs_point
        _ = args
        _ = dir
        _ = kwargs

    def get_atomic_weight(self, element: str) -> np.float64 | None:
        _ = element
        return None

    def get_molar_mass(
        self,
        species_name: str,
        mole_fractions: dict[str, np.float64] | None = None,
    ) -> np.float64 | None:
        _ = species_name
        _ = mole_fractions
        return None
