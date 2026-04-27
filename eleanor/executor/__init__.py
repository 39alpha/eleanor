import warnings

from ..exceptions import EleanorException
from ..plugin import is_abstract_instantiation_error, resolve_api_version
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
    "AbstractExecutor",
    "AbstractFuture",
    "BUILTIN_EXECUTORS",
    "ENTRY_POINT_GROUP",
    "ExecutorFactory",
    "MultiprocessingExecutor",
    "OVERRIDE_ENV_VAR",
    "SerialExecutor",
    "available_executors",
    "build_executor",
    "get_factory",
    "register_executor",
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
            "num_workers is ignored for serial executor",
            RuntimeWarning,
            stacklevel=3,
        )
    return SerialExecutor()


def _build_multiprocessing(num_workers: int | None) -> AbstractExecutor:
    return MultiprocessingExecutor(num_workers=_normalize_num_workers(num_workers))


_build_serial.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
_build_multiprocessing.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]

register_executor("serial", _build_serial)
register_executor("multiprocessing", _build_multiprocessing)


def build_executor(kind: str = "multiprocessing", *, num_workers: int | None = None) -> AbstractExecutor:
    """Construct an :class:`AbstractExecutor` for the given executor name.

    :param kind: the executor name. Must be one of :func:`available_executors`,
        which includes the built-in executors (``serial``, ``multiprocessing``)
        and any third-party executors discovered via the
        :data:`ENTRY_POINT_GROUP` entry-point group.
    :param num_workers: the requested worker count. Executors are free to
        normalize or ignore this value; see the individual executor classes.
    """
    factory = get_factory(kind)
    version = resolve_api_version(factory)
    try:
        executor = factory(num_workers)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        raise EleanorException(
            f'executor plugin "{kind}" failed to instantiate{version_suffix}: {e}',
        ) from e
    # ``ExecutorFactory`` declares the return type as ``AbstractExecutor``, but
    # entry-point-loaded plugins reach the registry as ``object`` and are cast
    # without runtime validation. The ``isinstance`` guard is a backstop for
    # third-party factories that violate the contract; basedpyright cannot see
    # past the static type, so the redundancy warning is suppressed.
    if not isinstance(executor, AbstractExecutor):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise EleanorException(
            f'executor plugin "{kind}" returned {type(executor).__name__}, ' + "expected an AbstractExecutor",
        )
    return executor
