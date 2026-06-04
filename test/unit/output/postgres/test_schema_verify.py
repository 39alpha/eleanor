"""Unit tests for the schema verifier helpers — no live database required.

Tests the pure functions: declared-name helpers, _columns_by_name,
and the mocked-reader ``verify_against_tables`` verifier check.
"""

from pytest_mock import MockerFixture

from eleanor.output.postgres.persistence import schema
from eleanor.output.postgres.persistence.schema import (
    TABLES,
    declared_constraint_names,
    declared_index_names,
    verify_against_tables,
)


def test_declared_index_names_includes_every_index_def() -> None:
    expected = {(t.name, idx.name) for t in TABLES for idx in t.indexes}
    assert declared_index_names() == expected


def test_declared_constraint_names_includes_checks_and_fk_names() -> None:
    result = declared_constraint_names()
    for t in TABLES:
        for ck in t.checks:
            assert (t.name, ck.name) in result
        for fk in t.foreign_keys:
            fk_name = schema._fk_constraint_name(t.name, fk.column)
            assert (t.name, fk_name) in result


def test_columns_by_name_rekeys_inspect_schema_output() -> None:
    shape: dict[str, list[tuple[str, str, bool]]] = {
        "orders": [("id", "integer", False), ("name", "text", False)],
        "variable_space": [("id", "integer", False)],
    }
    result = schema._columns_by_name(shape)
    assert result == {
        "orders": {"id": ("integer", False), "name": ("text", False)},
        "variable_space": {"id": ("integer", False)},
    }


def test_verify_reports_missing_index_from_mocked_reader(mocker: MockerFixture) -> None:
    """Unit leg of the indisvalid coverage triangle (D3 in PLAN.md).

    Mock live_index_names to return a set missing one declared entry;
    assert verify_against_tables reports it as missing or invalid.
    """
    full_index_names = declared_index_names()
    assert full_index_names, "TABLES must have at least one index for this test"

    missing_entry = next(iter(full_index_names))
    reduced = full_index_names - {missing_entry}

    mocker.patch.object(schema, "live_index_names", return_value=reduced)
    mocker.patch.object(schema, "live_constraint_names", return_value=declared_constraint_names())
    mocker.patch.object(schema, "inspect_schema", return_value={})

    problems = verify_against_tables(mocker.MagicMock())

    _table_name, index_name = missing_entry
    assert any(index_name in p and "missing or invalid" in p for p in problems), (
        f"Expected drift message about {index_name!r}, got: {problems}"
    )
