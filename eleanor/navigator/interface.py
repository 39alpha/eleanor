from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import numpy as np

from eleanor.exceptions import EleanorError
from eleanor.util import guard_is_float, guard_is_int

if TYPE_CHECKING:
    from collections.abc import Iterator

    import eleanor.variable_space as vs
    from eleanor.kernel.interface import AbstractKernel
    from eleanor.order import Order


class SimulationSize(Protocol):
    def num_systems(self, order: Order) -> int: ...


@dataclass(init=False, frozen=True)
class SystemCount(SimulationSize):
    count: int

    def __init__(self, count: int) -> None:
        guard_is_int(count, "count")
        if count <= 0:
            msg = "count must be positive, non-zero"
            raise EleanorError(msg)
        object.__setattr__(self, "count", count)

    def num_systems(self, order: Order) -> int:
        _ = order
        return self.count


@dataclass(init=False, frozen=True)
class SampleDensity(SimulationSize):
    density: float

    def __init__(self, density: float) -> None:
        guard_is_float(density, "density")
        if not np.isfinite(density):
            msg = "density must be finite"
            raise EleanorError(msg)

        if density <= 0.0:
            msg = "density must be positive, non-zero"
            raise EleanorError(msg)
        object.__setattr__(self, "density", density)

    def num_systems(self, order: Order) -> int:
        return max(1, round(self.density * order.volume()))


class AbstractNavigator(ABC):
    @abstractmethod
    def navigate(
        self,
        order: Order,
        kernel: AbstractKernel,
        simulation_size: SimulationSize,
        batch_size: int,
        *args: object,
        **kwargs: object,
    ) -> Iterator[list[vs.Point]]:
        pass

    def num_systems(self, order: Order, simulation_size: SimulationSize) -> int:
        return simulation_size.num_systems(order)


__all__ = [
    "AbstractNavigator",
    "SampleDensity",
    "SimulationSize",
    "SystemCount",
]
