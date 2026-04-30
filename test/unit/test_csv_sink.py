import csv
import io
import tempfile
import warnings
from types import SimpleNamespace
from unittest import mock

import yaml

from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.order import Order
from eleanor.output import ComputeResult
from eleanor.output import _build_csv
from eleanor.output.interface import ErrorInfo
from eleanor.output.csv.config import CsvConfig
from eleanor.output.csv.sink import CsvSink, _find_order_id_column, _schema_path
from eleanor.query import compile_query

from .common import TestCase


def _write_sidecar(
    filename: str,
    query: dict[str, object],
    *,
    next_order_id: int = 1,
    next_vs_point_id: int = 1,
) -> None:
    """Helper to spell out the on-disk sidecar shape exactly once per change."""
    with open(_schema_path(filename), "w") as handle:
        yaml.safe_dump(
            {
                "query": query,
                "next_order_id": next_order_id,
                "next_vs_point_id": next_vs_point_id,
            },
            handle,
            sort_keys=False,
        )


def _minimal_order() -> Order:
    return Order.from_yamls(
        """
name: csv-order
notes: csv sink test
creator: test
"""
    )


def _query_with_order_id() -> dict[str, object]:
    return {
        "row_scope": "vs_points[*]",
        "columns": [
            {"path": "order.id", "name": "order_id"},
            {"path": "vs_point.exit_code", "name": "exit_code"},
        ],
    }


def _query_without_order_id() -> dict[str, object]:
    return {
        "row_scope": "vs_points[*]",
        "columns": [
            {"path": "vs_point.exit_code", "name": "exit_code"},
        ],
    }


