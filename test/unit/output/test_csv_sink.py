import csv
import io
import os.path
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID
from unittest import TestCase, mock

import yaml
from eleanor.exceptions import EleanorError
from eleanor.kernel.settings import KernelSettings
from eleanor.order import Order
from eleanor.output import ComputeResult
from eleanor.output.csv import CsvSink, CsvSinkSettings, _binary_columns, _schema_path
from eleanor.output.interface import ErrorInfo
from eleanor.query import compile_query
from eleanor.variable_space import Point

_FAKE_KERNEL_SPEC = SimpleNamespace(
    settings_from_dict=mock.Mock(return_value=KernelSettings(timeout=None)),
    build=mock.Mock(),
)



def _write_batch(sink, order_id, results, progress=None):
    """Drive both halves of the split write protocol, as Eleanor does.

    ``prepare_batch`` (query evaluation) runs in a worker and ``commit_batch``
    (counter, assets, append, sidecar) in the parent, but for most tests the
    pair is one logical "write this batch".
    """
    prepared = sink.prepare_batch(order_id, results)
    return sink.commit_batch(order_id, prepared, progress=progress)

def _write_sidecar(
    filename: Path,
    query: dict[str, object],
    *,
    vs_points_seen: dict[str, int] | None = None,
    order_versions: dict[str, str] | None = None,
) -> None:
    """Helper to spell out the on-disk sidecar shape exactly once per change."""
    with open(_schema_path(filename), "w") as handle:
        yaml.safe_dump(
            {
                "query": query,
                "vs_points_seen": {} if vs_points_seen is None else vs_points_seen,
                "order_versions": {} if order_versions is None else order_versions,
            },
            handle,
            sort_keys=False,
        )


def _minimal_order() -> Order:
    with mock.patch(
        "eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC
    ):
        return Order.from_yamls(
            """
name: csv-order
notes: csv sink test
creator: test
kernel:
  kind: eq36
  model: b-dot
  charge_balance: H+
temperature: 25.0
pressure: 1.0
elements:
  Na: 1.0
"""
        )


def _query_exit_code() -> dict[str, object]:
    return {
        "row_scope": "vs_points[*]",
        "columns": [
            {"path": "vs_point.exit_code", "name": "exit_code"},
        ],
    }


def _settings(
    filename: Path,
    query: dict[str, object] | None = None,
    id_columns: list[str] | None = None,
) -> CsvSinkSettings:
    """Build settings that emit an ``order_id`` column, as most tests expect.

    ``order_id`` is a sink-owned identity column now, declared in settings
    rather than as a query path, so the header is ``id_columns + query
    columns``.
    """
    return CsvSinkSettings(
        filename=filename,
        query=_query_exit_code() if query is None else query,
        id_columns=["order_id"] if id_columns is None else id_columns,
    )


def _query_with_binary_column() -> dict[str, object]:
    return {
        "row_scope": "vs_points[*]",
        "columns": [
            {"path": "vs_point.exit_code", "name": "exit_code"},
            {"path": "vs_point.scratch.zip", "name": "scratch_zip"},
        ],
    }


def _query_without_order_id() -> dict[str, object]:
    return {
        "row_scope": "vs_points[*]",
        "columns": [
            {"path": "vs_point.exit_code", "name": "exit_code"},
        ],
    }


def _query_with_vs_index_column() -> dict[str, object]:
    return {
        "row_scope": "vs_points[*]",
        "columns": [
            {"path": "vs_point.@index", "name": "vs_index"},
            {"path": "vs_point.exit_code", "name": "exit_code"},
        ],
    }


def _point(*, exit_code: int = 0) -> Point:
    return cast(Point, cast(object, SimpleNamespace(exit_code=exit_code)))


