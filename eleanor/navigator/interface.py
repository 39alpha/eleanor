from abc import ABC, abstractmethod
from collections.abc import Iterator

import eleanor.variable_space as vs

from ..kernel.interface import AbstractKernel
from ..order import Order


class AbstractNavigator(ABC):
    order: Order
    kernel: AbstractKernel

    def __init__(self, order: Order, kernel: AbstractKernel):
        self.order = order
        self.kernel = kernel

    @abstractmethod
    def navigate(self, scale: int, batch_size: int, *args: object, **kwargs: object) -> Iterator[list[vs.Point]]:
        pass

    def num_systems(self, scale: int) -> int:
        return scale
