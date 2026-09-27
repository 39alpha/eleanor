from psycopg import sql

from eleanor.output.postgres.persistence import schema


def _insert_columns(table: schema.TableDef) -> tuple[str, ...]:
    """Return the column names that go into an INSERT statement.

    Identity-PK columns are excluded so the DB autogenerates the id at INSERT
    time. Every other column is included, including FK columns and JSONB / BYTEA
    payloads.

    NOTE: Previous versions used INT/BIGINT identity columns. Those have been
          removed, but we continue to filter the identity columns to avoid
          including them if we decide to add some back in the future.
    """
    return tuple(c.name for c in table.columns if not c.identity)


def _build_insert(table: schema.TableDef, returning: bool = False) -> sql.SQL | sql.Composed:
    """Build a named-parameter INSERT for ``table``.

    With ``returning=True`` an ``INSERT ... RETURNING id`` is produced;
    callers consume the returned id (typically the FK fanout target for
    a follow-up bulk INSERT into a child table).
    """
    cols = _insert_columns(table)
    column_list = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
    placeholder_list = sql.SQL(", ").join(sql.Placeholder(c) for c in cols)
    statement: sql.SQL | sql.Composed = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({values})").format(
        table=sql.Identifier(table.name),
        cols=column_list,
        values=placeholder_list,
    )
    if returning:
        statement = sql.SQL("{insert} RETURNING {id}").format(
            insert=statement,
            id=sql.Identifier("id"),
        )
    return statement


INSERTS: dict[str, sql.SQL | sql.Composed] = {
    table.name: _build_insert(table, returning=False) for table in schema.TABLES
}


SELECT_ORDER: sql.SQL = sql.SQL("SELECT id, name, tags, eleanor_version, raw, create_date FROM orders WHERE id = %s")


SELECT_SCRATCH_ENTRY: sql.SQL = sql.SQL(
    "SELECT vs.id AS variable_space_id, vs.exit_code, sc.zip FROM variable_space AS vs LEFT JOIN scratch AS sc ON sc.id = vs.id WHERE vs.id = %s",
)


__all__ = [
    "INSERTS",
    "SELECT_ORDER",
    "SELECT_SCRATCH_ENTRY",
]
