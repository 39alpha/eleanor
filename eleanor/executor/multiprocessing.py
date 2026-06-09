import os
import signal
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor
from concurrent.futures import wait as futures_wait
from typing import Self, TypeVar, override

from eleanor.exceptions import EleanorException
from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.settings import ExecutorSettings

T = TypeVar("T")


def _ignore_sigint() -> None:
    _ = signal.signal(signal.SIGINT, signal.SIG_IGN)


class MultiprocessingFuture(AbstractFuture[T]):
    _future: Future[T]

    def __init__(self, future: Future[T]) -> None:
        self._future = future

    @override
    def result(self) -> T:
        return self._future.result()

    @override
    def ready(self) -> bool:
        return self._future.done()

    @property
    def inner(self) -> Future[T]:
        return self._future


class MultiprocessingExecutor(AbstractExecutor):
    _pool: ProcessPoolExecutor | None
    _num_workers: int

    def __init__(self, settings: ExecutorSettings) -> None:
        self._pool = None
        self._num_workers = settings.num_workers if settings.num_workers is not None else (os.cpu_count() or 1)

    @override
    def __enter__(self) -> Self:
        self._pool = ProcessPoolExecutor(max_workers=self._num_workers, initializer=_ignore_sigint)
        return super().__enter__()

    @property
    @override
    def num_workers(self) -> int:
        return self._num_workers

    @override
    def submit(self, fn: Callable[..., T], *args: object, **kwargs: object) -> AbstractFuture[T]:
        if self._pool is None:
            msg = "executor is not active — enter the executor context before submitting work, or it has already been shut down"
            raise EleanorException(msg)
        return MultiprocessingFuture(self._pool.submit(fn, *args, **kwargs))

    @override
    def pop_completed_future(self, futures: list[AbstractFuture[T]]) -> AbstractFuture[T]:
        typed_futures = [future for future in futures if isinstance(future, MultiprocessingFuture)]
        if len(typed_futures) != len(futures):
            return super().pop_completed_future(futures)

        done, _ = futures_wait([future.inner for future in typed_futures], return_when=FIRST_COMPLETED)
        for idx, candidate in enumerate(futures):
            if isinstance(candidate, MultiprocessingFuture) and candidate.inner in done:
                return futures.pop(idx)
        msg = "failed to identify a completed future"
        raise EleanorException(msg)

    @override
    def shutdown(self, wait: bool = True) -> None:
        if self._pool is None:
            return
        if not wait:
            for process in self._pool._processes.values():
                process.terminate()
        self._pool.shutdown(wait=wait, cancel_futures=not wait)
        self._pool = None


__all__ = [
    "MultiprocessingExecutor",
    "MultiprocessingFuture",
]
