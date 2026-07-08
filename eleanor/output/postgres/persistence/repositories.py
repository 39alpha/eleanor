from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import cast

import numpy as np
import psycopg
from psycopg import sql

import eleanor.equilibrium_space as core_es
import eleanor.variable_space as core_vs
from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output import ErrorInfo
from eleanor.output.postgres.persistence import connection, converters, migrations, queries, schema
from eleanor.output.postgres.persistence.converters import OrderRecord, ScratchEntry
from eleanor.output.postgres.settings import PostgresDatabaseSettings, PostgresSinkSettings


def setup_schema(config: PostgresDatabaseSettings) -> None:
    """Idempotently create the sink's schema on the configured DB."""
    conn = connection.connect(config)
    schema.ensure_schema(conn)


def apply_pending_migrations(config: PostgresDatabaseSettings) -> None:
    """:class:`PostgresDatabaseSettings`-keyed wrapper around :func:`migrations.apply_pending_migrations`.

    Matches the shape of :func:`setup_schema`, :func:`drop_bulk_load_objects`, etc.
    """
    conn = connection.connect(config)
    migrations.apply_pending_migrations(conn)


def drop_bulk_load_objects(config: PostgresDatabaseSettings, targets: schema.BulkLoadTargets | None = None) -> None:
    """:class:`PostgresDatabaseSettings`-keyed wrapper around :func:`schema.drop_bulk_load_objects`.

    Acquires the process-local connection for ``config`` and delegates;
    no transactional shape of its own (the schema helper opens its own
    transaction internally). ``targets`` selects which object classes to drop.
    """
    conn = connection.connect(config)
    schema.drop_bulk_load_objects(conn, targets)


def recreate_bulk_load_objects(config: PostgresDatabaseSettings, targets: schema.BulkLoadTargets | None = None) -> None:
    """:class:`PostgresDatabaseSettings`-keyed wrapper around :func:`schema.recreate_bulk_load_objects`.

    Acquires the process-local connection for ``config`` and delegates;
    transactional shape is handled by the schema helper. ``targets`` selects
    which object classes to recreate.
    """
    conn = connection.connect(config)
    schema.recreate_bulk_load_objects(conn, targets)


@contextmanager
def bulk_load_window(
    config: PostgresDatabaseSettings, targets: schema.BulkLoadTargets | None = None
) -> Generator[None]:
    """:class:`PostgresDatabaseSettings`-keyed wrapper around :func:`schema.bulk_load_window`.

    Yields once after the drop has committed; recreates the constraints
    when the body returns (or in :keyword:`finally` if the body raises).
    ``targets`` selects which object classes the window drops and recreates.
    """
    conn = connection.connect(config)
    with schema.bulk_load_window(conn, targets):
        yield


def _passes_filter(value: np.float64, threshold: float, write_unformed: bool) -> bool:
    """Return True when ``value`` should be written to the database.

    The condition ``(write_unformed or value > -inf) and value >= threshold``
    has two axes:

    * Unformed values (``-inf``): included only when ``write_unformed`` is
      ``True`` *and* ``threshold`` is ``-inf`` (the default).  A finite
      ``threshold`` excludes ``-inf`` values unconditionally because
      ``-inf >= finite_threshold`` is always ``False``.
    * Finite values: included when ``value >= threshold``, regardless of
      ``write_unformed``.
    * NaN values are always excluded: both ``nan > -inf`` and
      ``nan >= threshold`` return ``False`` under IEEE 754, so no
      special-casing is needed.
    """
    return bool((write_unformed or value > np.float64(-np.inf)) and value >= threshold)


# Postgres' wire protocol caps the number of bind parameters per statement.
# The header field is technically signed int16 (32 767), but libpq accepts
# up to uint16 (65 535) in practice. We pick a number with comfortable
# headroom under the practical ceiling so a row whose width slightly
# exceeds our planned chunk-size estimate doesn't wrap around.
_MAX_BIND_PARAMS_PER_STATEMENT: int = 60_000

# Threshold above which :func:`_bulk_insert` switches from ``executemany``
# to binary ``COPY FROM STDIN``. COPY pays a small fixed handshake cost in
# exchange for skipping the per-row planner / rewriter pass, so it only
# wins on "large" batches. Around a thousand rows is the rough local-PG
# break-even point on the ES-side leaf tables we pool most aggressively.
_COPY_ROW_THRESHOLD: int = 1_000

