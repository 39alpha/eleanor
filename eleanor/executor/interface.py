from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator
from types import TracebackType
from typing import Generic, TypeVar

T = TypeVar('T')


class AbstractFuture(ABC, Generic[T]):

    @abstractmethod
    def result(self) -> T: ...


class AbstractExecutor(ABC):
    #: Whether workers launched by this executor can receive a ProgressHandle
    #: and report progress back to the parent process. Backends that run
    #: workers outside the parent's multiprocessing domain (e.g. MPI) should
    #: override this to ``False`` so callers know not to forward
    #: ``multiprocessing.Manager``-backed queues into workers.
    supports_worker_progress: bool = True

    @property
    @abstractmethod
    def num_workers(self) -> int: ...

    @abstractmethod
    def submit(self, fn: Callable[..., T], *args, **kwargs) -> AbstractFuture[T]: ...

    def map(self, fn: Callable[..., T], iterable: Iterable) -> Iterator[T]:
        futures = [self.submit(fn, item) for item in iterable]
        for future in futures:
            yield future.result()

    @abstractmethod
    def shutdown(self, wait: bool = True) -> None: ...

    def __enter__(self):
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ):
        self.shutdown(wait=True)
