"""Built-in output-sink factories used by entry-point discovery."""

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .csv import CsvSink
    from .memory import MemorySink
    from .null import NullSink
    from .postgres import PostgresSink

KNOWN_CSV_ARGS: frozenset[str] = frozenset({"filename", "query"})
KNOWN_MEMORY_ARGS: frozenset[str] = frozenset({"support_worker_writes"})
KNOWN_NULL_ARGS: frozenset[str] = frozenset({"support_worker_writes"})
KNOWN_POSTGRES_ARGS: frozenset[str] = frozenset({"database", "bulk_load_optimization"})


def build_csv(_config: object, *, verbose: bool = False, **args: object) -> "CsvSink":
    # ``verbose`` is accepted for parity with the other built-in factories but
    # the CSV sink has no verbose-only behaviour; ignore it deliberately.
    _ = verbose
    unknown = sorted(k for k in args if k not in KNOWN_CSV_ARGS)
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


def build_memory(_config: object, *, verbose: bool = False, **args: object) -> "MemorySink":
    # ``verbose`` is accepted for parity with the other built-in factories but
    # the memory sink has no verbose-only behaviour; ignore it deliberately.
    _ = verbose
    unknown = sorted(k for k in args if k not in KNOWN_MEMORY_ARGS)
    if unknown:
        warnings.warn(
            'built-in output sink "memory" does not accept these keyword arguments; ' + f"ignoring: {unknown}",
            RuntimeWarning,
            stacklevel=2,
        )

    from .memory import MemoryConfig, MemorySink

    return MemorySink(MemoryConfig(support_worker_writes=args.get("support_worker_writes", False)))


def build_null(_config: object, *, verbose: bool = False, **args: object) -> "NullSink":
    # ``verbose`` is accepted for parity with the other built-in factories but
    # the Null sink has no verbose-only behaviour; ignore it deliberately.
    _ = verbose
    unknown = sorted(k for k in args if k not in KNOWN_NULL_ARGS)
    if unknown:
        warnings.warn(
            'built-in output sink "null" does not accept these keyword arguments; ' + f"ignoring: {unknown}",
            RuntimeWarning,
            stacklevel=2,
        )

    from .null import NullConfig, NullSink

    return NullSink(NullConfig(support_worker_writes=args.get("support_worker_writes", False)))


def build_postgres(_config: object, *, verbose: bool = False, **args: object) -> "PostgresSink":
    unknown = sorted(k for k in args if k not in KNOWN_POSTGRES_ARGS)
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


build_csv.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_memory.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_null.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_postgres.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