# Map of the SQL types the schema declares to psycopg3's binary type names.
# Used by :func:`_bulk_copy` to pin the column types passed to
# :meth:`psycopg.copy.Copy.set_types`. Without this, psycopg falls back to
# inferring a type from each Python value -- and Python ``int`` infers as
# ``int8`` (BIGINT), so an ``INTEGER`` (int4) column like
# ``equilibrium_space_id`` blows up the binary COPY stream with a
# ``ProtocolViolation: insufficient data left in message``. Pinning the
# types from the static schema avoids that whole class of failure and
# also makes Jsonb / TIMESTAMP / BYTEA encodings explicit.
_COPY_PG_TYPE_BY_SQL_TYPE: dict[str, str] = {
    "INTEGER": "int4",
    "TEXT": "text",
    "DOUBLE PRECISION": "float8",
    "TIMESTAMP": "timestamp",
    "BYTEA": "bytea",
    "JSONB": "jsonb",
}


def _bulk_insert(
    cursor: psycopg.Cursor,
    table_name: str,
    rows: list[dict[str, object]],
) -> None:
    """Bulk-insert ``rows`` into ``table_name``; no-op if empty.

    Below :data:`_COPY_ROW_THRESHOLD`, this uses the named-parameter
    INSERT template from :mod:`queries` via ``executemany``. At or above
    the threshold it switches to binary ``COPY FROM STDIN``, which is
    substantially faster on the large pooled leaf tables because it
    avoids the per-row planner / rewriter overhead of repeated INSERTs.

    The helper is only for tables whose autogenerated ids are irrelevant
    to the caller. Fan-out paths that need ids back use
    :func:`_bulk_insert_returning_ids` instead.
    """
    if not rows:
        return
    if len(rows) >= _COPY_ROW_THRESHOLD:
        _bulk_copy(cursor, table_name, rows)
        return
    _ = cursor.executemany(queries.INSERTS[table_name], rows)


def _bulk_copy(
    cursor: psycopg.Cursor,
    table_name: str,
    rows: list[dict[str, object]],
) -> None:
    """Stream ``rows`` into ``table_name`` via binary ``COPY FROM STDIN``.

    Binary format is chosen so psycopg3's registered adapters continue to
    handle ``Jsonb`` payloads, ``datetime`` values, ``bytes`` / ``BYTEA``,
    and ``-math.inf`` / ``DOUBLE PRECISION`` without per-table
    special-casing. The row dict key order becomes the COPY column order,
    matching the uniform-row-shape contract the existing ``executemany``
    path already relies on.

    COPY has no ``RETURNING`` clause, so this helper is intentionally
    limited to the fire-and-forget leaf tables routed through
    :func:`_bulk_insert`.
    """
    if not rows:
        return
    columns = tuple(rows[0].keys())
    column_list = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    statement = sql.SQL("COPY {table} ({cols}) FROM STDIN WITH (FORMAT BINARY)").format(
        table=sql.Identifier(table_name),
        cols=column_list,
    )
    sql_type_by_column = {c.name: c.sql_type for c in schema.TABLES_BY_NAME[table_name].columns}
    pg_types = [_COPY_PG_TYPE_BY_SQL_TYPE[sql_type_by_column[c]] for c in columns]
    with cursor.copy(statement) as cp:
        cp.set_types(pg_types)
        for row in rows:
            cp.write_row(tuple(row[c] for c in columns))


