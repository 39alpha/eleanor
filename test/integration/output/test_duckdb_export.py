"""Integration tests for exporting a live Postgres database to DuckDB.

These tests require a live Postgres instance and the DuckDB postgres
extension. They skip when ``ELEANOR_TEST_DATABASE_URL`` is unset (handled by
the ``pg_config`` fixture). Each test starts from a freshly recreated
``public`` schema seeded with two orders and one variable-space row.
"""

import os
import urllib.parse
import uuid
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import cast

import duckdb
import psycopg
import pytest
import yaml
from click.testing import CliRunner
from psycopg.types.json import Jsonb

from eleanor.cli import main
from eleanor.output.postgres.persistence import connection, schema
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.output.postgres.tools.duckdb import ExportFormat, export_duckdb

_DATABASE_URL_ENV = "ELEANOR_TEST_DATABASE_URL"

_ORDER_IDS = (uuid.UUID(int=1), uuid.UUID(int=2))
_ORDER_NAMES = ("alpha", "it's beta")
_VS_ID = uuid.UUID(int=3)
_NONEMPTY_TABLES = {"orders", "variable_space"}


def _config_from_env() -> PostgresDatabaseSettings | None:
    url = os.environ.get(_DATABASE_URL_ENV)
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    return PostgresDatabaseSettings(
        host=parsed.hostname,
        port=parsed.port,
        database=(parsed.path or "/").lstrip("/") or None,
        username=parsed.username,
        password=parsed.password,
    )


def _raw_connect(cfg: PostgresDatabaseSettings) -> psycopg.Connection:
    return psycopg.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.database,
        user=cfg.username,
        password=cfg.password,
    )


@pytest.fixture(scope="session")
def pg_config() -> PostgresDatabaseSettings:
    cfg = _config_from_env()
    if cfg is None:
        pytest.skip(f"{_DATABASE_URL_ENV} not set")
    with duckdb.connect() as conn:
        try:
            _ = conn.sql("INSTALL postgres;")
            _ = conn.sql("LOAD postgres;")
        except duckdb.Error as e:
            pytest.skip(f"DuckDB postgres extension unavailable: {e}")
    return cfg


@pytest.fixture
def seeded_db(
    pg_config: PostgresDatabaseSettings,
) -> Generator[PostgresDatabaseSettings]:
    """Recreate the public schema, apply :data:`schema.TABLES` and seed a few rows."""
    connection.close_connection(pg_config)
    with _raw_connect(pg_config) as raw:
        with raw.cursor() as cur:
            _ = cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
            _ = cur.execute("CREATE SCHEMA public")
        raw.commit()
        schema.ensure_schema(raw)
        now = datetime.now()
        with raw.cursor() as cur:
            for order_id, name in zip(_ORDER_IDS, _ORDER_NAMES, strict=True):
                _ = cur.execute(
                    "INSERT INTO orders (id, name, tags, eleanor_version, raw, create_date) VALUES (%s, %s, %s, %s, %s, %s)",
                    (order_id, name, ["x", "y"], "1.0.0", Jsonb({"name": name}), now),
                )
            _ = cur.execute(
                "INSERT INTO variable_space (id, order_id, water_mass, temperature, pressure, exit_code, error, "
                "create_date, start_date, complete_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (_VS_ID, _ORDER_IDS[0], 1.0, 25.0, 1.0, 0, None, now, now, now),
            )
        raw.commit()
    yield pg_config
    connection.close_connection(pg_config)


