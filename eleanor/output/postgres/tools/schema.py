from typing import TextIO

from eleanor.output.postgres.persistence import schema


def dump_schema(stream: TextIO) -> None:
    """Print every ``CREATE TABLE`` and ``CREATE INDEX`` statement to ``stream``."""
    for table in schema.TABLES:
        print(schema.to_create_table_sql(table) + ";", file=stream)
        for idx in table.indexes:
            print(schema.to_create_index_sql(table, idx) + ";", file=stream)


__all__ = ["dump_schema"]