def _bulk_insert_returning_ids(
    cursor: psycopg.Cursor,
    table_name: str,
    rows: list[dict[str, object]],
) -> list[int]:
    """Bulk-insert ``rows`` and return the autogenerated ids in input order.

    Builds explicit multi-row ``INSERT INTO t (cols) VALUES (...), (...),
    ... RETURNING id`` statements and executes them via plain
    :meth:`Cursor.execute`. This is intentional: psycopg3's
    ``executemany(returning=True)`` activates pipeline mode internally
    on PG >= 14, and the per-result-set / pgresult bookkeeping that
    surfaces the returned rows interacts badly with subsequent
    ``executemany`` calls on the same cursor inside a savepoint --
    the pipeline aborts and downstream leaf-table INSERTs silently fail.
    Plain :meth:`execute` keeps the cursor in a single, well-defined
    state with no pipeline involvement.

    The rows are split into chunks bounded by
    :data:`_MAX_BIND_PARAMS_PER_STATEMENT` so we never approach
    Postgres' ~65 535 bind-parameter ceiling regardless of how many rows
    a caller pools. Ids are concatenated in input order across chunks so
    callers like :func:`_insert_es_subtree` can keep using
    ``zip(ids, end_member_lists)`` to fan ids out to children.
    """
    if not rows:
        return []
    columns = tuple(rows[0].keys())
    chunk_size = max(1, _MAX_BIND_PARAMS_PER_STATEMENT // len(columns))
    ids: list[int] = []
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        statement = _build_multi_row_insert_returning_id(table_name, columns, len(chunk))
        flat_params = [row[column] for row in chunk for column in columns]
        _ = cursor.execute(statement, flat_params)
        ids.extend(cast(int, fetched[0]) for fetched in cursor.fetchall())
    return ids


def _build_multi_row_insert_returning_id(
    table_name: str,
    columns: tuple[str, ...],
    row_count: int,
) -> sql.Composed:
    """Compose a single ``INSERT INTO t (cols) VALUES (...), ... RETURNING id`` statement.

    The statement is unique per ``(table, column-set, row_count)`` triple
    so prepared-statement caching is less effective than ``executemany``
    would be, but the savings would be irrelevant: the cost we just
    avoided (the pipeline-mode interaction) is much larger than the
    statement-prepare overhead we're paying here.
    """
    column_list = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    one_row = sql.SQL("({values})").format(
        values=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    rows_sql = sql.SQL(", ").join(one_row for _ in range(row_count))
    return sql.SQL("INSERT INTO {table} ({cols}) VALUES {rows} RETURNING {id}").format(
        table=sql.Identifier(table_name),
        cols=column_list,
        rows=rows_sql,
        id=sql.Identifier("id"),
    )


def insert_order(config: PostgresDatabaseSettings, order: Order) -> OrderRecord:
    """Insert ``order`` into the orders table and return the persisted record."""
    conn = connection.connect(config)
    row = converters.order_to_row(order)
    with conn.transaction(), conn.cursor() as cur:
        _ = cur.execute(queries.INSERTS_RETURNING_ID["orders"], row)
        result = cur.fetchone()
        if result is None:
            msg = "order INSERT did not return an id"
            raise EleanorError(msg)
        new_id = cast(int, result[0])

    return OrderRecord(
        id=new_id,
        name=order.name,
        tags=order.tags,
        eleanor_version=order.eleanor_version,
        raw=converters.normalize_dict(order, "order"),
        create_date=order.create_date,
    )


def get_order(config: PostgresDatabaseSettings, order_id: int) -> OrderRecord | None:
    """Fetch the orders row for ``order_id``, or ``None`` if absent."""
    conn = connection.connect(config)
    with conn.cursor() as cur:
        _ = cur.execute(queries.SELECT_ORDER, (order_id,))
        row = cur.fetchone()
    if row is None:
        return None
    return OrderRecord(
        id=cast(int, row[0]),
        name=cast(str, row[1]),
        tags=cast(list[str], row[2]),
        eleanor_version=cast(str, row[3]),
        raw=cast(dict[str, object], row[4]),
        create_date=cast(datetime, row[5]),
    )


def insert_point(
    connection_obj: psycopg.Connection,
    order_id: int,
    point: core_vs.Point,
    error: ErrorInfo | None = None,
    settings: PostgresSinkSettings | None = None,
) -> int:
    """Insert ``point`` and every descendant; return the new variable_space id.

    Caller is responsible for the transactional shape: the sink wraps
    each call in a per-VS-point ``connection.transaction(savepoint_name=...)``
    inside the batch's outer transaction, so a single bad row only rolls
    back that one VS point's savepoint and the rest of the batch still
    commits.
    """
    with connection_obj.cursor() as cur:
        # 1. variable_space + paired single-row tables (kernel, scratch).
        vs_id = _insert_variable_space_and_pair(cur, point, order_id, error)

        # 2. VS-side leaf collections + their nested children.
        _insert_vs_side_leaves(cur, vs_id, point)

        # 3. equilibrium_space + ES-side leaf collections, pooled across
        #    ES points (the Level 2 win on the dominant tables).
        if point.es_points:
            _insert_es_subtree(cur, vs_id, point.es_points, settings)

        return vs_id


def _insert_variable_space_and_pair(
    cur: psycopg.Cursor,
    point: core_vs.Point,
    order_id: int,
    error: ErrorInfo | None = None,
) -> int:
    """Insert variable_space row + its paired kernel + (optional) scratch."""
    vs_row = converters.vs_point_to_row(point, error, order_id)
    _ = cur.execute(queries.INSERTS_RETURNING_ID["variable_space"], vs_row)
    result = cur.fetchone()
    if result is None:
        msg = "variable_space INSERT did not return an id"
        raise EleanorError(msg)
    vs_id = cast(int, result[0])

    _ = cur.execute(queries.INSERTS["kernel"], converters.kernel_to_row(point.kernel, vs_id))
    if point.scratch is not None:
        _ = cur.execute(
            queries.INSERTS["scratch"],
            converters.scratch_to_row(point.scratch, vs_id),
        )
    return vs_id


def _insert_vs_side_leaves(
    cur: psycopg.Cursor,
    vs_id: int,
    point: core_vs.Point,
) -> None:
    """Bulk-insert every VS-side leaf collection and its nested children."""
    # Plain leaf tables (parent FK only, no nested children).
    _bulk_insert(
        cur,
        "elements",
        [converters.element_to_row(e, vs_id) for e in point.elements],
    )
    _bulk_insert(
        cur,
        "species",
        [converters.species_to_row(s, vs_id) for s in point.species],
    )
    _bulk_insert(
        cur,
        "mineral_reactants",
        [converters.mineral_reactant_to_row(r, vs_id) for r in point.mineral_reactants],
    )
    _bulk_insert(
        cur,
        "aqueous_reactants",
        [converters.aqueous_reactant_to_row(r, vs_id) for r in point.aqueous_reactants],
    )
    _bulk_insert(
        cur,
        "gas_reactants",
        [converters.gas_reactant_to_row(r, vs_id) for r in point.gas_reactants],
    )
    _bulk_insert(
        cur,
        "element_reactants",
        [converters.element_reactant_to_row(r, vs_id) for r in point.element_reactants],
    )
    _bulk_insert(
        cur,
        "fixed_gas_reactants",
        [converters.fixed_gas_reactant_to_row(r, vs_id) for r in point.fixed_gas_reactants],
    )

    # suppressions -> suppression_exceptions
    if point.suppressions:
        sup_rows = [converters.suppression_to_row(s, vs_id) for s in point.suppressions]
        sup_ids = _bulk_insert_returning_ids(cur, "suppressions", sup_rows)
        ex_rows = [
            converters.suppression_exception_to_row(ex, sup_id)
            for sup_id, sup in zip(sup_ids, point.suppressions, strict=True)
            for ex in sup.exceptions
        ]
        _bulk_insert(cur, "suppression_exceptions", ex_rows)

    # special_reactants -> special_reactant_compositions
    if point.special_reactants:
        sr_rows = [converters.special_reactant_to_row(r, vs_id) for r in point.special_reactants]
        sr_ids = _bulk_insert_returning_ids(cur, "special_reactants", sr_rows)
        sr_comp_rows = [
            converters.special_reactant_composition_to_row(comp, sr_id)
            for sr_id, sr in zip(sr_ids, point.special_reactants, strict=True)
            for comp in sr.composition
        ]
        _bulk_insert(cur, "special_reactant_compositions", sr_comp_rows)

    # solid_solution_reactants -> solid_solution_reactant_end_members
    if point.solid_solution_reactants:
        ssr_rows = [converters.solid_solution_reactant_to_row(r, vs_id) for r in point.solid_solution_reactants]
        ssr_ids = _bulk_insert_returning_ids(cur, "solid_solution_reactants", ssr_rows)
        em_rows = [
            converters.solid_solution_reactant_end_member_to_row(em, ssr_id)
            for ssr_id, ssr in zip(ssr_ids, point.solid_solution_reactants, strict=True)
            for em in ssr.end_members
        ]
        _bulk_insert(cur, "solid_solution_reactant_end_members", em_rows)


def _insert_es_subtree(
    cur: psycopg.Cursor,
    vs_id: int,
    es_points: list[core_es.Point],
    settings: PostgresSinkSettings | None = None,
) -> None:
    """Insert every ES point + its leaf children, pooled across ES points.

    The pooling is the Level 2 optimisation we landed earlier: leaf tables
    like ``equilibrium_aqueous_species`` collapse from one INSERT per ES
    point to one INSERT per VS point regardless of how many ES points
    contributed. That is the headline win on representative profiles.
    """
    # 1. Bulk-insert parent equilibrium_space rows, RETURNING id in input order.
    es_parent_rows = [converters.es_point_to_row(es, vs_id) for es in es_points]
    es_ids = _bulk_insert_returning_ids(cur, "equilibrium_space", es_parent_rows)

    # 2. Pool each leaf collection across all ES points so we emit at most
    #    one INSERT per leaf table for the whole VS point.
    elements_rows: list[dict[str, object]] = []
    aqueous_rows: list[dict[str, object]] = []
    pure_solid_rows: list[dict[str, object]] = []
    gas_rows: list[dict[str, object]] = []
    reactant_rows: list[dict[str, object]] = []
    redox_rows: list[dict[str, object]] = []
    ss_rows: list[dict[str, object]] = []
    # Parallel to ``ss_rows``; filled after the solid_solutions INSERT
    # returns ids so we can fan them out as the FK on end_members.
    end_member_lists: list[list[core_es.EndMember]] = []

    write_unformed: bool = settings.write_unformed if settings is not None else True
    min_log_moles: float = settings.min_log_moles if settings is not None else float("-inf")
    min_log_molality: float = settings.min_log_molality if settings is not None else float("-inf")
    min_log_fugacity: float = settings.min_log_fugacity if settings is not None else float("-inf")

    for es_id, es in zip(es_ids, es_points, strict=True):
        elements_rows.extend(converters.es_element_to_row(el, es_id) for el in es.elements)
        aqueous_rows.extend(
            converters.es_aqueous_species_to_row(sp, es_id)
            for sp in es.aqueous_species
            if _passes_filter(sp.log_molality, min_log_molality, write_unformed)
        )
        pure_solid_rows.extend(
            converters.es_pure_solid_to_row(ps, es_id)
            for ps in es.pure_solids
            if _passes_filter(
                ps.log_moles if ps.log_moles is not None else np.float64(-np.inf),
                min_log_moles,
                write_unformed,
            )
        )
        gas_rows.extend(
            converters.es_gas_to_row(g, es_id)
            for g in es.gases
            if _passes_filter(g.log_fugacity, min_log_fugacity, write_unformed)
        )
        reactant_rows.extend(converters.es_reactant_to_row(r, es_id) for r in es.reactants)
        redox_rows.extend(converters.es_redox_reaction_to_row(rr, es_id) for rr in es.redox_reactions)

        filtered_ss = [
            ss
            for ss in es.solid_solutions
            if _passes_filter(
                ss.log_moles if ss.log_moles is not None else np.float64(-np.inf),
                min_log_moles,
                write_unformed,
            )
        ]
        ss_rows.extend(converters.es_solid_solution_to_row(ss, es_id) for ss in filtered_ss)
        end_member_lists.extend(list(ss.end_members) for ss in filtered_ss)

    # 3. Single executemany per leaf table.
    _bulk_insert(cur, "equilibrium_elements", elements_rows)
    _bulk_insert(cur, "equilibrium_aqueous_species", aqueous_rows)
    _bulk_insert(cur, "equilibrium_pure_solids", pure_solid_rows)
    _bulk_insert(cur, "equilibrium_gases", gas_rows)
    _bulk_insert(cur, "equilibrium_reactants", reactant_rows)
    _bulk_insert(cur, "equilibrium_redox_reactions", redox_rows)

    # 4. Solid solutions need their ids fanned out to end_members.
    if ss_rows:
        ss_ids = _bulk_insert_returning_ids(cur, "equilibrium_solid_solutions", ss_rows)
        em_rows = [
            converters.es_end_member_to_row(em, ss_id)
            for ss_id, em_list in zip(ss_ids, end_member_lists, strict=True)
            for em in em_list
        ]
        _bulk_insert(cur, "equilibrium_end_members", em_rows)


def get_scratch_entry(
    config: PostgresDatabaseSettings,
    variable_space_id: int,
) -> ScratchEntry | None:
    """Fetch the persisted scratch payload for ``variable_space_id``.

    Returns ``None`` when the variable-space point does not exist. Raises
    :class:`LookupError` with ``'scratch'`` when the point exists but has
    no scratch row, so CLI callers can distinguish the two cases and
    preserve the historical error messages.
    """
    conn = connection.connect(config)
    with conn.cursor() as cur:
        _ = cur.execute(queries.SELECT_SCRATCH_ENTRY, (variable_space_id,))
        row = cur.fetchone()
    if row is None:
        return None
    if row[2] is None:
        msg = "scratch"
        raise LookupError(msg)
    return ScratchEntry(
        variable_space_id=cast(int, row[0]),
        exit_code=cast(int, row[1]),
        zip=cast(bytes, row[2]),
    )


__all__ = [
    "bulk_load_window",
    "drop_bulk_load_objects",
    "get_order",
    "get_scratch_entry",
    "insert_order",
    "insert_point",
    "recreate_bulk_load_objects",
    "setup_schema",
]