class TestCsvSink(TestCase):
    def test_capabilities_report_csv_contract(self):
        """Ensure CSV sink opts out of worker writes and opts in to progress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            self.assertFalse(sink.supports_worker_writes())
            self.assertTrue(sink.supports_progress())

    def test_build_csv_returns_sink_and_warns_on_unknown_kwargs(self):
        """Ensure _build_csv constructs CsvSink and warns once per build, listing only unknown kwargs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            query = _query_with_order_id()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                # ``verbose`` is an Eleanor-level kwarg the loader always
                # supplies; passing it must NOT trip the unknown-kwarg warning.
                # ``ignored_a`` and ``ignored_b`` must both surface in the
                # warning message, sorted, and produce exactly one warning.
                sink = _build_csv(
                    object(),
                    filename=filename,
                    query=query,
                    verbose=True,
                    ignored_b=True,
                    ignored_a=True,
                )
            self.assertIsInstance(sink, CsvSink)
            runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
            self.assertEqual(len(runtime_warnings), 1)
            message = str(runtime_warnings[0].message)
            self.assertIn("['ignored_a', 'ignored_b']", message)
            self.assertNotIn("verbose", message)
            self.assertNotIn("filename", message)
            self.assertNotIn("query", message)

    def test_build_csv_does_not_warn_when_only_known_kwargs_passed(self):
        """Ensure no RuntimeWarning is emitted when only ``filename``/``query``/``verbose`` are supplied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                _ = _build_csv(object(), filename=filename, query=_query_with_order_id(), verbose=False)
            runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
            self.assertEqual(runtime_warnings, [])

    def test_build_csv_rejects_missing_or_malformed_required_args(self):
        """Ensure _build_csv enforces filename/query shape."""
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.filename must be a string for output type "csv"',
        ):
            _build_csv(object(), query=_query_with_order_id())
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.query must be a mapping for output type "csv"',
        ):
            _build_csv(object(), filename="x.csv")
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.filename must be a string for output type "csv"',
        ):
            _build_csv(object(), filename=1, query=_query_with_order_id())  # type: ignore[arg-type]
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.query must be a mapping for output type "csv"',
        ):
            _build_csv(object(), filename="x.csv", query="bad")  # type: ignore[arg-type]

    def test_csv_config_validates_direct_constructor_and_from_raw(self):
        """Ensure CsvConfig validates both direct construction and from_raw paths."""
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.filename must be a string for output type "csv"',
        ):
            CsvConfig(filename=1, query={})  # type: ignore[arg-type]
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.query must be a mapping for output type "csv"',
        ):
            CsvConfig(filename="x.csv", query="bad")  # type: ignore[arg-type]
        with self.assertRaisesRegex(
            EleanorConfigurationException,
            'output.args.query must be a mapping for output type "csv"',
        ):
            CsvConfig.from_raw({"filename": "x.csv"})

    def test_initialize_fresh_file_creates_header_and_schema_and_order_id(self):
        """Ensure initialize on a new CSV writes header/schema with unclaimed next_order_id and next_vs_point_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows, [["order_id", "exit_code"]])

            schema_file = _schema_path(filename)
            with open(schema_file) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["query"], _query_with_order_id())
            self.assertEqual(schema["next_order_id"], 1)
            self.assertEqual(schema["next_vs_point_id"], 1)

            order = _minimal_order()
            self.assertEqual(sink.begin_run(order), 1)
            self.assertEqual(order.id, 1)
            with open(schema_file) as handle:
                schema_after_begin = yaml.safe_load(handle)
            self.assertEqual(schema_after_begin["next_order_id"], 2)
            # ``begin_run`` does not consume vs point ids, so the persisted
            # value is still the one ``initialize`` wrote.
            self.assertEqual(schema_after_begin["next_vs_point_id"], 1)

    def test_initialize_existing_matching_files_claims_and_increments_order_id(self):
        """Ensure begin_run claims current next_order_id and durably increments it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["order_id", "exit_code"])
                writer.writerow([4, 0])
            _write_sidecar(filename, _query_with_order_id(), next_order_id=5, next_vs_point_id=12)

            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            with open(_schema_path(filename)) as handle:
                schema_after_init = yaml.safe_load(handle)
            self.assertEqual(schema_after_init["next_order_id"], 5)
            self.assertEqual(schema_after_init["next_vs_point_id"], 12)
            order = _minimal_order()
            self.assertEqual(sink.begin_run(order), 5)
            self.assertEqual(order.id, 5)

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["next_order_id"], 6)
            self.assertEqual(schema["next_vs_point_id"], 12)

    def test_initialize_existing_csv_without_schema_raises(self):
        """Ensure CSV-without-schema mismatch is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["order_id", "exit_code"])
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            with self.assertRaises(EleanorException):
                sink.initialize()

    def test_initialize_existing_header_mismatch_raises(self):
        """Ensure existing header names/order must match compiled query columns exactly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["exit_code", "order_id"])
            _write_sidecar(filename, _query_with_order_id(), next_order_id=2)
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            with self.assertRaises(EleanorException):
                sink.initialize()

    def test_initialize_header_only_csv_with_order_id_column_succeeds(self):
        """Ensure header-only existing CSV passes order-id max validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["order_id", "exit_code"])
            _write_sidecar(filename, _query_with_order_id(), next_order_id=2)
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

    def test_initialize_skips_max_id_check_when_no_order_id_column(self):
        """Ensure initialize succeeds without max-id scan when query lacks order-id column."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["exit_code"])
                writer.writerow(["not-an-int"])
            _write_sidecar(filename, _query_without_order_id(), next_order_id=22)
            sink = CsvSink(CsvConfig(filename=filename, query=_query_without_order_id()))
            sink.initialize()

    def test_initialize_raises_when_max_order_id_mismatches_schema(self):
        """Ensure existing data max order-id must equal schema next_order_id - 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["order_id", "exit_code"])
                writer.writerow([9, 0])
            _write_sidecar(filename, _query_with_order_id(), next_order_id=99)
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            with self.assertRaises(EleanorException):
                sink.initialize()

    def test_begin_run_stamps_order_fields_and_is_idempotent(self):
        """Ensure begin_run is idempotent per object and stamps fields for each new order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            order = _minimal_order()
            order.eleanor_version = None
            first = sink.begin_run(order)
            second = sink.begin_run(order)
            self.assertEqual(first, 1)
            self.assertEqual(second, 1)
            self.assertEqual(order.id, 1)
            self.assertIsNotNone(order.eleanor_version)

            supplied = _minimal_order()
            supplied.eleanor_version = "caller-version"
            self.assertEqual(sink.begin_run(supplied), 2)
            self.assertEqual(supplied.id, 2)
            self.assertEqual(supplied.eleanor_version, "caller-version")

    def test_begin_run_issues_sequential_ids_for_distinct_orders(self):
        """Ensure distinct order objects receive sequential IDs from one initialized sink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            first = _minimal_order()
            second = _minimal_order()
            self.assertEqual(sink.begin_run(first), 1)
            self.assertEqual(sink.begin_run(second), 2)

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["next_order_id"], 3)

    def test_begin_run_before_initialize_raises(self):
        """Ensure begin_run rejects orders when the sink has not been initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            with self.assertRaisesRegex(EleanorException, "not initialized"):
                sink.begin_run(_minimal_order())

    def test_write_batch_success_appends_rows_converts_none_and_ticks_progress(self):
        """Ensure write_batch appends rows, maps None->"", preserves points, and returns outcomes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            order = _minimal_order()
            sink.begin_run(order)
            original_vs_points = order.vs_points

            r0 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            r1 = ComputeResult(point=SimpleNamespace(exit_code=5, order_id=None))
            progress = mock.Mock()
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[
                    iter([{"order_id": 1, "exit_code": None}, {"order_id": 1, "exit_code": 7}]),
                    iter([{"order_id": 1, "exit_code": 5}]),
                ],
            ):
                outcomes = sink.write_batch(1, [r0, r1], progress=progress)

            self.assertEqual(len(outcomes), 2)
            self.assertTrue(all(outcome.committed for outcome in outcomes))
            self.assertEqual(outcomes[0].exit_code, 0)
            self.assertEqual(outcomes[1].exit_code, 5)
            # ``point_id`` is a sink-lifetime monotonic counter starting at 1;
            # navigators rely on non-None ids to drive completion.
            self.assertEqual(outcomes[0].point_id, 1)
            self.assertEqual(outcomes[1].point_id, 2)
            self.assertEqual(progress.tick.call_count, 2)
            self.assertIs(order.vs_points, original_vs_points)

            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["order_id", "exit_code"])
            self.assertEqual(rows[1], ["1", ""])
            self.assertEqual(rows[2], ["1", "7"])
            self.assertEqual(rows[3], ["1", "5"])

    def test_write_batch_failure_logs_traceback_reraises_and_decrements_counter_when_no_rows(self):
        """Ensure evaluate failures are loud, re-raised, and decrement next_order_id when no writes happened."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            order = _minimal_order()
            sink.begin_run(order)
            original_vs_points = order.vs_points

            result = ComputeResult(point=SimpleNamespace(exit_code=3, order_id=None))
            captured = io.StringIO()
            with (
                mock.patch("eleanor.output.csv.sink.evaluate", side_effect=RuntimeError("boom")),
                mock.patch("eleanor.output.csv.sink.sys.stderr", captured),
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    sink.write_batch(1, [result])

            text = captured.getvalue()
            self.assertIn("VS point index 0", text)
            self.assertIn("RuntimeError", text)
            self.assertIn("boom", text)
            self.assertIn("Traceback", text)
            self.assertIs(order.vs_points, original_vs_points)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["next_order_id"], 1)
            self.assertEqual(sink.begin_run(_minimal_order()), 1)

    def test_write_batch_failure_does_not_decrement_after_any_successful_append(self):
        """Ensure schema counter stays put once at least one row append already succeeded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            ok = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            bad = ComputeResult(point=SimpleNamespace(exit_code=9, order_id=None))
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[iter([{"order_id": 1, "exit_code": 0}]), RuntimeError("explode")],
            ):
                with self.assertRaisesRegex(RuntimeError, "explode"):
                    sink.write_batch(1, [ok, bad])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["next_order_id"], 2)

    def test_find_order_id_column_detects_order_and_point_paths_with_precedence(self):
        """Ensure helper detects order.id and vs.Point.order_id with order.id precedence."""
        point_only = compile_query(
            Order,
            {
                "row_scope": "vs_points[*]",
                "columns": [{"path": "vs_point.order_id", "name": "point_order_id"}],
            },
        )
        self.assertEqual(_find_order_id_column(point_only), "point_order_id")

        both = compile_query(
            Order,
            {
                "row_scope": "vs_points[*]",
                "columns": [
                    {"path": "vs_point.order_id", "name": "point_order_id"},
                    {"path": "order.id", "name": "order_id"},
                ],
            },
        )
        self.assertEqual(_find_order_id_column(both), "order_id")

    def test_find_order_id_column_returns_none_when_absent(self):
        """Ensure helper returns None when query has no supported order-id path."""
        compiled = compile_query(
            Order,
            {
                "row_scope": "vs_points[*]",
                "columns": [{"path": "vs_point.exit_code", "name": "exit_code"}],
            },
        )
        self.assertIsNone(_find_order_id_column(compiled))

    def test_csv_sink_is_importable_from_output_package(self):
        """Ensure CsvSink is accessible via the eleanor.output lazy-import path."""
        import eleanor.output as out
        from eleanor.output.csv.sink import CsvSink as sink_cls

        self.assertIs(out.CsvSink, sink_cls)

    def test_point_id_counter_is_monotonic_across_begin_run_calls(self):
        """Ensure ``WriteOutcome.point_id`` is unique across runs from the same sink instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            first_order = _minimal_order()
            sink.begin_run(first_order)
            r0 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            r1 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[
                    iter([{"order_id": 1, "exit_code": 0}]),
                    iter([{"order_id": 1, "exit_code": 0}]),
                ],
            ):
                first_outcomes = sink.write_batch(1, [r0, r1])

            second_order = _minimal_order()
            sink.begin_run(second_order)
            r2 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[iter([{"order_id": 2, "exit_code": 0}])],
            ):
                second_outcomes = sink.write_batch(2, [r2])

            self.assertEqual([o.point_id for o in first_outcomes], [1, 2])
            self.assertEqual([o.point_id for o in second_outcomes], [3])

    def test_write_batch_persists_advanced_next_vs_point_id(self):
        """Ensure successful write_batch flushes the advanced ``next_vs_point_id`` to the sidecar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            r0 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            r1 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[
                    iter([{"order_id": 1, "exit_code": 0}]),
                    iter([{"order_id": 1, "exit_code": 0}]),
                ],
            ):
                _ = sink.write_batch(1, [r0, r1])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["next_vs_point_id"], 3)

    def test_initialize_resumes_next_vs_point_id_from_existing_sidecar(self):
        """Ensure a fresh sink against an existing sidecar resumes from the persisted ``next_vs_point_id``."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["order_id", "exit_code"])
            _write_sidecar(filename, _query_with_order_id(), next_order_id=1, next_vs_point_id=100)

            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            r0 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[iter([{"order_id": 1, "exit_code": 0}])],
            ):
                outcomes = sink.write_batch(1, [r0])

            self.assertEqual(outcomes[0].point_id, 100)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["next_vs_point_id"], 101)

    def test_initialize_rejects_missing_or_invalid_next_vs_point_id(self):
        """Ensure ``initialize`` rejects sidecars whose ``next_vs_point_id`` is missing, non-int, or bool."""
        for bad_value, label in [
            (None, "missing"),
            ("not-an-int", "string"),
            (True, "bool"),
        ]:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    filename = f"{tmpdir}/rows.csv"
                    with open(filename, "w", newline="") as handle:
                        csv.writer(handle).writerow(["order_id", "exit_code"])
                    payload: dict[str, object] = {
                        "query": _query_with_order_id(),
                        "next_order_id": 1,
                    }
                    if bad_value is not None:
                        payload["next_vs_point_id"] = bad_value
                    with open(_schema_path(filename), "w") as handle:
                        yaml.safe_dump(payload, handle, sort_keys=False)

                    sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
                    with self.assertRaisesRegex(EleanorException, "next_vs_point_id"):
                        sink.initialize()

    def test_write_batch_failure_rollback_does_not_rewind_next_vs_point_id(self):
        """Ensure ``next_vs_point_id`` already consumed earlier in a batch is preserved across a rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            # First result yields zero rows (so ``_rows_written`` stays False)
            # but still consumes a point id; second result raises in evaluate.
            empty = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            bad = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[iter([]), RuntimeError("boom")],
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    sink.write_batch(1, [empty, bad])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            # ``next_order_id`` is rolled back to 1 (no rows landed) but the
            # already-issued point id 1 must NOT be reusable.
            self.assertEqual(schema["next_order_id"], 1)
            self.assertEqual(schema["next_vs_point_id"], 2)

    def test_write_batch_skips_errored_compute_result(self):
        """Ensure ``ComputeResult.error`` produces a non-committed outcome with no row, no tick, no id consumed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            errored = ComputeResult(
                point=SimpleNamespace(exit_code=0, order_id=None),
                error=ErrorInfo(type_name="RuntimeError", message="worker died", traceback_text="tb"),
            )
            progress = mock.Mock()
            with mock.patch("eleanor.output.csv.sink.evaluate") as mocked_evaluate:
                outcomes = sink.write_batch(1, [errored], progress=progress)

            self.assertEqual(len(outcomes), 1)
            self.assertIsNone(outcomes[0].point_id)
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
            self.assertEqual(schema["next_vs_point_id"], 1)

    def test_write_batch_handles_mixed_errored_and_healthy_batch(self):
        """Ensure healthy results in a mixed batch get sequential ids and errored ones are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            ok0 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            errored = ComputeResult(
                point=SimpleNamespace(exit_code=0, order_id=None),
                error=ErrorInfo(type_name="OSError", message="transport failed", traceback_text="tb"),
            )
            ok1 = ComputeResult(point=SimpleNamespace(exit_code=0, order_id=None))
            progress = mock.Mock()
            # ``evaluate`` is only invoked for the two healthy results.
            with mock.patch(
                "eleanor.output.csv.sink.evaluate",
                side_effect=[
                    iter([{"order_id": 1, "exit_code": 0}]),
                    iter([{"order_id": 1, "exit_code": 0}]),
                ],
            ) as mocked_evaluate:
                outcomes = sink.write_batch(1, [ok0, errored, ok1], progress=progress)

            self.assertEqual([o.point_id for o in outcomes], [1, None, 2])
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
            self.assertEqual(schema["next_vs_point_id"], 3)
