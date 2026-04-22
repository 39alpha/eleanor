from collections.abc import Callable
from typing import TypeVar, override

from .interface import AbstractExecutor, AbstractFuture

T = TypeVar('T')


class SerialFuture(AbstractFuture[T]):
    _value: T

    def __init__(self, value: T):
        self._value = value

    @override
    def result(self) -> T:
        return self._value


class SerialExecutor(AbstractExecutor):
    @property
    @override
    def num_workers(self) -> int:
        return 1

    @override
    def submit(
        self,
        fn: Callable[..., T],
        *args: object,
        **kwargs: object,
    ) -> AbstractFuture[T]:
        return SerialFuture(fn(*args, **kwargs))

    @override
    def shutdown(self, wait: bool = True) -> None:
        _ = wait
        pass
