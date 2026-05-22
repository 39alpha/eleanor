from typing import cast

from eleanor.exceptions import EleanorException
from eleanor.executor.interface import AbstractExecutor, AbstractFuture
from eleanor.executor.registry import get_factory
from eleanor.plugin import is_abstract_instantiation_error, resolve_api_version


def load_executor(kind: str = "multiprocessing", *, num_workers: int | None = None) -> AbstractExecutor:
    factory = get_factory(kind)
    version = resolve_api_version(factory)
    try:
        executor = factory(num_workers)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        msg = f"executor plugin {kind!r} failed to instantiate{version_suffix}: {e}"
        raise EleanorException(msg) from e

    if not isinstance(cast(object, executor), AbstractExecutor):
        msg = f"executor plugin {kind!r} returned {type(executor).__name__}, expected an AbstractExecutor"
        raise EleanorException(msg)

    return executor


__all__ = [
    "AbstractExecutor",
    "AbstractFuture",
    "load_executor",
]