def _tables(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.sql("SELECT table_name FROM duckdb_tables()").fetchall()
    return {cast(str, row[0]) for row in rows}


def _order_names(conn: duckdb.DuckDBPyConnection) -> list[str]:
    return [cast(str, row[0]) for row in conn.sql("SELECT name FROM orders ORDER BY name").fetchall()]


def test_export_to_database_file_copies_every_table(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    db_file = tmp_path / "out.db"

    export_duckdb(seeded_db, db_file=db_file)

    with duckdb.connect(db_file, read_only=True) as conn:
        assert _tables(conn) == {table.name for table in schema.TABLES}
        assert _order_names(conn) == sorted(_ORDER_NAMES)
        for table in schema.TABLES:
            columns = [cast(str, row[0]) for row in conn.sql(f"DESCRIBE {table.name}").fetchall()]
            assert columns == [column.name for column in table.columns]


def test_export_preserves_column_values(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    db_file = tmp_path / "out.db"

    export_duckdb(seeded_db, db_file=db_file)

    with duckdb.connect(db_file, read_only=True) as conn:
        row = conn.sql("SELECT id, tags, eleanor_version, raw->>'name' FROM orders WHERE name = 'alpha'").fetchone()
        assert row == (_ORDER_IDS[0], ["x", "y"], "1.0.0", "alpha")
        vs = conn.sql("SELECT id, order_id, temperature, error FROM variable_space").fetchall()
        assert vs == [(_VS_ID, _ORDER_IDS[0], 25.0, None)]


def test_export_does_not_persist_credentials_or_attachment(
    seeded_db: PostgresDatabaseSettings,
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "out.db"

    export_duckdb(seeded_db, db_file=db_file)

    with duckdb.connect(db_file, read_only=True) as conn:
        assert conn.sql("SELECT name FROM duckdb_secrets()").fetchall() == []
        databases = {cast(str, row[0]) for row in conn.sql("SELECT database_name FROM duckdb_databases()").fetchall()}
        assert "pg" not in databases
    if seeded_db.password:
        assert seeded_db.password.encode() not in db_file.read_bytes()


def test_export_skips_empty_tables(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    db_file = tmp_path / "out.db"

    export_duckdb(seeded_db, db_file=db_file, no_export_empty=True)

    with duckdb.connect(db_file, read_only=True) as conn:
        assert _tables(conn) == _NONEMPTY_TABLES


def test_hive_scripts_do_not_reference_the_postgres_connection(
    seeded_db: PostgresDatabaseSettings,
    tmp_path: Path,
) -> None:
    hive = tmp_path / "hive"

    export_duckdb(seeded_db, hive=hive, format=ExportFormat.CSV)

    for script in ("schema.sql", "load.sql"):
        text = (hive / script).read_text().lower()
        for needle in ("secret", "pg_export", "attach", "postgres"):
            assert needle not in text


@pytest.mark.parametrize("format", list(ExportFormat))
def test_export_to_hive_round_trips(
    seeded_db: PostgresDatabaseSettings,
    tmp_path: Path,
    format: ExportFormat,
) -> None:
    hive = tmp_path / "hive"

    export_duckdb(seeded_db, hive=hive, format=format, no_export_empty=True)

    assert (hive / "schema.sql").is_file()
    assert (hive / "load.sql").is_file()
    for table in _NONEMPTY_TABLES:
        assert (hive / f"{table}.{format}").exists()

    with duckdb.connect() as conn:
        _ = conn.sql(f"IMPORT DATABASE '{hive}'")
        assert _tables(conn) == _NONEMPTY_TABLES
        assert _order_names(conn) == sorted(_ORDER_NAMES)


def test_export_to_database_and_hive(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    db_file = tmp_path / "out.db"
    hive = tmp_path / "hive"

    export_duckdb(seeded_db, db_file=db_file, hive=hive, format=ExportFormat.CSV)

    with duckdb.connect(db_file, read_only=True) as conn:
        assert _order_names(conn) == sorted(_ORDER_NAMES)
    assert (hive / "orders.csv").is_file()


def test_export_creates_nested_directories(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    db_file = tmp_path / "a" / "b" / "out.db"
    hive = tmp_path / "c" / "d" / "hive"

    export_duckdb(seeded_db, db_file=db_file, hive=hive, format=ExportFormat.CSV)

    with duckdb.connect(db_file, read_only=True) as conn:
        assert _order_names(conn) == sorted(_ORDER_NAMES)
    assert (hive / "orders.csv").is_file()


def test_export_to_existing_parquet_hive_appends(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    hive = tmp_path / "hive"

    export_duckdb(seeded_db, hive=hive, format=ExportFormat.PARQUET)
    export_duckdb(seeded_db, hive=hive, format=ExportFormat.PARQUET)

    with duckdb.connect() as conn:
        rows = conn.sql(f"SELECT name FROM read_parquet('{hive}/orders.parquet/*.parquet') ORDER BY name").fetchall()
    assert [cast(str, row[0]) for row in rows] == sorted(_ORDER_NAMES * 2)


def test_export_to_existing_csv_hive_overwrites(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    hive = tmp_path / "hive"

    export_duckdb(seeded_db, hive=hive, format=ExportFormat.CSV)
    export_duckdb(seeded_db, hive=hive, format=ExportFormat.CSV)

    with duckdb.connect() as conn:
        _ = conn.sql(f"IMPORT DATABASE '{hive}'")
        assert _order_names(conn) == sorted(_ORDER_NAMES)


def test_export_applies_user_options(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    hive = tmp_path / "hive"

    export_duckdb(
        seeded_db,
        hive=hive,
        format=ExportFormat.CSV,
        no_export_empty=True,
        options={"DELIMITER": "|", "HEADER": False},
    )

    lines = (hive / "orders.csv").read_text().splitlines()
    assert len(lines) == len(_ORDER_NAMES)
    assert all("|" in line for line in lines)


def test_failed_export_removes_database_file_and_hides_password(
    seeded_db: PostgresDatabaseSettings,
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "out.db"
    marker = "SECRET-PASSWORD-MARKER"
    settings = PostgresDatabaseSettings(
        host=seeded_db.host,
        port=seeded_db.port,
        database=f"{seeded_db.database}_does_not_exist_{uuid.uuid4().hex}",
        username=seeded_db.username,
        password=marker,
    )

    with pytest.raises(duckdb.Error) as excinfo:
        export_duckdb(settings, db_file=db_file)

    assert marker not in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []


def _write_config(path: Path, settings: PostgresDatabaseSettings) -> Path:
    database = {
        key: value
        for key, value in {
            "host": settings.host,
            "port": settings.port,
            "database": settings.database,
            "username": settings.username,
            "password": settings.password,
        }.items()
        if value is not None
    }
    _ = path.write_text(yaml.safe_dump({"output": {"kind": "postgres", "database": database}}))
    return path


def test_cli_exports_database_file(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    config = _write_config(tmp_path / "config.yaml", seeded_db)
    db_file = tmp_path / "out.db"

    result = CliRunner().invoke(main, ["postgres", "export", "duckdb", "-c", str(config), "-o", str(db_file), "-n"])

    assert result.exit_code == 0, result.output
    with duckdb.connect(db_file, read_only=True) as conn:
        assert _tables(conn) == _NONEMPTY_TABLES


def test_cli_exports_hive_with_options(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    config = _write_config(tmp_path / "config.yaml", seeded_db)
    hive = tmp_path / "bob's hive"

    result = CliRunner().invoke(
        main,
        [
            "postgres",
            "export",
            "duckdb",
            "-c",
            str(config),
            "-H",
            str(hive),
            "-t",
            "csv",
            "-e",
            "delimiter=;",
            "-e",
            "header=false",
            "-n",
        ],
    )

    assert result.exit_code == 0, result.output
    lines = (hive / "orders.csv").read_text().splitlines()
    assert len(lines) == len(_ORDER_NAMES)
    assert all(";" in line for line in lines)


def test_cli_reports_failure_without_password(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    marker = "SECRET-PASSWORD-MARKER"
    settings = PostgresDatabaseSettings(
        host=seeded_db.host,
        port=seeded_db.port,
        database=f"{seeded_db.database}_does_not_exist_{uuid.uuid4().hex}",
        username=seeded_db.username,
        password=marker,
    )
    config = _write_config(tmp_path / "config.yaml", settings)
    db_file = tmp_path / "out.db"

    result = CliRunner().invoke(main, ["postgres", "export", "duckdb", "-c", str(config), "-o", str(db_file)])

    assert result.exit_code != 0
    assert "failed to export database" in result.output
    assert marker not in result.output
    assert not db_file.exists()


def test_failed_export_removes_created_directories(seeded_db: PostgresDatabaseSettings, tmp_path: Path) -> None:
    settings = PostgresDatabaseSettings(
        host=seeded_db.host,
        port=seeded_db.port,
        database=f"{seeded_db.database}_does_not_exist_{uuid.uuid4().hex}",
        username=seeded_db.username,
        password=seeded_db.password,
    )

    with pytest.raises(duckdb.Error):
        export_duckdb(settings, db_file=tmp_path / "a" / "b" / "out.db", hive=tmp_path / "c" / "d" / "hive")

    assert list(tmp_path.iterdir()) == []


def test_cli_exports_to_nested_user_relative_paths(
    seeded_db: PostgresDatabaseSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _write_config(tmp_path / "config.yaml", seeded_db)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = CliRunner().invoke(
        main,
        [
            "postgres",
            "export",
            "duckdb",
            "-c",
            str(config),
            "--output=~/a/b/out.db",
            "--hive=~/c/d/hive",
            "-t",
            "csv",
            "-n",
        ],
    )

    assert result.exit_code == 0, result.output
    with duckdb.connect(tmp_path / "a" / "b" / "out.db", read_only=True) as conn:
        assert _tables(conn) == _NONEMPTY_TABLES
    assert (tmp_path / "c" / "d" / "hive" / "orders.csv").is_file()
