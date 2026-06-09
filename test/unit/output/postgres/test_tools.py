"""Unit tests for the diagnostic helpers under :mod:`output.postgres.tools`.

These wrappers are tiny by design (CLIs glue around the persistence
layer), but coverage of their bodies pins down their public contracts:

* :func:`tools.schema.dump_schema` writes one ``CREATE TABLE``-plus-
  ``CREATE INDEX`` block per declared :class:`schema.TableDef` to the
  caller's stream, with a trailing semicolon on each statement.
* :func:`tools.scratch.load_scratch_entry` is a thin pass-through to
  :func:`repositories.get_scratch_entry`.
"""

import io
from unittest import TestCase, mock

from eleanor.output.postgres.persistence import schema
from eleanor.output.postgres.persistence.converters import ScratchEntry
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.output.postgres.tools.schema import dump_schema
from eleanor.output.postgres.tools.scratch import load_scratch_entry


class TestDumpSchema(TestCase):
    """Coverage of :func:`tools.schema.dump_schema`."""

    def test_dumps_create_table_and_index_for_every_declared_table(self) -> None:
        """
        Ensure every :class:`schema.TableDef` lands in the output as a
        ``CREATE TABLE IF NOT EXISTS`` followed by one ``CREATE INDEX``
        line per declared index. Statements terminate with a semicolon
        so the output is directly pipe-able into ``psql``.
        """
        cfg = PostgresDatabaseSettings(database="db", username="u", password="p")
        buf = io.StringIO()
        dump_schema(cfg, buf)
        output = buf.getvalue()

        for table in schema.TABLES:
            self.assertIn(f'CREATE TABLE IF NOT EXISTS "{table.name}"', output)
            for idx in table.indexes:
                self.assertIn(f'"{idx.name}"', output)

        # Each emitted statement has a trailing semicolon (the dump is
        # designed to be runnable without further processing).
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith(
                ("CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX")
            ):
                self.assertTrue(
                    stripped.endswith(";") or stripped.endswith("("),
                    f"statement {stripped!r} should end with semicolon or open paren",
                )

    def test_dump_schema_does_not_consult_database(self) -> None:
        """
        Ensure the dump is purely table-driven and never reaches into
        the persistence connection module: the helper is documented as
        producing static DDL that doesn't depend on any live database.
        """
        cfg = PostgresDatabaseSettings(database="db", username="u", password="p")
        buf = io.StringIO()
        with mock.patch(
            "eleanor.output.postgres.persistence.connection.connect",
        ) as connect:
            dump_schema(cfg, buf)
        connect.assert_not_called()


class TestLoadScratchEntry(TestCase):
    """Coverage of :func:`tools.scratch.load_scratch_entry`."""

    def test_delegates_to_repositories_get_scratch_entry(self) -> None:
        """
        Ensure :func:`load_scratch_entry` is a thin pass-through to
        :func:`repositories.get_scratch_entry` and forwards the active
        :class:`PostgresDatabaseSettings` and ``variable_space_id`` unchanged.
        """
        cfg = PostgresDatabaseSettings(database="db", username="u", password="p")
        entry = ScratchEntry(variable_space_id=11, exit_code=0, zip=b"payload")
        with mock.patch(
            "eleanor.output.postgres.tools.scratch.get_scratch_entry",
            return_value=entry,
        ) as get_scratch_entry:
            got = load_scratch_entry(cfg, 11)
        self.assertIs(got, entry)
        get_scratch_entry.assert_called_once_with(cfg, 11)
