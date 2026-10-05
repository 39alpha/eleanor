from enum import StrEnum
from pathlib import Path

import duckdb

from eleanor.exceptions import EleanorError
from eleanor.output.postgres.persistence import schema
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.typing import StrPath


def __attach(settings: PostgresDatabaseSettings) -> str:
    parts: list[str] = []

    if settings.host is not None:
        parts.append(f"host={settings.host}")
    if settings.port is not None:
        parts.append(f"port={settings.port}")
    if settings.database is not None:
        parts.append(f"dbname={settings.database}")
    if settings.username is not None:
        parts.append(f"user={settings.username}")
    if settings.password is not None:
        parts.append(f"password={settings.password}")

    if not parts:
        msg = "cannot generate an ATTACH statement for empty PostgresDatabaseSettings"
        raise EleanorError(msg)

    return f"ATTACH '{' '.join(parts)}' AS pg (TYPE postgres, READ_ONLY)"


class ExportFormat(StrEnum):
    PARQUET = "parquet"
    CSV = "csv"


EXPORT_FORMATS: frozenset[ExportFormat] = frozenset(
    [
        ExportFormat.PARQUET,
        ExportFormat.CSV,
    ]
)

type ExportOptionKey = str
type ExportOptionValue = str | int | bool
type ExportOptions = dict[ExportOptionKey, ExportOptionValue]

_DEFAULT_EXPORT_OPTIONS: dict[ExportFormat, ExportOptions] = {
    ExportFormat.PARQUET: {
        "COMPRESSION": "zstd",
        "ROW_GROUPS_PER_FILE": 123,
        "FILENAME_PATTERN": '"{uuid}"',
        "APPEND": True,
    },
    ExportFormat.CSV: {
        "FILENAME_PATTERN": '"{uuid}"',
        "APPEND": True,
    },
}


def _load_options(format: ExportFormat, options: ExportOptions | None = None) -> ExportOptions:
    opts = {**_DEFAULT_EXPORT_OPTIONS[format]}
    if options is not None:
        opts.update({key.upper(): value for key, value in options.items()})
    return opts


def _option(key: ExportOptionKey, value: ExportOptionValue) -> str:
    if isinstance(value, bool) and not isinstance(value, int):
        return f"{key.upper()}"
    if isinstance(value, (str, int)):
        return f"{key.upper()} {value!s}"

    msg = f"unexpected option type {type(value).__name__!r} for {key}: {value}"
    raise EleanorError(msg)


def _prepare_options(opts: ExportOptions) -> str:
    return ", ".join(_option(key, value) for key, value in opts.items())


def _export_query(hive: Path | str, format: ExportFormat, options: ExportOptions | None = None) -> str:
    options = _load_options(format, options)
    return f"EXPORT DATABASE '{hive}' (format {str(format).lower()!s}, {_prepare_options(options)});"


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

    if db_file is not None:
        db_file = Path(db_file).expanduser()
        if db_file.exists():
            msg = "cannot export to an existing DuckDB database"
            raise EleanorError(msg)
        if verbose:
            print(f"Writing to database file {db_file!r}")
    elif verbose:
        print("Writing to in-memory database")

    with duckdb.connect(db_file if db_file is not None else ":memory:") as conn:
        _ = conn.sql("INSTALL postgres;")
        _ = conn.sql("LOAD postgres;")
        _ = conn.sql(__attach(settings))

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

        if hive is not None:
            if verbose:
                print(f"Exporting to hive {hive!r} in {format!s} format")
            _ = conn.sql(_export_query(hive, format, options=options))


__all__ = [
    "EXPORT_FORMATS",
    "ExportFormat",
    "export_duckdb",
]
