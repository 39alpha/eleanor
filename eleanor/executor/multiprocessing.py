import os
from collections.abc import Callable
from multiprocessing import Pool
from multiprocessing.pool import ApplyResult, Pool as PoolClass
from typing import TypeVar, override

from eleanor.exceptions import EleanorException

from .interface import AbstractExecutor, AbstractFuture

T = TypeVar('T')


class MultiprocessingFuture(AbstractFuture[T]):
    _future: ApplyResult[T]

    def __init__(self, future: ApplyResult[T]):
        self._future = future

    @override
    def result(self) -> T:
        return self._future.get()


class MultiprocessingExecutor(AbstractExecutor):
    _pool: PoolClass | None
    _num_workers: int

    def __init__(self, num_workers: int | None = None):
        self._pool = Pool(processes=num_workers)
        self._num_workers = num_workers if num_workers is not None else (os.cpu_count() or 1)

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
            raise EleanorException('executor has already been shut down')
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
