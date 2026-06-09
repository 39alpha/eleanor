"""Unit tests for persistence/migrations.py — no live database required.

Uses ``tmp_path`` + ``monkeypatch`` to swap ``_PKG`` so the runner reads
synthetic migration directories instead of the real bundled one.
"""

from pathlib import Path

import pytest
from eleanor.exceptions import EleanorException
from eleanor.output.postgres.persistence import migrations


@pytest.fixture
def fake_migrations_pkg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pkg = tmp_path / "migrations"
    pkg.mkdir()
    monkeypatch.setattr(migrations, "_PKG", pkg)
    return pkg


def test_discover_returns_empty_on_empty_directory(fake_migrations_pkg: Path) -> None:
    result = migrations.discover()
    assert result == ()


def test_discover_parses_transactional_file(fake_migrations_pkg: Path) -> None:
    sql = "CREATE TABLE foo (id INTEGER);\n"
    (fake_migrations_pkg / "0001_initial_schema.sql").write_text(sql, encoding="utf-8")
    result = migrations.discover()
    assert len(result) == 1
    m = result[0]
    assert m.version == 1
    assert m.slug == "initial_schema"
    assert m.transactional is True
    assert m.sql == sql


def test_discover_parses_notxn_file(fake_migrations_pkg: Path) -> None:
    sql = "CREATE INDEX CONCURRENTLY foo_idx ON foo (bar);\n"
    (fake_migrations_pkg / "0001_add_foo_idx.notxn.sql").write_text(
        sql, encoding="utf-8"
    )
    result = migrations.discover()
    assert len(result) == 1
    m = result[0]
    assert m.version == 1
    assert m.slug == "add_foo_idx"
    assert m.transactional is False
    assert m.sql == sql


def test_discover_rejects_malformed_filename(fake_migrations_pkg: Path) -> None:
    (fake_migrations_pkg / "bad_name.sql").write_text("", encoding="utf-8")
    with pytest.raises(EleanorException, match="malformed"):
        migrations.discover()


def test_discover_ignores_non_sql_files(fake_migrations_pkg: Path) -> None:
    (fake_migrations_pkg / "README.md").write_text("docs", encoding="utf-8")
    (fake_migrations_pkg / "0001_initial_schema.sql").write_text(
        "SELECT 1;", encoding="utf-8"
    )
    result = migrations.discover()
    assert len(result) == 1
    assert result[0].version == 1


def test_discover_rejects_duplicate_version(fake_migrations_pkg: Path) -> None:
    (fake_migrations_pkg / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (fake_migrations_pkg / "0001_second.sql").write_text("SELECT 2;", encoding="utf-8")
    with pytest.raises(EleanorException, match="duplicate"):
        migrations.discover()


def test_discover_rejects_noncontiguous_numbering(fake_migrations_pkg: Path) -> None:
    (fake_migrations_pkg / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (fake_migrations_pkg / "0003_third.sql").write_text("SELECT 3;", encoding="utf-8")
    with pytest.raises(EleanorException, match="non-contiguous"):
        migrations.discover()


def test_filename_regex_accepts_long_underscore_slug(fake_migrations_pkg: Path) -> None:
    name = "0042_a_really_long_slug_with_numbers_42.sql"
    (fake_migrations_pkg / name).write_text("SELECT 1;", encoding="utf-8")
    # also need 0001..0041 to avoid non-contiguous error
    for i in range(1, 42):
        (fake_migrations_pkg / f"{i:04d}_placeholder.sql").write_text(
            "SELECT 1;", encoding="utf-8"
        )
    result = migrations.discover()
    assert result[-1].version == 42
    assert result[-1].slug == "a_really_long_slug_with_numbers_42"
