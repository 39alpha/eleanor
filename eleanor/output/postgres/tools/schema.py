"""Diagnostic helper: dump the postgres sink's schema to a stream.

The sink keeps its schema as plain :class:`TableDef` objects, so dumping
is just a loop over :data:`schema.TABLES` calling the DDL emitter. No DB
connection is required.
"""

from typing import TextIO

from ..config import DatabaseConfig
from ..persistence import schema


def dump_schema(config: DatabaseConfig, stream: TextIO) -> None:
    """Print every ``CREATE TABLE`` and ``CREATE INDEX`` statement to ``stream``.

    ``config`` is unused -- kept for compatibility with the previous
    signature so external CLIs that pass a ``DatabaseConfig`` keep
    working without change. The schema is static and identical across
    DBs the sink targets.
    """
    _ = config  # signature compatibility; the schema is static.
    for table in schema.TABLES:
        print(schema.to_create_table_sql(table) + ";", file=stream)
        for idx in table.indexes:
            print(schema.to_create_index_sql(table, idx) + ";", file=stream)
