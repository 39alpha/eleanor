from collections.abc import Iterator
from itertools import batched
from typing import TYPE_CHECKING, Protocol, cast, override

import eleanor.variable_space as vs
from eleanor.constraints.point_builder import PointBuilder
from eleanor.exceptions import EleanorException
from eleanor.navigator.interface import AbstractNavigator

if TYPE_CHECKING:
    from eleanor.kernel import AbstractKernel
    from eleanor.order import Order


class PointGenerator(Protocol):
    def __call__(
        self,
        order: Order,
        kernel: AbstractKernel,
        *_args: object,
        order_id: int | None = None,
        **kwargs: object,
    ) -> vs.Point: ...


class RandomNavigator(AbstractNavigator):
    @override
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
        generate = cast(PointGenerator, self.generate)
        for batch in batched(
            (generate(order, kernel, *args, order_id=order_id, **kwargs) for _ in range(scale)),
            batch_size,
            strict=False,
        ):
            yield list(batch)

    def generate(
        self,
        order: Order,
        kernel: AbstractKernel,
        *_args: object,
        order_id: int | None = None,
        **kwargs: object,
    ) -> vs.Point:
        max_attempts: object = kwargs.get("max_attempts", 1)
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
            msg = f"max_attempts must be an integer, got {type(max_attempts).__name__}"
            raise EleanorException(msg)
        elif max_attempts < 1:
            msg = f"max_attempts must be at least one, got {max_attempts}"
            raise EleanorException(msg)

        last_exception: Exception | None = None
        while max_attempts > 0:
            try:
                point_builder = PointBuilder(order)
                _ = kernel.constrain(point_builder)

                parameters = point_builder.constrain()
                while parameters:
                    for parameter in parameters:
                        point_builder[parameter] = point_builder[parameter].random()[0]
                    parameters = point_builder.constrain()

                return point_builder.generate_vs(order_id if order_id is not None else order.id)
            except Exception as e:
                last_exception = e
                max_attempts -= 1

        msg = "failed to select VS point"
        raise EleanorException(msg) from last_exception


_ = AbstractNavigator.register(RandomNavigator)

__all__ = ["RandomNavigator"]
