from enum import StrEnum
from pathlib import Path

import duckdb

from eleanor.exceptions import EleanorError
from eleanor.output.postgres.persistence import schema
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.typing import StrPath


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _make_parents(path: Path) -> list[Path]:
    created = [parent for parent in path.parents if not parent.exists()]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        _remove_empty_directories(created)
        raise
    return created


def _remove_empty_directories(dirs: list[Path]) -> None:
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            continue


def _secret(settings: PostgresDatabaseSettings) -> str:
    fields = {
        "HOST": settings.host,
        "PORT": settings.port,
        "DBNAME": settings.database,
        "USER": settings.username,
        "PASSWORD": settings.password,
        "SSLMODE": settings.sslmode,
    }

    params = [
        f"{key} {value}" if isinstance(value, int) else f"{key} '{_escape(value)}'"
        for key, value in fields.items()
        if value is not None
    ]

    if not params:
        msg = "cannot generate a postgres secret for empty PostgresDatabaseSettings"
        raise EleanorError(msg)

    return f"CREATE TEMPORARY SECRET pg_export (TYPE postgres, {', '.join(params)})"


class ExportFormat(StrEnum):
    PARQUET = "parquet"
    CSV = "csv"
    JSON = "json"


EXPORT_FORMATS: frozenset[ExportFormat] = frozenset(
    [
        ExportFormat.PARQUET,
        ExportFormat.CSV,
        ExportFormat.JSON,
    ]
)

type ExportOptionKey = str
type ExportOptionValue = str | int | bool
type ExportOptions = dict[ExportOptionKey, ExportOptionValue]

_DEFAULT_EXPORT_OPTIONS: dict[ExportFormat, ExportOptions] = {
    ExportFormat.PARQUET: {
        "COMPRESSION": "zstd",
        "ROW_GROUPS_PER_FILE": 123,
        "FILENAME_PATTERN": "{uuid}",
        "APPEND": True,
    },
}


def _load_options(format: ExportFormat, options: ExportOptions | None = None) -> ExportOptions:
    opts = {**_DEFAULT_EXPORT_OPTIONS.get(format, {})}
    if options is not None:
        opts.update({key.upper(): value for key, value in options.items()})

    return opts


def _option(key: ExportOptionKey, value: ExportOptionValue) -> str:
    if isinstance(value, bool):
        return f"{key.upper()} {str(value).lower()}"
    if isinstance(value, int):
        return f"{key.upper()} {value}"
    if isinstance(value, str):
        return f"{key.upper()} '{_escape(value)}'"

    msg = f"unexpected option type {type(value).__name__!r} for {key}: {value}"
    raise EleanorError(msg)


def _prepare_options(opts: ExportOptions) -> str:
    return ", ".join(_option(key, value) for key, value in opts.items())


def _export_query(hive: Path, format: ExportFormat, options: ExportOptions | None = None) -> str:
    options = _load_options(format, options)

    if options:
        with_part = f"(format {str(format).lower()!s}, {_prepare_options(options)})"
    else:
        with_part = f"(format {str(format).lower()!s})"

    return f"EXPORT DATABASE '{_escape(str(hive))}' {with_part!s};"


def export_duckdb(
    settings: PostgresDatabaseSettings,
    /,
    db_file: StrPath | None = None,
    hive: StrPath | None = None,
    format: ExportFormat = ExportFormat.PARQUET,
    no_export_empty: bool = False,
    verbose: bool = False,
    options: ExportOptions | None = None,
) -> None:
    if db_file is None and hive is None:
        return

    if db_file is None and format not in EXPORT_FORMATS:
        msg = f"unrecognized export format {format!r}, expected one of {EXPORT_FORMATS!r}"
        raise EleanorError(msg)

    created_parents: list[Path] = []
    if db_file is not None:
        db_file = Path(db_file).expanduser().absolute()
        if db_file.exists():
            msg = f"cannot export to existing DuckDB database '{db_file!s}'"
            raise EleanorError(msg)

        created_parents.extend(_make_parents(db_file))

        if verbose:
            print(f"Writing to database file '{db_file!s}'")
    elif verbose:
        print("Writing to in-memory database")

    db_write_completed = False
    export_completed = False
    try:
        if hive is not None:
            hive = Path(hive).expanduser().absolute()
            created_parents.extend(_make_parents(hive))

        with duckdb.connect(db_file if db_file is not None else ":memory:") as conn:
            _ = conn.sql("INSTALL postgres;")
            _ = conn.sql("LOAD postgres;")
            _ = conn.sql(_secret(settings))
            _ = conn.sql("ATTACH '' AS pg (TYPE postgres, SECRET pg_export, READ_ONLY)")

            for table in schema.TABLES:
                if no_export_empty:
                    result = conn.sql(f"SELECT COUNT(*) FROM pg.{table.name}").fetchone()
                    if result and result[0] == 0:
                        if verbose:
                            print(f"    Skipping empty table {table.name}")
                        continue

                columns = ", ".join([column.name for column in table.columns])
                query = f"CREATE TABLE {table.name} AS (SELECT {columns} FROM pg.{table.name} ORDER BY {columns});"

                if verbose:
                    print(f"    Importing {table.name!r}")
                _ = conn.sql(query)

            db_write_completed = True

            if hive is not None:
                if verbose:
                    print(f"Exporting to hive {hive!s} in {format!s} format")
                _ = conn.sql(_export_query(hive, format, options=options))

        export_completed = True
    finally:
        if not db_write_completed and db_file is not None and db_file.exists():
            if verbose:
                print(f"Removing incomplete database file '{db_file!s}'")
            db_file.unlink()
        if not export_completed:
            _remove_empty_directories(created_parents)


__all__ = [
    "EXPORT_FORMATS",
    "ExportFormat",
    "export_duckdb",
]
