from collections.abc import Iterator
from itertools import batched
from typing import override

import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.exceptions import EleanorException
from eleanor.navigator.interface import AbstractNavigator
from eleanor.typing import Callable, cast


class Random(AbstractNavigator):
    @override
    def navigate(self, scale: int, batch_size: int, *args: object, **kwargs: object) -> Iterator[list[vs.Point]]:
        generate = cast(Callable[..., vs.Point], self.generate)
        for batch in batched((generate(*args, **kwargs) for _ in range(scale)), batch_size):
            yield list(batch)

    def generate(self, *_args: object, order_id: int | None = None, **kwargs: object) -> vs.Point:
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
                boatswain = Boatswain(self.order)
                _ = self.kernel.constrain(boatswain)

                parameters = boatswain.constrain()
                while parameters:
                    for parameter in parameters:
                        boatswain[parameter] = boatswain[parameter].random()[0]
                    parameters = boatswain.constrain()

                return boatswain.generate_vs(order_id)
            except Exception as e:
                last_exception = e
                max_attempts -= 1

        msg = "failed to select VS point"
        raise EleanorException(msg) from last_exception


_ = AbstractNavigator.register(Random)

__all__ = ["Random"]
