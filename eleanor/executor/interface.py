import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType
from typing import Self, TypeVar

from eleanor.exceptions import EleanorError

T = TypeVar("T")


class AbstractFuture[T](ABC):
    @abstractmethod
    def result(self) -> T: ...

    def ready(self) -> bool:
        return True


class AbstractExecutor(ABC):
    supports_worker_progress: bool = True

    @property
    @abstractmethod
    def num_workers(self) -> int: ...

    @abstractmethod
    def submit(self, fn: Callable[..., T], *args: object, **kwargs: object) -> AbstractFuture[T]: ...

    def pop_completed_future(self, futures: list[AbstractFuture[T]]) -> AbstractFuture[T]:
        """Pop one future from ``futures`` in the backend's preferred completion order.

        Backends with non-blocking completion introspection may override this to
        pop whichever future has already completed.
        """
        if len(futures) == 0:
            msg = "cannot pop a completed future from an empty list"
            raise EleanorError(msg)

        delay = 0.001
        while True:
            for idx, candidate in enumerate(futures):
                if candidate.ready():
                    return futures.pop(idx)
            time.sleep(delay)
            delay = min(delay * 2, 0.128)

    @abstractmethod
    def shutdown(self, wait: bool = True) -> None: ...

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        wait = _exc_type is None or not issubclass(_exc_type, KeyboardInterrupt)
        self.shutdown(wait=wait)


__all__ = [
    "AbstractExecutor",
    "AbstractFuture",
]
