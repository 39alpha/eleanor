"""Unit tests for :mod:`eleanor.output.postgres.tools.duckdb`.

The statement builders are exercised both as strings and, where DuckDB can
run them without a Postgres server, against a real in-memory DuckDB. The
export driver is exercised against a fake connection that records the
statements it is sent and fails on demand.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from types import TracebackType
from typing import Self, cast

import duckdb
import pytest
from pytest_mock import MockerFixture

from eleanor.exceptions import EleanorError
from eleanor.output.postgres.persistence import schema
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.output.postgres.tools import duckdb as tools
from eleanor.output.postgres.tools.duckdb import ExportFormat, export_duckdb

_SETTINGS = PostgresDatabaseSettings(database="eleanor", username="alice", password="hunter2")


@pytest.fixture
def postgres_extension() -> Iterator[duckdb.DuckDBPyConnection]:
    """An in-memory DuckDB with the postgres extension loaded, or skip."""
    conn = duckdb.connect()
    try:
        _ = conn.sql("INSTALL postgres;")
        _ = conn.sql("LOAD postgres;")
    except duckdb.Error as e:
        conn.close()
        pytest.skip(f"DuckDB postgres extension unavailable: {e}")
    yield conn
    conn.close()


class _Result:
    def __init__(self, row: tuple[int]) -> None:
        self.row = row

    def fetchone(self) -> tuple[int]:
        return self.row


class _FakeConnection:
    """Records statements; raises on the first one matching ``fail_on``."""

    def __init__(
        self,
        path: Path | None,
        fail_on: str | None = None,
        count: int = 1,
        error: type[BaseException] = duckdb.IOException,
        before_fail: Callable[[], None] | None = None,
    ) -> None:
        self.statements: list[str] = []
        self.fail_on = fail_on
        self.count = count
        self.error = error
        self.before_fail = before_fail
        if path is not None:
            path.touch()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def sql(self, query: str) -> _Result:
        self.statements.append(query)
        if self.fail_on is not None and query.startswith(self.fail_on):
            if self.before_fail is not None:
                self.before_fail()
            msg = f"injected failure on {self.fail_on!r}"
            raise self.error(msg)
        return _Result((self.count,))


def _patch_connect(
    mocker: MockerFixture,
    *,
    fail_on: str | None = None,
    count: int = 1,
    error: type[BaseException] = duckdb.IOException,
    before_fail: Callable[[], None] | None = None,
) -> list[_FakeConnection]:
    """Replace ``duckdb.connect`` in the tools module with a fake factory."""
    made: list[_FakeConnection] = []

    def connect(database: str | Path) -> _FakeConnection:
        conn = _FakeConnection(None if database == ":memory:" else Path(database), fail_on, count, error, before_fail)
        made.append(conn)
        return conn

    _ = mocker.patch.object(tools.duckdb, "connect", side_effect=connect)
    return made


def test_escape_doubles_single_quotes() -> None:
    assert tools._escape("it's") == "it''s"
    assert tools._escape("''") == "''''"


def test_escape_leaves_other_characters_alone() -> None:
    value = 'a "b" \\c; -- d'
    assert tools._escape(value) == value


def test_secret_includes_only_configured_fields() -> None:
    sql = tools._secret(PostgresDatabaseSettings(host="db.example.org", database="eleanor"))
    assert sql == "CREATE TEMPORARY SECRET pg_export (TYPE postgres, HOST 'db.example.org', DBNAME 'eleanor')"


def test_secret_includes_every_field_in_order() -> None:
    settings = PostgresDatabaseSettings(
        host="127.0.0.1",
        port=5433,
        database="eleanor",
        username="alice",
        password="hunter2",
        sslmode="verify-full",
    )
    assert tools._secret(settings) == (
        "CREATE TEMPORARY SECRET pg_export (TYPE postgres, HOST '127.0.0.1', PORT 5433, DBNAME 'eleanor', "
        "USER 'alice', PASSWORD 'hunter2', SSLMODE 'verify-full')"
    )


def test_secret_escapes_quotes_in_values() -> None:
    sql = tools._secret(PostgresDatabaseSettings(host=None, password="it's"))
    assert sql == "CREATE TEMPORARY SECRET pg_export (TYPE postgres, PASSWORD 'it''s')"


def test_secret_rejects_empty_settings() -> None:
    with pytest.raises(EleanorError, match="empty PostgresDatabaseSettings"):
        _ = tools._secret(PostgresDatabaseSettings(host=None))


@pytest.mark.parametrize(
    "password",
    ["plain", "with space", "it's", "back\\slash", 'dou"ble', "semi;colon -- comment", "''"],
)
def test_secret_is_accepted_by_duckdb_and_redacts_password(
    postgres_extension: duckdb.DuckDBPyConnection,
    password: str,
) -> None:
    settings = PostgresDatabaseSettings(
        host="db.example.org",
        port=5432,
        database="eleanor",
        username="alice",
        password=password,
        sslmode="require",
    )
    _ = postgres_extension.sql(tools._secret(settings))

    row = postgres_extension.sql("SELECT secret_string FROM duckdb_secrets() WHERE name = 'pg_export'").fetchone()
    assert row is not None
    secret = cast(str, row[0])
    assert "password=redacted" in secret
    assert "host=db.example.org" in secret
    assert "port=5432" in secret
    assert "dbname=eleanor" in secret
    assert "user=alice" in secret
    assert "sslmode=require" in secret


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "KEY true"),
        (False, "KEY false"),
        (0, "KEY 0"),
        (123, "KEY 123"),
        ("zstd", "KEY 'zstd'"),
        ("%d 'of' %B", "KEY '%d ''of'' %B'"),
        ("", "KEY ''"),
    ],
)
def test_option_renders_value_by_type(value: bool | int | str, expected: str) -> None:
    assert tools._option("KEY", value) == expected


def test_option_upper_cases_the_key() -> None:
    assert tools._option("header", True) == "HEADER true"


def test_option_rejects_unsupported_types() -> None:
    with pytest.raises(EleanorError, match="unexpected option type 'float'"):
        _ = tools._option("KEY", cast(int, 1.5))


def test_load_options_defaults_for_parquet() -> None:
    assert tools._load_options(ExportFormat.PARQUET) == {
        "COMPRESSION": "zstd",
        "ROW_GROUPS_PER_FILE": 123,
        "FILENAME_PATTERN": "{uuid}",
        "APPEND": True,
    }


@pytest.mark.parametrize("format", [ExportFormat.CSV, ExportFormat.JSON])
def test_load_options_has_no_defaults_for_text_formats(format: ExportFormat) -> None:
    assert tools._load_options(format) == {}


def test_load_options_overrides_defaults_case_insensitively() -> None:
    opts = tools._load_options(ExportFormat.PARQUET, {"compression": "snappy", "append": False})
    assert opts["COMPRESSION"] == "snappy"
    assert opts["APPEND"] is False
    assert "compression" not in opts


def test_load_options_does_not_mutate_defaults() -> None:
    _ = tools._load_options(ExportFormat.PARQUET, {"COMPRESSION": "snappy", "EXTRA": 1})
    assert tools._load_options(ExportFormat.PARQUET)["COMPRESSION"] == "zstd"
    assert "EXTRA" not in tools._load_options(ExportFormat.PARQUET)


def test_export_query_without_options() -> None:
    assert tools._export_query(Path("out"), ExportFormat.CSV) == "EXPORT DATABASE 'out' (format csv);"


def test_export_query_with_options() -> None:
    query = tools._export_query(Path("out"), ExportFormat.CSV, {"delimiter": "|", "header": True})
    assert query == "EXPORT DATABASE 'out' (format csv, DELIMITER '|', HEADER true);"


def test_export_query_escapes_the_hive_path() -> None:
    assert (
        tools._export_query(Path("bob's export"), ExportFormat.JSON) == "EXPORT DATABASE 'bob''s export' (format json);"
    )


def test_export_query_includes_parquet_defaults() -> None:
    query = tools._export_query(Path("out"), ExportFormat.PARQUET)
    assert query == (
        "EXPORT DATABASE 'out' (format parquet, COMPRESSION 'zstd', ROW_GROUPS_PER_FILE 123, "
        "FILENAME_PATTERN '{uuid}', APPEND true);"
    )


@pytest.mark.parametrize("format", list(ExportFormat))
def test_export_query_runs_in_duckdb(tmp_path: Path, format: ExportFormat) -> None:
    hive = tmp_path / f"bob's {format}"
    with duckdb.connect() as conn:
        _ = conn.sql("CREATE TABLE orders AS SELECT 'it''s' AS name, [1, 2] AS tags")
        _ = conn.sql(tools._export_query(hive, format))

    assert (hive / "schema.sql").is_file()
    assert (hive / "load.sql").is_file()
    assert (hive / f"orders.{format}").exists()

    with duckdb.connect() as conn:
        _ = conn.sql(f"IMPORT DATABASE '{tools._escape(str(hive))}'")
        assert conn.sql("SELECT name FROM orders").fetchall() == [("it's",)]


def test_export_query_runs_in_duckdb_with_csv_options(tmp_path: Path) -> None:
    hive = tmp_path / "csv"
    with duckdb.connect() as conn:
        _ = conn.sql("CREATE TABLE orders AS SELECT 'a' AS x, 'b' AS y")
        _ = conn.sql(tools._export_query(hive, ExportFormat.CSV, {"DELIMITER": "|", "HEADER": False}))

    assert (hive / "orders.csv").read_text().strip() == "a|b"


def test_export_duckdb_without_targets_does_nothing(mocker: MockerFixture) -> None:
    made = _patch_connect(mocker)
    export_duckdb(_SETTINGS)
    assert made == []


def test_export_duckdb_rejects_an_existing_database_file(tmp_path: Path, mocker: MockerFixture) -> None:
    db_file = tmp_path / "out.db"
    _ = db_file.write_bytes(b"keep me")
    made = _patch_connect(mocker)

    with pytest.raises(EleanorError, match="cannot export to existing DuckDB database"):
        export_duckdb(_SETTINGS, db_file=db_file)

    assert made == []
    assert db_file.read_bytes() == b"keep me"


def test_export_duckdb_expands_user_in_database_path(
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    made = _patch_connect(mocker)

    export_duckdb(_SETTINGS, db_file="~/out.db")

    assert len(made) == 1
    assert (tmp_path / "out.db").exists()


def test_export_duckdb_creates_missing_database_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    db_file = tmp_path / "a" / "b" / "out.db"
    _ = _patch_connect(mocker)

    export_duckdb(_SETTINGS, db_file=db_file)

    assert db_file.exists()


def test_export_duckdb_creates_missing_hive_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    hive = tmp_path / "a" / "b" / "hive"
    _ = _patch_connect(mocker)

    export_duckdb(_SETTINGS, hive=hive)

    assert hive.parent.is_dir()


def test_export_duckdb_sends_statements_in_order(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker)

    export_duckdb(_SETTINGS, db_file=tmp_path / "out.db", hive=tmp_path / "hive", format=ExportFormat.CSV)

    (conn,) = made
    assert conn.statements[:4] == [
        "INSTALL postgres;",
        "LOAD postgres;",
        tools._secret(_SETTINGS),
        "ATTACH '' AS pg (TYPE postgres, SECRET pg_export, READ_ONLY)",
    ]
    creates = conn.statements[4:-1]
    assert [s.split()[2] for s in creates] == [table.name for table in schema.TABLES]
    assert conn.statements[-1] == tools._export_query(tmp_path / "hive", ExportFormat.CSV)


def test_export_duckdb_never_puts_the_password_in_the_attach(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker)

    export_duckdb(_SETTINGS, db_file=tmp_path / "out.db")

    (conn,) = made
    (attach,) = [s for s in conn.statements if s.startswith("ATTACH")]
    assert "hunter2" not in attach


def test_export_duckdb_copies_every_column_in_order(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker)

    export_duckdb(_SETTINGS, db_file=tmp_path / "out.db")

    (conn,) = made
    columns = ", ".join(column.name for column in schema.ORDERS.columns)
    assert f"CREATE TABLE orders AS (SELECT {columns} FROM pg.orders ORDER BY {columns});" in conn.statements


def test_export_duckdb_uses_memory_without_database_file(tmp_path: Path, mocker: MockerFixture) -> None:
    connect = mocker.patch.object(tools.duckdb, "connect", return_value=_FakeConnection(None))

    export_duckdb(_SETTINGS, hive=tmp_path / "hive")

    connect.assert_called_once_with(":memory:")


def test_export_duckdb_skips_empty_tables_when_asked(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker, count=0)

    export_duckdb(_SETTINGS, db_file=tmp_path / "out.db", no_export_empty=True)

    (conn,) = made
    assert not [s for s in conn.statements if s.startswith("CREATE TABLE")]
    counts = [s for s in conn.statements if s.startswith("SELECT COUNT(*)")]
    assert len(counts) == len(schema.TABLES)


def test_export_duckdb_keeps_nonempty_tables_when_skipping_empty(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker, count=3)

    export_duckdb(_SETTINGS, db_file=tmp_path / "out.db", no_export_empty=True)

    (conn,) = made
    assert len([s for s in conn.statements if s.startswith("CREATE TABLE")]) == len(schema.TABLES)


def test_export_duckdb_does_not_count_rows_by_default(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker, count=0)

    export_duckdb(_SETTINGS, db_file=tmp_path / "out.db")

    (conn,) = made
    assert not [s for s in conn.statements if s.startswith("SELECT COUNT(*)")]


@pytest.mark.parametrize("fail_on", ["INSTALL", "LOAD", "CREATE TEMPORARY SECRET", "ATTACH", "CREATE TABLE"])
def test_export_duckdb_removes_incomplete_database_file(
    tmp_path: Path,
    mocker: MockerFixture,
    fail_on: str,
) -> None:
    db_file = tmp_path / "out.db"
    _ = _patch_connect(mocker, fail_on=fail_on)

    with pytest.raises(duckdb.IOException, match="injected failure"):
        export_duckdb(_SETTINGS, db_file=db_file)

    assert not db_file.exists()


def test_export_duckdb_reports_removal_when_verbose(
    tmp_path: Path,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_file = tmp_path / "out.db"
    _ = _patch_connect(mocker, fail_on="ATTACH")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=db_file, verbose=True)

    assert f"Removing incomplete database file '{db_file}'" in capsys.readouterr().out


def test_export_duckdb_keeps_complete_database_file_when_hive_export_fails(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    db_file = tmp_path / "out.db"
    _ = _patch_connect(mocker, fail_on="EXPORT DATABASE")

    with pytest.raises(duckdb.IOException, match="injected failure"):
        export_duckdb(_SETTINGS, db_file=db_file, hive=tmp_path / "hive")

    assert db_file.exists()


def test_export_duckdb_removes_database_file_on_interrupt(tmp_path: Path, mocker: MockerFixture) -> None:
    db_file = tmp_path / "out.db"
    _ = _patch_connect(mocker, fail_on="CREATE TABLE", error=KeyboardInterrupt)

    with pytest.raises(KeyboardInterrupt):
        export_duckdb(_SETTINGS, db_file=db_file)

    assert not db_file.exists()


def test_export_duckdb_does_not_leak_password_when_connection_fails(
    postgres_extension: duckdb.DuckDBPyConnection,
    tmp_path: Path,
) -> None:
    del postgres_extension
    db_file = tmp_path / "out.db"
    settings = PostgresDatabaseSettings(
        host="127.0.0.1",
        port=1,
        database="eleanor",
        username="alice",
        password="SECRET-PASSWORD-MARKER",
    )

    with pytest.raises(duckdb.Error) as excinfo:
        export_duckdb(settings, db_file=db_file)

    assert "SECRET-PASSWORD-MARKER" not in str(excinfo.value)
    assert not db_file.exists()
    assert list(tmp_path.iterdir()) == []


def test_export_duckdb_reports_absolute_path_for_relative_existing_database(
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / "out.db").write_bytes(b"keep me")
    _ = _patch_connect(mocker)

    with pytest.raises(EleanorError, match=f"'{tmp_path / 'out.db'}'"):
        export_duckdb(_SETTINGS, db_file="out.db")


def test_export_duckdb_opens_relative_database_by_absolute_path(
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    connect = mocker.patch.object(tools.duckdb, "connect", return_value=_FakeConnection(None))

    export_duckdb(_SETTINGS, db_file="out.db")

    connect.assert_called_once_with(tmp_path / "out.db")


def test_export_duckdb_exports_relative_hive_by_absolute_path(
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    made = _patch_connect(mocker)

    export_duckdb(_SETTINGS, hive="hive", format=ExportFormat.CSV)

    (conn,) = made
    assert conn.statements[-1] == tools._export_query(tmp_path / "hive", ExportFormat.CSV)


def test_export_duckdb_expands_user_in_hive_path(
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    made = _patch_connect(mocker)

    export_duckdb(_SETTINGS, hive="~/a/hive", format=ExportFormat.CSV)

    (conn,) = made
    assert conn.statements[-1] == tools._export_query(tmp_path / "a" / "hive", ExportFormat.CSV)
    assert (tmp_path / "a").is_dir()


def test_export_duckdb_does_not_create_the_hive_directory_itself(tmp_path: Path, mocker: MockerFixture) -> None:
    hive = tmp_path / "a" / "hive"
    _ = _patch_connect(mocker)

    export_duckdb(_SETTINGS, hive=hive)

    assert hive.parent.is_dir()
    assert not hive.exists()


def test_export_duckdb_creates_directories_before_connecting(tmp_path: Path, mocker: MockerFixture) -> None:
    db_file = tmp_path / "a" / "out.db"
    hive = tmp_path / "b" / "hive"
    seen: list[tuple[bool, bool]] = []

    def connect(database: Path) -> _FakeConnection:
        seen.append((db_file.parent.is_dir(), hive.parent.is_dir()))
        return _FakeConnection(database)

    _ = mocker.patch.object(tools.duckdb, "connect", side_effect=connect)

    export_duckdb(_SETTINGS, db_file=db_file, hive=hive)

    assert seen == [(True, True)]


def test_export_duckdb_fails_before_connecting_when_database_directory_is_blocked(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    _ = (tmp_path / "blocker").write_text("")
    made = _patch_connect(mocker)

    with pytest.raises(OSError):  # noqa: PT011
        export_duckdb(_SETTINGS, db_file=tmp_path / "blocker" / "out.db")

    assert made == []


def test_export_duckdb_fails_before_connecting_when_hive_directory_is_blocked(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    _ = (tmp_path / "blocker").write_text("")
    made = _patch_connect(mocker)

    with pytest.raises(OSError):  # noqa: PT011
        export_duckdb(_SETTINGS, hive=tmp_path / "blocker" / "a" / "hive")

    assert made == []


def test_export_duckdb_reports_paths_when_verbose(
    tmp_path: Path,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_file = tmp_path / "out.db"
    hive = tmp_path / "hive"
    _ = _patch_connect(mocker)

    export_duckdb(_SETTINGS, db_file=db_file, hive=hive, format=ExportFormat.CSV, verbose=True)

    out = capsys.readouterr().out
    assert f"Writing to database file '{db_file}'" in out
    assert f"Exporting to hive {hive} in csv format" in out


def test_export_duckdb_reports_memory_database_when_verbose(
    tmp_path: Path,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _patch_connect(mocker)

    export_duckdb(_SETTINGS, hive=tmp_path / "hive", verbose=True)

    assert "Writing to in-memory database" in capsys.readouterr().out


# Directories created for an export are removed again when the export fails,
# provided they are still empty. Directories that already existed are never
# removed, and neither is anything holding output the user keeps.


def test_failed_export_removes_created_database_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    _ = _patch_connect(mocker, fail_on="ATTACH")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "b" / "out.db")

    assert list(tmp_path.iterdir()) == []


def test_failed_export_keeps_directories_that_already_existed(tmp_path: Path, mocker: MockerFixture) -> None:
    (tmp_path / "a").mkdir()
    _ = _patch_connect(mocker, fail_on="ATTACH")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "b" / "out.db")

    assert (tmp_path / "a").is_dir()
    assert list((tmp_path / "a").iterdir()) == []


def test_failed_export_removes_created_hive_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    _ = _patch_connect(mocker, fail_on="EXPORT DATABASE")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, hive=tmp_path / "a" / "b" / "hive")

    assert list(tmp_path.iterdir()) == []


def test_failed_import_removes_both_sets_of_created_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    _ = _patch_connect(mocker, fail_on="CREATE TABLE")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "out.db", hive=tmp_path / "b" / "c" / "hive")

    assert list(tmp_path.iterdir()) == []


def test_failed_export_removes_a_shared_created_directory(tmp_path: Path, mocker: MockerFixture) -> None:
    _ = _patch_connect(mocker, fail_on="ATTACH")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "out.db", hive=tmp_path / "a" / "hive")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("db_file", "hive"),
    [
        ("a/out.db", "a/x/hive"),
        ("a/x/out.db", "a/hive"),
        ("a/out.db", "a/x/y/hive"),
        ("a/x/y/out.db", "a/hive"),
    ],
)
def test_failed_export_removes_nested_created_directories(
    tmp_path: Path,
    mocker: MockerFixture,
    db_file: str,
    hive: str,
) -> None:
    _ = _patch_connect(mocker, fail_on="ATTACH")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=tmp_path / db_file, hive=tmp_path / hive)

    assert list(tmp_path.iterdir()) == []


def test_failed_hive_export_keeps_database_and_its_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    db_file = tmp_path / "a" / "out.db"
    _ = _patch_connect(mocker, fail_on="EXPORT DATABASE")

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=db_file, hive=tmp_path / "b" / "c" / "hive")

    assert db_file.exists()
    assert not (tmp_path / "b").exists()


def test_failed_hive_export_keeps_partial_hive_output(tmp_path: Path, mocker: MockerFixture) -> None:
    hive = tmp_path / "a" / "hive"

    def write_partial_hive() -> None:
        hive.mkdir()
        _ = (hive / "orders.csv").write_text("partial\n")

    _ = _patch_connect(mocker, fail_on="EXPORT DATABASE", before_fail=write_partial_hive)

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, hive=hive)

    assert (hive / "orders.csv").read_text() == "partial\n"


def test_failed_export_keeps_created_directories_that_gained_content(tmp_path: Path, mocker: MockerFixture) -> None:
    other = tmp_path / "a" / "b" / "other.txt"

    def write_other() -> None:
        _ = other.write_text("keep me")

    _ = _patch_connect(mocker, fail_on="ATTACH", before_fail=write_other)

    with pytest.raises(duckdb.IOException):
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "b" / "out.db")

    assert other.read_text() == "keep me"
    assert not (tmp_path / "a" / "b" / "out.db").exists()


def test_failed_hive_directory_creation_removes_created_database_directories(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    _ = (tmp_path / "blocker").write_text("")
    _ = _patch_connect(mocker)

    with pytest.raises(OSError):  # noqa: PT011
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "out.db", hive=tmp_path / "blocker" / "hive")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["blocker"]


# A directory name longer than any filesystem allows makes ``mkdir`` fail
# after it has already created the ancestors above that name.
_TOO_LONG = "x" * 300


def test_partially_created_database_directories_are_removed(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker)

    with pytest.raises(OSError):  # noqa: PT011
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / _TOO_LONG / "out.db")

    assert made == []
    assert list(tmp_path.iterdir()) == []


def test_partially_created_hive_directories_are_removed(tmp_path: Path, mocker: MockerFixture) -> None:
    made = _patch_connect(mocker)

    with pytest.raises(OSError):  # noqa: PT011
        export_duckdb(_SETTINGS, hive=tmp_path / "a" / _TOO_LONG / "hive")

    assert made == []
    assert list(tmp_path.iterdir()) == []


def test_partially_created_hive_directories_remove_database_directories_too(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    made = _patch_connect(mocker)

    with pytest.raises(OSError):  # noqa: PT011
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "out.db", hive=tmp_path / "b" / _TOO_LONG / "hive")

    assert made == []
    assert list(tmp_path.iterdir()) == []


def test_interrupted_export_removes_created_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    _ = _patch_connect(mocker, fail_on="CREATE TABLE", error=KeyboardInterrupt)

    with pytest.raises(KeyboardInterrupt):
        export_duckdb(_SETTINGS, db_file=tmp_path / "a" / "out.db", hive=tmp_path / "b" / "hive")

    assert list(tmp_path.iterdir()) == []


def test_successful_export_keeps_created_directories(tmp_path: Path, mocker: MockerFixture) -> None:
    db_file = tmp_path / "a" / "out.db"
    hive = tmp_path / "b" / "hive"
    _ = _patch_connect(mocker)

    export_duckdb(_SETTINGS, db_file=db_file, hive=hive)

    assert db_file.exists()
    assert hive.parent.is_dir()
