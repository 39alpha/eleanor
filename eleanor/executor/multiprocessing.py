import os
from collections.abc import Callable
from multiprocessing import Pool
from multiprocessing.pool import ApplyResult
from multiprocessing.pool import Pool as PoolClass
from typing import Self, TypeVar, override

from eleanor.exceptions import EleanorException

from .interface import AbstractExecutor, AbstractFuture

T = TypeVar("T")


class MultiprocessingFuture(AbstractFuture[T]):
    _future: ApplyResult[T]

    def __init__(self, future: ApplyResult[T]):
        self._future = future

    @override
    def result(self) -> T:
        return self._future.get()

    @override
    def ready(self) -> bool:
        return self._future.ready()


class MultiprocessingExecutor(AbstractExecutor):
    _pool: PoolClass | None
    _num_workers: int

    def __init__(self, num_workers: int | None = None):
        self._pool = None
        self._num_workers = num_workers if num_workers is not None else (os.cpu_count() or 1)

    @override
    def __enter__(self) -> Self:
        self._pool = Pool(processes=self._num_workers)
        return super().__enter__()

    @property
    @override
    def num_workers(self) -> int:
        return self._num_workers

    @override
    def submit(
        self,
        fn: Callable[..., T],
        *args: object,
        **kwargs: object,
    ) -> AbstractFuture[T]:
        if self._pool is None:
            raise EleanorException(
                "executor is not active — enter the executor context before submitting work, or it has already been shut down"
            )
        return MultiprocessingFuture(self._pool.apply_async(fn, args, kwargs))

    @override
    def shutdown(self, wait: bool = True) -> None:
        if self._pool is None:
            return
        if wait:
            self._pool.close()
            self._pool.join()
        else:
            self._pool.terminate()
        self._pool = None
