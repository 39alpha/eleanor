from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Unpack

    import numpy as np

    import eleanor.equilibrium_space as es
    import eleanor.variable_space as vs
    from eleanor.constraints.point_builder import PointBuilder
    from eleanor.order import Order
    from eleanor.typing import EleanorKwargs, StrPath


class AbstractKernel(ABC):
    def prepare_setup_args(self, *args: object) -> dict[str, object]:
        _ = args
        return {}

    @abstractmethod
    def setup(self, order: Order, **kwargs: object) -> None:
        pass

    @abstractmethod
    def run(self, vs_point: vs.Point, *args: object, **kwargs: Unpack[EleanorKwargs]) -> list[es.Point]:
        pass

    def validate_order(self, order: Order) -> None:
        _ = order

    def is_soft_exit(self, code: int) -> bool:
        return code == 0

    def constrain(self, point_builder: PointBuilder) -> PointBuilder:
        return point_builder

    def copy_data(self, vs_point: vs.Point, *args: object, dir: StrPath = ".", **kwargs: Unpack[EleanorKwargs]) -> None:
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


__all__ = ["AbstractKernel"]
