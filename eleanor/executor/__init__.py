import warnings

from .interface import AbstractExecutor, AbstractFuture
from .multiprocessing import MultiprocessingExecutor
from .registry import (
    BUILTIN_EXECUTORS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    ExecutorFactory,
    available_executors,
    get_factory,
    register_executor,
)
from .serial import SerialExecutor

__all__ = [
    'AbstractExecutor',
    'AbstractFuture',
    'BUILTIN_EXECUTORS',
    'ENTRY_POINT_GROUP',
    'ExecutorFactory',
    'MultiprocessingExecutor',
    'OVERRIDE_ENV_VAR',
    'SerialExecutor',
    'available_executors',
    'build_executor',
    'get_factory',
    'register_executor',
]


def _normalize_num_workers(num_workers: int | None) -> int | None:
    """Clamp ``num_workers`` to ``>= 1``, preserving ``None`` as the default sentinel."""
    if num_workers is None:
        return None
    if num_workers <= 0:
        return 1
    return num_workers


def _build_serial(num_workers: int | None) -> AbstractExecutor:
    if num_workers is not None:
        warnings.warn(
            'num_workers is ignored for serial executor',
            RuntimeWarning,
            stacklevel=3,
        )
    return SerialExecutor()


def _build_multiprocessing(num_workers: int | None) -> AbstractExecutor:
    return MultiprocessingExecutor(num_workers=_normalize_num_workers(num_workers))


register_executor('serial', _build_serial)
register_executor('multiprocessing', _build_multiprocessing)


def build_executor(kind: str = 'multiprocessing', *, num_workers: int | None = None) -> AbstractExecutor:
    """Construct an :class:`AbstractExecutor` for the given executor name.

    :param kind: the executor name. Must be one of :func:`available_executors`,
        which includes the built-in executors (``serial``, ``multiprocessing``)
        and any third-party executors discovered via the
        :data:`ENTRY_POINT_GROUP` entry-point group.
    :param num_workers: the requested worker count. Executors are free to
        normalize or ignore this value; see the individual executor classes.
    """
    factory = get_factory(kind)
    return factory(num_workers)
