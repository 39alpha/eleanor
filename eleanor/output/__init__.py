"""Public surface of the ``eleanor.output`` extension point.

The registry API (:func:`available_outputs`, :func:`get_factory`,
:func:`register_output`) is re-exported eagerly.

The interface dataclasses (:class:`OutputSink`, :class:`ComputeResult`,
:class:`ErrorInfo`, :class:`WriteOutcome`, :class:`RunStats`) and the
built-in :class:`PostgresSink` are loaded on demand through :pep:`562`'s
``__getattr__`` hook so importing :mod:`eleanor.output` does not pull in
psycopg or the schema/converters/queries graph until a caller actually
touches one of those names. A matching ``TYPE_CHECKING`` block keeps
static type checkers seeing them as regular re-exports.

The built-in ``postgres`` output factory is defined here and registered at
module import time; the heavy :mod:`eleanor.output.postgres` import is
deferred inside the factory callable so it only occurs when the factory is
actually called.
"""

import warnings
from typing import TYPE_CHECKING

from ..exceptions import EleanorException
from ..plugin import is_abstract_instantiation_error, resolve_api_version
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
    from typing import Protocol

    class _OutputConfig(Protocol):
        @property
        def type(self) -> str: ...

        @property
        def args(self) -> dict[str, object]: ...

    class _LoaderConfig(Protocol):
        @property
        def output(self) -> _OutputConfig: ...

    from .csv import CsvSink as CsvSink
    from .interface import ComputeResult as ComputeResult
    from .interface import ErrorInfo as ErrorInfo
    from .interface import OutputSink as OutputSink
    from .interface import RunStats as RunStats
    from .interface import WriteOutcome as WriteOutcome
    from .memory import MemorySink as MemorySink
    from .null import NullSink as NullSink
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
    if name == "CsvSink":
        from .csv import CsvSink

        return CsvSink
    if name == "MemorySink":
        from .memory import MemorySink

        return MemorySink
    if name == "NullSink":
        from .null import NullSink

        return NullSink
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_KNOWN_CSV_ARGS: frozenset[str] = frozenset({"filename", "query"})
_KNOWN_MEMORY_ARGS: frozenset[str] = frozenset()
_KNOWN_NULL_ARGS: frozenset[str] = frozenset({"support_worker_writes"})
_KNOWN_POSTGRES_ARGS: frozenset[str] = frozenset({"database", "bulk_load_optimization"})


def _build_csv(_config: object, *, verbose: bool = False, **args: object) -> "CsvSink":
    # ``verbose`` is accepted for parity with the other built-in factories but
    # the CSV sink has no verbose-only behaviour; ignore it deliberately.
    _ = verbose
    unknown = sorted(k for k in args if k not in _KNOWN_CSV_ARGS)
    if unknown:
        warnings.warn(
            'built-in output sink "csv" does not accept these keyword arguments; ' + f"ignoring: {unknown}",
            RuntimeWarning,
            stacklevel=2,
        )

    from .csv import CsvConfig, CsvSink

    return CsvSink(
        CsvConfig(
            filename=args.get("filename"),
            query=args.get("query"),
        )
    )


def _build_memory(_config: object, *, verbose: bool = False, **args: object) -> "MemorySink":
    # ``verbose`` is accepted for parity with the other built-in factories but
    # the memory sink has no verbose-only behaviour; ignore it deliberately.
    _ = verbose
    unknown = sorted(k for k in args if k not in _KNOWN_MEMORY_ARGS)
    if unknown:
        warnings.warn(
            'built-in output sink "memory" does not accept these keyword arguments; ' + f"ignoring: {unknown}",
            RuntimeWarning,
            stacklevel=2,
        )

    from .memory import MemorySink

    return MemorySink()


def _build_null(_config: object, *, verbose: bool = False, **args: object) -> "NullSink":
    # ``verbose`` is accepted for parity with the other built-in factories but
    # the Null sink has no verbose-only behaviour; ignore it deliberately.
    _ = verbose
    unknown = sorted(k for k in args if k not in _KNOWN_NULL_ARGS)
    if unknown:
        warnings.warn(
            'built-in output sink "null" does not accept these keyword arguments; ' + f"ignoring: {unknown}",
            RuntimeWarning,
            stacklevel=2,
        )

    from .null import NullConfig, NullSink

    return NullSink(NullConfig(support_worker_writes=args.get("support_worker_writes", False)))


def _build_postgres(_config: object, *, verbose: bool = False, **args: object) -> "PostgresSink":
    unknown = sorted(k for k in args if k not in _KNOWN_POSTGRES_ARGS)
    if unknown:
        warnings.warn(
            'built-in output sink "postgres" does not accept these keyword arguments; ' + f"ignoring: {unknown}",
            RuntimeWarning,
            stacklevel=2,
        )

    from ..typing import cast
    from .postgres import PostgresSink
    from .postgres.config import DatabaseConfig, DatabaseRaw

    # The registry splats config.output.args as kwargs, so the 'database' kwarg
    # IS the raw database block from the config file. Use it directly rather than
    # re-traversing config.raw, which keeps the factory self-consistent even if
    # the caller mutates config.output.args without touching config.raw.
    database_raw = args.get("database")
    db_config = (
        DatabaseConfig.from_raw(cast(DatabaseRaw, cast(object, database_raw)))
        if isinstance(database_raw, dict)
        else DatabaseConfig()
    )
    # ``bulk_load_optimization`` is a sink-behaviour knob (a sibling of
    # ``database`` in ``output.args``), not a connection setting, so it
    # threads straight onto :class:`PostgresSink` rather than into the
    # frozen :class:`DatabaseConfig` (which is hashable and used as a
    # connection-cache key).
    bulk_load_optimization = bool(args.get("bulk_load_optimization", False))
    return PostgresSink(
        db_config,
        verbose=verbose,
        bulk_load_optimization=bulk_load_optimization,
    )


_build_csv.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
_build_memory.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
_build_null.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
_build_postgres.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]


register_output("csv", _build_csv)
register_output("null", _build_null)
register_output("postgres", _build_postgres)
register_output("memory", _build_memory)


def load_output_sink(config: "_LoaderConfig", verbose: bool = False) -> "OutputSink":
    factory = get_factory(config.output.type)
    version = resolve_api_version(factory)
    try:
        built = factory(config, verbose=verbose, **config.output.args)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        raise EleanorException(
            f'output sink plugin "{config.output.type}" failed to instantiate{version_suffix}: {e}',
        ) from e

    from .interface import OutputSink

    if not isinstance(built, OutputSink):
        raise EleanorException(
            f'output sink plugin "{config.output.type}" returned ' + f"{type(built).__name__}, expected an OutputSink",
        )
    return built


__all__ = [
    "BUILTIN_OUTPUTS",
    "CsvSink",
    "ComputeResult",
    "ENTRY_POINT_GROUP",
    "ErrorInfo",
    "MemorySink",
    "NullSink",
    "OVERRIDE_ENV_VAR",
    "OutputFactory",
    "OutputSink",
    "PostgresSink",
    "RunStats",
    "WriteOutcome",
    "available_outputs",
    "get_factory",
    "load_output_sink",
    "register_output",
]
