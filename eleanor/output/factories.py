import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eleanor.output.csv import CsvSink
    from eleanor.output.memory import MemorySink
    from eleanor.output.null import NullSink
    from eleanor.output.postgres import PostgresSink

KNOWN_CSV_ARGS: frozenset[str] = frozenset({"filename", "query"})
KNOWN_MEMORY_ARGS: frozenset[str] = frozenset({"support_worker_writes"})
KNOWN_NULL_ARGS: frozenset[str] = frozenset({"support_worker_writes"})
KNOWN_POSTGRES_ARGS: frozenset[str] = frozenset({"database", "bulk_load_optimization"})


def build_csv(*, verbose: bool = False, **args: object) -> CsvSink:
    _ = verbose
    unknown = sorted(k for k in args if k not in KNOWN_CSV_ARGS)
    if unknown:
        warnings.warn(
            f'built-in output sink "csv" does not accept these keyword arguments; ignoring: {unknown}',
            RuntimeWarning,
            stacklevel=2,
        )

    from eleanor.output.csv import CsvConfig, CsvSink

    return CsvSink(
        CsvConfig(
            filename=args.get("filename"),
            query=args.get("query"),
        )
    )


def build_memory(*, verbose: bool = False, **args: object) -> MemorySink:
    _ = verbose
    unknown = sorted(k for k in args if k not in KNOWN_MEMORY_ARGS)
    if unknown:
        warnings.warn(
            f'built-in output sink "memory" does not accept these keyword arguments; ignoring: {unknown}',
            RuntimeWarning,
            stacklevel=2,
        )

    from eleanor.output.memory import MemoryConfig, MemorySink

    return MemorySink(MemoryConfig(support_worker_writes=args.get("support_worker_writes", False)))


def build_null(*, verbose: bool = False, **args: object) -> NullSink:
    _ = verbose
    unknown = sorted(k for k in args if k not in KNOWN_NULL_ARGS)
    if unknown:
        warnings.warn(
            f'built-in output sink "null" does not accept these keyword arguments; ignoring: {unknown}',
            RuntimeWarning,
            stacklevel=2,
        )

    from eleanor.output.null import NullConfig, NullSink

    return NullSink(NullConfig(support_worker_writes=args.get("support_worker_writes", False)))


def build_postgres(*, verbose: bool = False, **args: object) -> PostgresSink:
    unknown = sorted(k for k in args if k not in KNOWN_POSTGRES_ARGS)
    if unknown:
        warnings.warn(
            f'built-in output sink "postgres" does not accept these keyword arguments; ignoring: {unknown}',
            RuntimeWarning,
            stacklevel=2,
        )

    from eleanor.output.postgres import PostgresSink
    from eleanor.output.postgres.config import DatabaseConfig, DatabaseRaw
    from eleanor.typing import cast

    database_raw = args.get("database")
    db_config = (
        DatabaseConfig.from_raw(cast(DatabaseRaw, cast(object, database_raw)))
        if isinstance(database_raw, dict)
        else DatabaseConfig()
    )
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


__all__ = [
    "build_csv",
    "build_memory",
    "build_null",
    "build_postgres",
]
