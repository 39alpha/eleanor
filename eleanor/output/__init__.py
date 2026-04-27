"""Public surface of the ``eleanor.output`` extension point.

The registry API (:func:`available_outputs`, :func:`get_factory`,
:func:`register_output`) is re-exported eagerly.

The interface dataclasses (:class:`OutputSink`, :class:`ComputeResult`,
:class:`ErrorInfo`, :class:`WriteOutcome`, :class:`RunStats`) and the
built-in :class:`PostgresSink` transitively pull in SQLAlchemy ORM models
and are therefore loaded on demand through :pep:`562`'s ``__getattr__``
hook, with a matching ``TYPE_CHECKING`` block so static type checkers see
them as regular re-exports.

The built-in ``postgres`` output factory is defined here and registered at
module import time; the heavy :mod:`eleanor.output.postgres` import is
deferred inside the factory callable so it only occurs when the factory is
actually called.
"""

import warnings
from typing import TYPE_CHECKING

from ..exceptions import EleanorException
from .registry import (
    BUILTIN_OUTPUTS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    OutputFactory,
    available_outputs,
    get_factory,
    register_output,
)

if TYPE_CHECKING:
    from .interface import ComputeResult as ComputeResult
    from .interface import ErrorInfo as ErrorInfo
    from .interface import OutputSink as OutputSink
    from .interface import RunStats as RunStats
    from .interface import WriteOutcome as WriteOutcome
    from .postgres import PostgresSink as PostgresSink


def __getattr__(name: str) -> object:
    if name == "ComputeResult":
        from .interface import ComputeResult

        return ComputeResult
    if name == "ErrorInfo":
        from .interface import ErrorInfo

        return ErrorInfo
    if name == "OutputSink":
        from .interface import OutputSink

        return OutputSink
    if name == "RunStats":
        from .interface import RunStats

        return RunStats
    if name == "WriteOutcome":
        from .interface import WriteOutcome

        return WriteOutcome
    if name == "PostgresSink":
        from .postgres import PostgresSink

        return PostgresSink
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _build_postgres(config: object, *, verbose: bool = False, **args: object) -> "PostgresSink":
    database = getattr(config, "database", None)
    if database is None:
        raise EleanorException("postgres output sink requires config.database")
    if args:
        warnings.warn(
            'built-in output sink "postgres" does not accept keyword arguments; ' + f"ignoring: {list(args)}",
            RuntimeWarning,
            stacklevel=2,
        )
    from ..connection import DatabaseConfig
    from .postgres import PostgresSink

    if not isinstance(database, DatabaseConfig):
        raise EleanorException("postgres output sink requires a DatabaseConfig")
    return PostgresSink(database, verbose=verbose)


register_output("postgres", _build_postgres)

__all__ = [
    "BUILTIN_OUTPUTS",
    "ComputeResult",
    "ENTRY_POINT_GROUP",
    "ErrorInfo",
    "OVERRIDE_ENV_VAR",
    "OutputFactory",
    "OutputSink",
    "PostgresSink",
    "RunStats",
    "WriteOutcome",
    "available_outputs",
    "get_factory",
    "register_output",
]
