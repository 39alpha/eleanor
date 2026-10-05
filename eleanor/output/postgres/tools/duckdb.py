from pathlib import Path

import duckdb

from eleanor.exceptions import EleanorError
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.typing import StrPath


def export_duckdb(_settings: PostgresDatabaseSettings, /, db_file: StrPath | None = None) -> None:
    if db_file is not None:
        db_file = Path(db_file).expanduser()
        if db_file.exists():
            msg = "cannot export to an existing DuckDB database"
            raise EleanorError(msg)

    with duckdb.connect(db_file if db_file is not None else ":memory:"):
        ...


__all__ = ["export_duckdb"]
