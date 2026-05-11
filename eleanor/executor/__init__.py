"""Public surface of the ``eleanor.executor`` extension point.

The registry API (:func:`available_executors`, :func:`get_factory`,
:func:`register_executor`) is re-exported eagerly.

The interface classes (:class:`AbstractExecutor`, :class:`AbstractFuture`) and
the built-in :class:`SerialExecutor` and :class:`MultiprocessingExecutor` are
loaded on demand through :pep:`562`'s ``__getattr__`` hook so importing
:mod:`eleanor.executor` does not eagerly pull in the implementation modules.
A matching ``TYPE_CHECKING`` block keeps static type checkers seeing them as
regular re-exports. Built-in executor factories live in
:mod:`eleanor.executor.factories` and defer their concrete-class imports to
construction time.
"""

from typing import TYPE_CHECKING, cast

from ..exceptions import EleanorException
from ..plugin import is_abstract_instantiation_error, resolve_api_version
from .registry import (
    BUILTIN_EXECUTORS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    ExecutorFactory,
    available_executors,
    get_factory,
    register_executor,
)

if TYPE_CHECKING:
    from .interface import AbstractExecutor as AbstractExecutor
    from .interface import AbstractFuture as AbstractFuture
    from .multiprocessing import MultiprocessingExecutor as MultiprocessingExecutor
    from .serial import SerialExecutor as SerialExecutor


def __getattr__(name: str) -> object:
    if name == "AbstractExecutor":
        from .interface import AbstractExecutor

        return AbstractExecutor
    if name == "AbstractFuture":
        from .interface import AbstractFuture

        return AbstractFuture
    if name == "MultiprocessingExecutor":
        from .multiprocessing import MultiprocessingExecutor

        return MultiprocessingExecutor
    if name == "SerialExecutor":
        from .serial import SerialExecutor

        return SerialExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    "get_factory",
    "load_executor",
    "register_executor",
]


def load_executor(kind: str = "multiprocessing", *, num_workers: int | None = None) -> "AbstractExecutor":
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
    # third-party factories that violate the contract; the ``cast(object, ...)``
    # erases the static type so basedpyright does not flag the check.
    from .interface import AbstractExecutor

    executor_obj = cast(object, executor)
    if not isinstance(executor_obj, AbstractExecutor):
        raise EleanorException(
            f'executor plugin "{kind}" returned {type(executor).__name__}, ' + "expected an AbstractExecutor",
        )
    return executor
