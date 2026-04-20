from collections.abc import Callable
from typing import TypeVar

from .interface import AbstractExecutor, AbstractFuture

T = TypeVar('T')


class SerialFuture(AbstractFuture[T]):
    _value: T

    def __init__(self, value: T):
        self._value = value

    def result(self) -> T:
        return self._value


class SerialExecutor(AbstractExecutor):
    @property
    def num_workers(self) -> int:
        return 1

    def submit(self, fn: Callable[..., T], *args, **kwargs) -> AbstractFuture[T]:
        return SerialFuture(fn(*args, **kwargs))

    def shutdown(self, wait: bool = True) -> None:
        pass