class TestCsvSink(TestCase):
    def test_capabilities_report_csv_contract(self) -> None:
        """Ensure CSV sink opts out of worker writes and opts in to progress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            self.assertFalse(sink.supports_worker_commit())
            self.assertTrue(sink.supports_progress())

    def test_csv_config_validates_direct_constructor_and_from_dict(self) -> None:
        """Ensure CsvSinkSettings validates both direct construction and from_dict paths."""
        with self.assertRaisesRegex(EleanorError, "filename must be a Path"):
            _ = CsvSinkSettings(filename=1, query={})  # pyright: ignore[reportArgumentType]

        with self.assertRaisesRegex(EleanorError, "query must be a dictionary"):
            _ = CsvSinkSettings(filename=Path("x.csv"), query="bad")  # pyright: ignore[reportArgumentType]

        with self.assertRaisesRegex(EleanorError, "filename must be a str or Path"):
            _ = CsvSinkSettings.from_dict({"filename": 1})

        with self.assertRaisesRegex(EleanorError, "query must be a dictionary"):
            _ = CsvSinkSettings.from_dict({"filename": "x.csv"})

    def test_initialize_fresh_file_creates_header_and_schema_and_order_id(self) -> None:
        """Ensure initialize on a new CSV writes an empty sidecar and begin_run claims order id 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows, [["order_id", "exit_code"]])

            schema_file = _schema_path(filename)
            with open(schema_file) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["query"], _query_exit_code())
            self.assertEqual(schema["vs_points_seen"], {})
            self.assertEqual(schema["order_versions"], {})

            order = _minimal_order()
            order_id = sink.begin_run(order)
            self.assertIsInstance(order_id, UUID)
            with open(schema_file) as handle:
                schema_after_begin = yaml.safe_load(handle)
            self.assertEqual(schema_after_begin["vs_points_seen"], {str(order_id): 0})
            self.assertEqual(
                schema_after_begin["order_versions"],
                {str(order_id): order.eleanor_version},
            )

    def test_initialize_resets_sidecar_state_when_csv_deleted(self) -> None:
        """Ensure re-initialization after CSV deletion writes empty vs_points_seen and order_versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

            order = _minimal_order()
            order.eleanor_version = "v1"
            order_id = sink.begin_run(order)

            schema_file = _schema_path(filename)
            with open(schema_file) as handle:
                before = yaml.safe_load(handle)
            self.assertEqual(before["vs_points_seen"], {str(order_id): 0})
            self.assertEqual(before["order_versions"], {str(order_id): "v1"})

            os.remove(filename)
            os.remove(schema_file)
            sink.initialize()

            with open(schema_file) as handle:
                after = yaml.safe_load(handle)
            self.assertEqual(after["vs_points_seen"], {})
            self.assertEqual(after["order_versions"], {})

    def test_initialize_existing_matching_files_adds_a_new_run(self) -> None:
        """Ensure a fresh begin_run leaves an existing run's count alone.

        The new run gets its own UUID and a zero count; the run already in the
        sidecar keeps the count it had, so appending to a shared file never
        disturbs another run's numbering.
        """
        existing = "8c1cf4f0-c37f-4a2f-9a4d-6a5f4a0f1d2b"
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["order_id", "exit_code"])
                writer.writerow([existing, 0])
            _write_sidecar(filename, _query_exit_code(), vs_points_seen={existing: 1})

            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            with open(_schema_path(filename)) as handle:
                schema_after_init = yaml.safe_load(handle)
            self.assertEqual(schema_after_init["vs_points_seen"], {existing: 1})
            order = _minimal_order()
            order_id = sink.begin_run(order)
            self.assertNotEqual(str(order_id), existing)

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(
                schema["vs_points_seen"], {existing: 1, str(order_id): 0}
            )

    def test_initialize_existing_csv_without_schema_raises(self) -> None:
        """Ensure CSV-without-schema mismatch is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["order_id", "exit_code"])
            sink = CsvSink(
                _settings(filename)
            )
            with self.assertRaises(EleanorError):
                sink.initialize()

    def test_initialize_existing_header_mismatch_raises(self) -> None:
        """Ensure existing header names/order must match compiled query columns exactly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["exit_code", "order_id"])
            _write_sidecar(filename, _query_exit_code(), vs_points_seen={"run-a": 0})
            sink = CsvSink(
                _settings(filename)
            )
            with self.assertRaises(EleanorError):
                sink.initialize()

    def test_initialize_header_only_csv_with_sidecar_succeeds(self) -> None:
        """Ensure header-only existing CSV initializes when sidecar has a valid vs_points_seen mapping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["order_id", "exit_code"])
            _write_sidecar(filename, _query_exit_code(), vs_points_seen={})
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

    def test_initialize_uses_missing_vs_points_seen_as_empty_mapping(self) -> None:
        """Ensure sidecars without vs_points_seen are accepted as an empty mapping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["exit_code"])
                writer.writerow(["not-an-int"])
            with open(_schema_path(filename), "w") as handle:
                yaml.safe_dump(
                    {"query": _query_without_order_id()}, handle, sort_keys=False
                )
            sink = CsvSink(
                _settings(filename, _query_without_order_id(), id_columns=[])
            )
            sink.initialize()
            self.assertIsInstance(sink.begin_run(_minimal_order()), UUID)

    def test_initialize_rejects_invalid_vs_points_seen_shapes(self) -> None:
        """Ensure initialize rejects non-mapping or invalid-key/value vs_points_seen payloads."""
        cases: list[tuple[object, str]] = [
            ("not-a-mapping", "invalid vs_points_seen"),
            ({1: 0}, "invalid key"),
            ({"run-a": True}, "invalid count"),
        ]
        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                with tempfile.TemporaryDirectory() as tmpdir:
                    filename = Path(tmpdir) / "rows.csv"
                    with open(filename, "w", newline="") as handle:
                        csv.writer(handle).writerow(["order_id", "exit_code"])
                    with open(_schema_path(filename), "w") as handle:
                        yaml.safe_dump(
                            {
                                "query": _query_exit_code(),
                                "vs_points_seen": raw_value,
                            },
                            handle,
                            sort_keys=False,
                        )
                    sink = CsvSink(
                        _settings(filename)
                    )
                    with self.assertRaisesRegex(EleanorError, expected):
                        sink.initialize()

    def test_begin_run_stamps_order_fields_and_is_idempotent(self) -> None:
        """Ensure begin_run is idempotent per object and stamps fields for each new order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

            order = _minimal_order()
            first = sink.begin_run(order)
            second = sink.begin_run(order)
            self.assertEqual(first, second)

            supplied = _minimal_order()
            supplied.eleanor_version = "caller-version"
            other = sink.begin_run(supplied)
            self.assertNotEqual(other, first)
            self.assertEqual(supplied.eleanor_version, "caller-version")

    def test_begin_run_raises_on_version_mismatch_for_reused_order_id(self) -> None:
        """Ensure persisted sidecar versions reject reusing an order id with a different eleanor_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

            first = _minimal_order()
            first.eleanor_version = "v1"
            order_id = sink.begin_run(first)

            restarted = CsvSink(
                _settings(filename)
            )
            restarted.initialize()

            mismatch = _minimal_order()
            mismatch.eleanor_version = "v2"
            with self.assertRaisesRegex(
                EleanorError, "different version of Eleanor"
            ):
                _ = restarted.begin_run(mismatch, requested_id=str(order_id))

    def test_begin_run_issues_distinct_ids_for_distinct_orders(self) -> None:
        """Ensure distinct order objects each get their own id and counter entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

            first_order_id = sink.begin_run(_minimal_order())
            second_order_id = sink.begin_run(_minimal_order())
            self.assertNotEqual(first_order_id, second_order_id)

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(
                schema["vs_points_seen"],
                {str(first_order_id): 0, str(second_order_id): 0},
            )

    def test_begin_run_resumes_a_requested_id_from_the_sidecar(self) -> None:
        """Ensure a requested_id the sidecar knows resumes that run rather than starting one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            restarted = CsvSink(
                _settings(filename)
            )
            restarted.initialize()
            resumed = restarted.begin_run(
                _minimal_order(), requested_id=str(order_id)
            )

            self.assertEqual(resumed, order_id)

    def test_begin_run_rejects_an_unknown_or_malformed_requested_id(self) -> None:
        """Ensure only a run the sidecar records can be extended.

        A UUID this file has never seen would otherwise start a brand-new run
        under an id the caller believed already existed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

            unknown = "8c1cf4f0-c37f-4a2f-9a4d-6a5f4a0f1d2b"
            with self.assertRaisesRegex(EleanorError, "no order .* to extend"):
                _ = sink.begin_run(_minimal_order(), requested_id=unknown)

            with self.assertRaisesRegex(EleanorError, "must be a UUID"):
                _ = sink.begin_run(_minimal_order(), requested_id="42")

    def test_begin_run_before_initialize_writes_sidecar(self) -> None:
        """Ensure begin_run can persist sidecar state without initialize, but write_batch still requires initialize."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            order = _minimal_order()
            order_id = sink.begin_run(order)
            self.assertFalse(os.path.exists(filename))
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 0})
            result = ComputeResult(point=_point(exit_code=0))
            with self.assertRaisesRegex(EleanorError, "requires initialize\\(\\)"):
                _ = _write_batch(sink, order_id, [result])

    def test_write_batch_success_appends_rows_converts_none_and_ticks_progress(
        self,
    ) -> None:
        """Ensure write_batch appends rows, maps None->\"\", preserves points, and returns outcomes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order = _minimal_order()
            order_id = sink.begin_run(order)
            original_vs_points = order.vs_points

            r0 = ComputeResult(point=_point(exit_code=0))
            r1 = ComputeResult(point=_point(exit_code=5))
            progress = mock.Mock()
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter(
                        [
                            {"exit_code": None},
                            {"exit_code": 7},
                        ]
                    ),
                    iter([{"exit_code": 5}]),
                ],
            ):
                outcomes = _write_batch(sink, order_id, [r0, r1], progress=progress)

            self.assertEqual(len(outcomes), 2)
            self.assertTrue(all(outcome.committed for outcome in outcomes))
            self.assertEqual(outcomes[0].exit_code, 0)
            self.assertEqual(outcomes[1].exit_code, 5)
            self.assertEqual(progress.tick.call_count, 2)
            self.assertIs(order.vs_points, original_vs_points)

            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["order_id", "exit_code"])
            self.assertEqual(rows[1], [str(order_id), ""])
            self.assertEqual(rows[2], [str(order_id), "7"])
            self.assertEqual(rows[3], [str(order_id), "5"])
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 2})

    def test_write_batch_evaluates_each_point_against_order_copy(self) -> None:
        """Ensure each evaluate call receives a per-point Order shell, not the canonical Order object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order = _minimal_order()
            order_id = sink.begin_run(order)
            original_vs_points = order.vs_points

            r0 = ComputeResult(point=_point(exit_code=0))
            r1 = ComputeResult(point=_point(exit_code=5))
            expected_points = [r0.point, r1.point]
            seen_roots: list[Order] = []

            def _fake_evaluate(_compiled: object, root: Order):
                expected = expected_points[len(seen_roots)]
                self.assertIsNot(root, order)
                self.assertIs(order.vs_points, original_vs_points)
                self.assertEqual(order.vs_points, [])
                self.assertEqual(root.vs_points, [expected])
                seen_roots.append(root)
                return iter([{"exit_code": expected.exit_code}])

            with mock.patch("eleanor.output.csv.evaluate", side_effect=_fake_evaluate):
                outcomes = _write_batch(sink, order_id, [r0, r1])

            self.assertEqual(len(outcomes), 2)
            self.assertTrue(all(outcome.committed for outcome in outcomes))
            self.assertEqual(len(seen_roots), 2)
            self.assertIs(order.vs_points, original_vs_points)
            self.assertEqual(order.vs_points, [])

    def test_prepare_batch_failure_is_loud_and_isolated_to_its_point(
        self,
    ) -> None:
        """Ensure an evaluate failure is reported per point rather than aborting.

        Evaluation moved into ``prepare_batch``, which records a failure on
        that point's prepared item instead of raising, so the rest of the
        chunk still commits. The error is still loud on stderr, still yields a
        non-committed outcome, and still consumes no point id.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order = _minimal_order()
            order_id = sink.begin_run(order)
            original_vs_points = order.vs_points

            result = ComputeResult(point=_point(exit_code=3))
            captured = io.StringIO()
            with (
                mock.patch(
                    "eleanor.output.csv.evaluate", side_effect=RuntimeError("boom")
                ),
                mock.patch("eleanor.output.csv.sys.stderr", captured),
            ):
                outcomes = _write_batch(sink, order_id, [result])

            text = captured.getvalue()
            self.assertIn("VS point index 0", text)
            self.assertIn("RuntimeError", text)
            self.assertIn("boom", text)
            self.assertIn("Traceback", text)
            self.assertIs(order.vs_points, original_vs_points)

            self.assertEqual(len(outcomes), 1)
            self.assertFalse(outcomes[0].committed)
            self.assertIn("boom", outcomes[0].error_message or "")

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 0})
            self.assertNotEqual(sink.begin_run(_minimal_order()), order_id)

    def test_a_failing_point_does_not_discard_its_healthy_neighbours(
        self,
    ) -> None:
        """Ensure one bad point no longer costs the whole chunk its rows.

        Previously an evaluate failure propagated out of ``write_batch``,
        skipping the end-of-batch sidecar flush and leaving the healthy point's
        progress only in memory. Now the failure is confined to its own
        outcome, so the good point commits and the sidecar is flushed as usual.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            ok = ComputeResult(point=_point(exit_code=0))
            bad = ComputeResult(point=_point(exit_code=9))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"exit_code": 0}]),
                    RuntimeError("explode"),
                ],
            ):
                outcomes = _write_batch(sink, order_id, [ok, bad])

            self.assertTrue(outcomes[0].committed)
            self.assertFalse(outcomes[1].committed)
            self.assertIn("explode", outcomes[1].error_message or "")

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            # The healthy point's progress is now durable immediately, rather
            # than waiting for the next begin_run to flush it.
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 1})
            self.assertNotEqual(sink.begin_run(_minimal_order()), order_id)

    def test_id_columns_default_to_none_and_leave_the_header_to_the_query(self) -> None:
        """Ensure omitting id_columns emits no identity columns at all."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename, id_columns=[])
            )
            sink.initialize()
            with open(filename, newline="") as handle:
                self.assertEqual(next(csv.reader(handle)), ["exit_code"])
            self.assertIsInstance(sink.begin_run(_minimal_order()), UUID)

    def test_id_columns_are_rejected_when_unknown_or_duplicated(self) -> None:
        """Ensure only the names this sink can actually fill are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with self.assertRaisesRegex(EleanorError, "unknown id_columns"):
                _ = _settings(filename, id_columns=["run_id"])
            with self.assertRaisesRegex(EleanorError, "duplicate id_columns"):
                _ = _settings(filename, id_columns=["order_id", "order_id"])
            with self.assertRaisesRegex(EleanorError, "must be a list of strings"):
                _ = CsvSinkSettings(
                    filename=filename,
                    query=_query_exit_code(),
                    id_columns=cast("list[str]", [1]),
                )

    def test_id_columns_may_not_shadow_a_query_column(self) -> None:
        """Ensure a collision is refused rather than silently overwritten.

        The sink fills its id columns after evaluation, so a query column of
        the same name would lose its value with no indication why.
        """
        query = {
            "row_scope": "vs_points[*]",
            "columns": [{"path": "vs_point.exit_code", "name": "order_id"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with self.assertRaisesRegex(EleanorError, "collide with query column"):
                _ = CsvSink(_settings(filename, query))

    def test_csv_sink_is_importable_from_submodule(self) -> None:
        """Ensure CsvSink is accessible directly from eleanor.output.csv."""
        from eleanor.output.csv import CsvSink as sink_cls

        self.assertIsNotNone(sink_cls)

    def test_vs_points_seen_counter_is_per_order_not_global(self) -> None:
        """Ensure per-order ``vs_points_seen`` counters reset for each new order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()

            first_order = _minimal_order()
            first_order_id = sink.begin_run(first_order)
            r0 = ComputeResult(point=_point(exit_code=0))
            r1 = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"exit_code": 0}]),
                    iter([{"exit_code": 0}]),
                ],
            ):
                first_outcomes = _write_batch(sink, first_order_id, [r0, r1])

            second_order = _minimal_order()
            second_order_id = sink.begin_run(second_order)
            r2 = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"exit_code": 0}])],
            ):
                second_outcomes = _write_batch(sink, second_order_id, [r2])

            self.assertTrue(all(outcome.committed for outcome in first_outcomes))
            self.assertTrue(second_outcomes[0].committed)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(
                schema["vs_points_seen"],
                {str(first_order_id): 2, str(second_order_id): 1},
            )

    def test_write_batch_persists_advanced_vs_points_seen_for_order(self) -> None:
        """Ensure successful write_batch flushes the advanced per-order count to the sidecar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            r0 = ComputeResult(point=_point(exit_code=0))
            r1 = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"exit_code": 0}]),
                    iter([{"exit_code": 0}]),
                ],
            ):
                _ = _write_batch(sink, order_id, [r0, r1])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 2})

    def test_initialize_resumes_existing_order_count_from_sidecar(self) -> None:
        """Ensure a resumed run continues its persisted point count rather than restarting."""
        existing = "8c1cf4f0-c37f-4a2f-9a4d-6a5f4a0f1d2b"
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["order_id", "exit_code"])
            _write_sidecar(
                filename, _query_exit_code(), vs_points_seen={existing: 100}
            )

            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order(), requested_id=existing)
            self.assertEqual(str(order_id), existing)

            r0 = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"exit_code": 0}])],
            ):
                outcomes = _write_batch(sink, order_id, [r0])

            self.assertTrue(outcomes[0].committed)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {existing: 101})

    def test_initialize_rejects_non_int_or_bool_vs_points_seen_entries(self) -> None:
        """Ensure initialize rejects sidecars with non-int or bool order counters."""
        for bad_value, label in [
            ("not-an-int", "string"),
            (True, "bool"),
        ]:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    filename = Path(tmpdir) / "rows.csv"
                    with open(filename, "w", newline="") as handle:
                        csv.writer(handle).writerow(["order_id", "exit_code"])
                    with open(_schema_path(filename), "w") as handle:
                        yaml.safe_dump(
                            {
                                "query": _query_exit_code(),
                                "vs_points_seen": {"run-a": bad_value},
                            },
                            handle,
                            sort_keys=False,
                        )

                    sink = CsvSink(
                        _settings(filename)
                    )
                    with self.assertRaisesRegex(EleanorError, "invalid count"):
                        sink.initialize()

    def test_initialize_rejects_invalid_order_versions_shapes(self) -> None:
        """Ensure initialize rejects non-mapping or invalid-key/value order_versions payloads."""
        cases: list[tuple[object, str]] = [
            ("not-a-mapping", "invalid order_versions"),
            ({1: "v1"}, "invalid key"),
            ({"run-a": 5}, "invalid version"),
        ]
        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                with tempfile.TemporaryDirectory() as tmpdir:
                    filename = Path(tmpdir) / "rows.csv"
                    with open(filename, "w", newline="") as handle:
                        csv.writer(handle).writerow(["order_id", "exit_code"])
                    with open(_schema_path(filename), "w") as handle:
                        yaml.safe_dump(
                            {
                                "query": _query_exit_code(),
                                "vs_points_seen": {"run-a": 0},
                                "order_versions": raw_value,
                            },
                            handle,
                            sort_keys=False,
                        )

                    sink = CsvSink(
                        _settings(filename)
                    )
                    with self.assertRaisesRegex(EleanorError, expected):
                        sink.initialize()

    def test_write_batch_failure_after_empty_rows_keeps_order_count_unchanged(
        self,
    ) -> None:
        """Ensure empty evaluate output does not advance per-order counts across a later failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            # First result yields zero rows and does not consume the count;
            # second result raises in evaluate. Neither advances the counter.
            empty = ComputeResult(point=_point(exit_code=0))
            bad = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([]), RuntimeError("boom")],
            ):
                outcomes = _write_batch(sink, order_id, [empty, bad])

            self.assertFalse(outcomes[0].committed)
            self.assertFalse(outcomes[1].committed)

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 0})

    def test_write_batch_skips_errored_compute_result(self) -> None:
        """Ensure ``ComputeResult.error`` produces a non-committed outcome with no row, no tick, no id consumed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            errored = ComputeResult(
                point=_point(exit_code=0),
                error=ErrorInfo(
                    type_name="RuntimeError", message="worker died", traceback_text="tb"
                ),
            )
            progress = mock.Mock()
            with mock.patch("eleanor.output.csv.evaluate") as mocked_evaluate:
                outcomes = _write_batch(sink, order_id, [errored], progress=progress)

            self.assertEqual(len(outcomes), 1)
            self.assertEqual(outcomes[0].exit_code, -1)
            self.assertFalse(outcomes[0].committed)
            self.assertEqual(outcomes[0].error_message, "worker died")
            mocked_evaluate.assert_not_called()
            progress.tick.assert_not_called()

            # Only the header row exists in the CSV.
            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows, [["order_id", "exit_code"]])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 0})

    def test_write_batch_handles_mixed_errored_and_healthy_batch(self) -> None:
        """Ensure healthy results in a mixed batch get per-order ids and errored ones are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            ok0 = ComputeResult(point=_point(exit_code=0))
            errored = ComputeResult(
                point=_point(exit_code=0),
                error=ErrorInfo(
                    type_name="OSError", message="transport failed", traceback_text="tb"
                ),
            )
            ok1 = ComputeResult(point=_point(exit_code=0))
            progress = mock.Mock()
            # ``evaluate`` is only invoked for the two healthy results.
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"exit_code": 0}]),
                    iter([{"exit_code": 0}]),
                ],
            ) as mocked_evaluate:
                outcomes = _write_batch(sink, order_id, [ok0, errored, ok1], progress=progress)
            self.assertEqual([o.exit_code for o in outcomes], [0, -1, 0])
            self.assertEqual([o.committed for o in outcomes], [True, False, True])
            self.assertEqual(outcomes[1].error_message, "transport failed")
            self.assertEqual(mocked_evaluate.call_count, 2)
            # One tick per healthy result; the errored one is skipped.
            self.assertEqual(progress.tick.call_count, 2)

            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["order_id", "exit_code"])
            self.assertEqual(len(rows), 3)  # header + two healthy rows

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 2})

    def test_write_batch_does_not_advance_count_when_evaluate_returns_no_rows(
        self,
    ) -> None:
        """Ensure empty evaluate output yields an uncommitted outcome and does not consume a point id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename)
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            empty = ComputeResult(point=_point(exit_code=0))
            one_row = ComputeResult(point=_point(exit_code=0))
            progress = mock.Mock()
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([]),
                    iter([{"exit_code": 0}]),
                ],
            ):
                outcomes = _write_batch(sink, order_id, [empty, one_row], progress=progress)
            self.assertEqual([o.exit_code for o in outcomes], [0, 0])
            self.assertEqual([o.committed for o in outcomes], [False, True])
            self.assertEqual(progress.tick.call_count, 2)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {str(order_id): 1})

    def test_point_id_column_counts_points_within_the_run(self) -> None:
        """Ensure ``point_id`` numbers VS points per run, independent of row count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                _settings(filename, id_columns=["order_id", "point_id"])
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            first = ComputeResult(point=_point(exit_code=0))
            second = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    # Two rows for the first point: both carry its point_id.
                    iter([{"exit_code": 0}, {"exit_code": 0}]),
                    iter([{"exit_code": 0}]),
                ],
            ):
                outcomes = _write_batch(sink, order_id, [first, second])
            self.assertTrue(all(outcome.committed for outcome in outcomes))
            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["order_id", "point_id", "exit_code"])
            self.assertEqual(rows[1], [str(order_id), "0", "0"])
            self.assertEqual(rows[2], [str(order_id), "0", "0"])
            self.assertEqual(rows[3], [str(order_id), "1", "0"])

    def test_a_vs_point_index_column_is_rejected(self) -> None:
        """Ensure ``vs_point.@index`` is refused with a pointer to ``id_columns``.

        Evaluation happens one point at a time against a one-element
        ``vs_points``, so the path can only ever yield 0. It used to be
        silently overwritten with the sink's counter, which made the column
        disagree with the path that requested it.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with self.assertRaisesRegex(EleanorError, "id_columns: \\[point_id\\]"):
                _ = CsvSink(
                    _settings(filename, _query_with_vs_index_column())
                )

    def test_binary_columns_finds_bytes_terminals_only(self) -> None:
        """Ensure only ``bytes``-terminal columns are classified as binary."""
        compiled = compile_query(
            Order,
            {
                "row_scope": "vs_points[*]",
                "columns": [
                    {"path": "vs_point.scratch.zip", "name": "scratch_zip"},
                    {"path": "vs_point.exit_code", "name": "exit_code"},
                    {"path": "vs_point.@index", "name": "vs_index"},
                    {"path": "vs_point", "name": "point_scope"},
                ],
            },
            allow_container_terminals=True,
        )
        self.assertEqual(_binary_columns(compiled), frozenset({"scratch_zip"}))

    def test_initialize_creates_asset_directories(self) -> None:
        """Ensure initialize creates per-column asset directories for binary columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                CsvSinkSettings(filename=filename, query=_query_with_binary_column())
            )
            sink.initialize()
            self.assertTrue(os.path.isdir(f"{tmpdir}/scratch_zip"))

    def test_write_batch_extracts_binary_to_file_and_writes_path(self) -> None:
        """Ensure binary cells are written to disk and replaced with relative asset paths in CSV output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                CsvSinkSettings(filename=filename, query=_query_with_binary_column())
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            result = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"exit_code": 0, "scratch_zip": b"zip-bytes"}])],
            ):
                outcomes = _write_batch(sink, order_id, [result])

            self.assertTrue(outcomes[0].committed)
            asset_file = Path(tmpdir) / f"scratch_zip/{order_id}_0.zip"
            self.assertTrue(os.path.exists(asset_file))
            with open(asset_file, "rb") as handle:
                self.assertEqual(handle.read(), b"zip-bytes")
            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["exit_code", "scratch_zip"])
            self.assertEqual(
                rows[1], ["0", f"scratch_zip/{order_id}_0.zip"]
            )

    def test_write_batch_binary_none_writes_blank(self) -> None:
        """Ensure None-valued binary cells remain blank and do not emit files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                CsvSinkSettings(filename=filename, query=_query_with_binary_column())
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            result = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"exit_code": 0, "scratch_zip": None}])],
            ):
                outcomes = _write_batch(sink, order_id, [result])

            self.assertTrue(outcomes[0].committed)
            self.assertFalse(
                os.path.exists(f"{tmpdir}/scratch_zip/{order_id}_0.zip")
            )
            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ["0", ""])

    def test_initialize_resume_creates_asset_directories(self) -> None:
        """Ensure initialize on an existing CSV with binary columns creates per-column asset directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["exit_code", "scratch_zip"])
            _write_sidecar(
                filename, _query_with_binary_column(), vs_points_seen={"run-a": 1}
            )
            sink = CsvSink(
                CsvSinkSettings(filename=filename, query=_query_with_binary_column())
            )
            sink.initialize()
            self.assertTrue(os.path.isdir(f"{tmpdir}/scratch_zip"))

    def test_binary_asset_naming_uses_order_and_point_counter(self) -> None:
        """Ensure extracted binary file names follow <column>/<order_id>_<point_counter>.zip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                CsvSinkSettings(filename=filename, query=_query_with_binary_column())
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            first = ComputeResult(point=_point(exit_code=0))
            second = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"exit_code": 0, "scratch_zip": b"one"}]),
                    iter([{"exit_code": 0, "scratch_zip": b"two"}]),
                ],
            ):
                outcomes = _write_batch(sink, order_id, [first, second])

            self.assertTrue(all(outcome.committed for outcome in outcomes))
            self.assertTrue(
                os.path.exists(f"{tmpdir}/scratch_zip/{order_id}_0.zip")
            )
            self.assertTrue(
                os.path.exists(f"{tmpdir}/scratch_zip/{order_id}_1.zip")
            )
            with open(f"{tmpdir}/scratch_zip/{order_id}_0.zip", "rb") as handle:
                self.assertEqual(handle.read(), b"one")
            with open(f"{tmpdir}/scratch_zip/{order_id}_1.zip", "rb") as handle:
                self.assertEqual(handle.read(), b"two")

    def test_write_batch_binary_multi_row_uses_row_suffix(self) -> None:
        """Ensure multi-row binary outputs for one point use a row-index suffix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = Path(tmpdir) / "rows.csv"
            sink = CsvSink(
                CsvSinkSettings(filename=filename, query=_query_with_binary_column())
            )
            sink.initialize()
            order_id = sink.begin_run(_minimal_order())

            result = ComputeResult(point=_point(exit_code=0))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter(
                        [
                            {"exit_code": 0, "scratch_zip": b"first"},
                            {"exit_code": 0, "scratch_zip": b"second"},
                        ]
                    )
                ],
            ):
                outcomes = _write_batch(sink, order_id, [result])

            self.assertTrue(outcomes[0].committed)
            self.assertTrue(
                os.path.exists(f"{tmpdir}/scratch_zip/{order_id}_0_0.zip")
            )
            self.assertTrue(
                os.path.exists(f"{tmpdir}/scratch_zip/{order_id}_0_1.zip")
            )
