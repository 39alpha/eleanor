import warnings
from collections.abc import Callable
from typing import TypeVar, override

from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.settings import ExecutorSettings

T = TypeVar("T")


class SerialFuture(AbstractFuture[T]):
    _value: T

    def __init__(self, value: T) -> None:
        self._value = value

    @override
    def result(self) -> T:
        return self._value


class SerialExecutor(AbstractExecutor):
    def __init__(self, settings: ExecutorSettings) -> None:
        if settings.num_workers is not None and settings.num_workers != 1:
            warnings.warn(
                f"serial executor does not support multiple workers; ignoring num_workers={settings.num_workers}"
            )

    @property
    @override
    def num_workers(self) -> int:
        return 1

    @override
    def submit(self, fn: Callable[..., T], *args: object, **kwargs: object) -> AbstractFuture[T]:
        return SerialFuture(fn(*args, **kwargs))

    @override
    def shutdown(self, wait: bool = True) -> None:
        _ = wait
        pass


__all__ = [
    "SerialExecutor",
    "SerialFuture",
]
