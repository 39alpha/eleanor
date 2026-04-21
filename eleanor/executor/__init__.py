from .interface import AbstractExecutor, AbstractFuture
from .multiprocessing import MultiprocessingExecutor
from .registry import (
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    ExecutorFactory,
    available_backends,
    get_factory,
    register_backend,
)
from .serial import SerialExecutor

__all__ = [
    'AbstractExecutor',
    'AbstractFuture',
    'ENTRY_POINT_GROUP',
    'ExecutorFactory',
    'MultiprocessingExecutor',
    'OVERRIDE_ENV_VAR',
    'SerialExecutor',
    'available_backends',
    'build_executor',
    'register_backend',
]


def build_executor(kind: str = 'multiprocessing', *, num_workers: int | None = None) -> AbstractExecutor:
    """Construct an :class:`AbstractExecutor` for the given backend name.

    :param kind: the backend name. Must be one of :func:`available_backends`,
        which includes the built-in backends (``serial``, ``multiprocessing``)
        and any third-party backends discovered via the
        :data:`ENTRY_POINT_GROUP` entry-point group.
    :param num_workers: the requested worker count. Backends are free to
        normalize or ignore this value; see the individual backend classes.
    """
    factory = get_factory(kind)
    return factory(num_workers)
