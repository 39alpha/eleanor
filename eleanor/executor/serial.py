import warnings
from collections.abc import Callable
from typing import TypeVar, override

from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.settings import Settings

T = TypeVar("T")


class Future(AbstractFuture[T]):
    _value: T

    def __init__(self, value: T):
        self._value = value

    @override
    def result(self) -> T:
        return self._value


class Executor(AbstractExecutor):
    def __init__(self, settings: Settings):
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
        return Future(fn(*args, **kwargs))

    @override
    def shutdown(self, wait: bool = True) -> None:
        _ = wait
        pass


__all__ = [
    "Executor",
    "Future",
]
