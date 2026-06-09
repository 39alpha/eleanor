from typing import Callable, override

import pytest
from eleanor.exceptions import EleanorException
from eleanor.executor import load_executor
from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.registry import available_executors
from eleanor.executor.settings import ExecutorSettings


class Future(AbstractFuture[object]):
    _value: object

    def __init__(self, value: object) -> None:
        self._value = value

    @override
    def result(self) -> object:
        return self._value


class Executor(AbstractExecutor):
    shutdown_calls: int

    def __init__(self) -> None:
        self.shutdown_calls = 0

    @property
    @override
    def num_workers(self) -> int:
        return 2

    @override
    def submit(
        self, fn: Callable[..., object], *args: object, **kwargs: object
    ) -> AbstractFuture[object]:
        return Future(fn(*args, **kwargs))

    @override
    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_calls += 1


def test_context_manager_calls_shutdown() -> None:
    executor = Executor()
    with executor as active:
        assert active is executor
    assert executor.shutdown_calls == 1


def test_load_executor_rejects_unknown_executor() -> None:
    with pytest.raises(EleanorException, match="executor is not supported"):
        _ = load_executor(kind="bad-backend", settings=ExecutorSettings())


def test_load_executor_registry_contains_builtins() -> None:
    live = available_executors()

    # The two built-ins must always be present; plugins (e.g. eleanor_mpi)
    # may add more.
    assert "serial" in live
    assert "multiprocessing" in live
    assert "bad-backend" not in live


def test_abstract_executor_default_supports_worker_progress() -> None:
    executor = Executor()
    assert executor.supports_worker_progress
