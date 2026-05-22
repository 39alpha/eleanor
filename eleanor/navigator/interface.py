from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import eleanor.variable_space as vs
    from eleanor.kernel.interface import AbstractKernel
    from eleanor.order import Order


class AbstractNavigator(ABC):
    @abstractmethod
    def navigate(
        self,
        order: Order,
        kernel: AbstractKernel,
        scale: int,
        batch_size: int,
        *args: object,
        order_id: int | None = None,
        **kwargs: object,
    ) -> Iterator[list[vs.Point]]:
        pass

    def num_systems(self, order: Order, scale: int) -> int:
        _ = order
        return scale


__all__ = ["AbstractNavigator"]
