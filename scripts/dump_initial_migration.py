"""Emit the initial schema migration SQL from the current TABLES definition.

Run this script to regenerate ``0001_initial_schema.sql`` if the canonical
DDL helpers change. The output captures what ``schema.ensure_schema`` does:
CREATE TABLE for every table in TABLES (in TABLES order), then CREATE INDEX
for every index declared on those tables. Foreign keys are inlined in the
CREATE TABLE statement by ``to_create_table_sql``; do not re-emit them here.

See PLAN.md §D1 for why this script is committed rather than thrown away.
"""

import sys

from eleanor.output.postgres.persistence.schema import (
    TABLES,
    to_create_index_sql,
    to_create_table_sql,
)

lines: list[str] = []

for t in TABLES:
    lines.append(to_create_table_sql(t) + ";\n")

for t in TABLES:
    for idx in t.indexes:
        lines.append(to_create_index_sql(t, idx) + ";\n")

_ = sys.stdout.write("\n".join(lines))
if lines:
    _ = sys.stdout.write("\n")
