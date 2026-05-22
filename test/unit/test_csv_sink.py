import csv
import io
import os.path
import tempfile
import warnings
from types import SimpleNamespace
from typing import cast
from unittest import mock

import yaml

from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.kernel.config import Settings as KernelSettings
from eleanor.order import Order
from eleanor.output import ComputeResult
from eleanor.output.csv import CsvConfig, CsvSink, _classify_columns, _schema_path
from eleanor.output.factories import build_csv as _build_csv
from eleanor.output.interface import ErrorInfo
from eleanor.query import compile_query
from eleanor.variable_space import Point

from .common import TestCase

_FAKE_KERNEL_SPEC = SimpleNamespace(
    settings_from_dict=mock.Mock(return_value=KernelSettings(timeout=None)),
    build=mock.Mock(),
)


def _write_sidecar(
    filename: str,
    query: dict[str, object],
    *,
    vs_points_seen: dict[int, int] | None = None,
    order_versions: dict[int, str] | None = None,
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
    with mock.patch("eleanor.kernel.registry.get_factory", return_value=_FAKE_KERNEL_SPEC):
        return Order.from_yamls(
            """
name: csv-order
notes: csv sink test
creator: test
kernel:
  type: eq36
  args: {}
temperature: 25.0
pressure: 1.0
elements:
  Na: 1.0
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
            {"path": "order.id", "name": "order_id"},
            {"path": "vs_point.@index", "name": "vs_index"},
            {"path": "vs_point.exit_code", "name": "exit_code"},
        ],
    }


def _point(*, exit_code: int = 0, order_id: int | None = None) -> Point:
    return cast(Point, cast(object, SimpleNamespace(exit_code=exit_code, order_id=order_id)))


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
        """Ensure initialize on a new CSV writes an empty sidecar and begin_run claims order id 0."""
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
            self.assertEqual(schema["vs_points_seen"], {})
            self.assertEqual(schema["order_versions"], {})

            order = _minimal_order()
            self.assertEqual(sink.begin_run(order), 0)
            self.assertEqual(order.id, 0)
            with open(schema_file) as handle:
                schema_after_begin = yaml.safe_load(handle)
            self.assertEqual(schema_after_begin["vs_points_seen"], {0: 0})
            self.assertEqual(schema_after_begin["order_versions"], {0: order.eleanor_version})

    def test_initialize_resets_sidecar_state_when_csv_deleted(self):
        """Ensure re-initialization after CSV deletion writes empty vs_points_seen and order_versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            order = _minimal_order()
            order.id = 3
            order.eleanor_version = "v1"
            sink.begin_run(order)

            schema_file = _schema_path(filename)
            with open(schema_file) as handle:
                before = yaml.safe_load(handle)
            self.assertEqual(before["vs_points_seen"], {3: 0})
            self.assertEqual(before["order_versions"], {3: "v1"})

            os.remove(filename)
            os.remove(schema_file)
            sink.initialize()

            with open(schema_file) as handle:
                after = yaml.safe_load(handle)
            self.assertEqual(after["vs_points_seen"], {})
            self.assertEqual(after["order_versions"], {})

    def test_initialize_existing_matching_files_claims_next_order_id(self):
        """Ensure begin_run allocates max(order_id)+1 and persists a new zero-count entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["order_id", "exit_code"])
                writer.writerow([4, 0])
            _write_sidecar(filename, _query_with_order_id(), vs_points_seen={4: 1})

            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            with open(_schema_path(filename)) as handle:
                schema_after_init = yaml.safe_load(handle)
            self.assertEqual(schema_after_init["vs_points_seen"], {4: 1})
            order = _minimal_order()
            self.assertEqual(sink.begin_run(order), 5)
            self.assertEqual(order.id, 5)

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {4: 1, 5: 0})

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
            _write_sidecar(filename, _query_with_order_id(), vs_points_seen={1: 0})
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            with self.assertRaises(EleanorException):
                sink.initialize()

    def test_initialize_header_only_csv_with_sidecar_succeeds(self):
        """Ensure header-only existing CSV initializes when sidecar has a valid vs_points_seen mapping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["order_id", "exit_code"])
            _write_sidecar(filename, _query_with_order_id(), vs_points_seen={})
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

    def test_initialize_uses_missing_vs_points_seen_as_empty_mapping(self):
        """Ensure sidecars without vs_points_seen are accepted as an empty mapping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["exit_code"])
                writer.writerow(["not-an-int"])
            with open(_schema_path(filename), "w") as handle:
                yaml.safe_dump({"query": _query_without_order_id()}, handle, sort_keys=False)
            sink = CsvSink(CsvConfig(filename=filename, query=_query_without_order_id()))
            sink.initialize()
            self.assertEqual(sink.begin_run(_minimal_order()), 0)

    def test_initialize_rejects_invalid_vs_points_seen_shapes(self):
        """Ensure initialize rejects non-mapping or invalid-key/value vs_points_seen payloads."""
        cases: list[tuple[object, str]] = [
            ("not-a-mapping", "invalid vs_points_seen"),
            ({True: 0}, "invalid key"),
            ({1: True}, "invalid count"),
        ]
        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                with tempfile.TemporaryDirectory() as tmpdir:
                    filename = f"{tmpdir}/rows.csv"
                    with open(filename, "w", newline="") as handle:
                        csv.writer(handle).writerow(["order_id", "exit_code"])
                    with open(_schema_path(filename), "w") as handle:
                        yaml.safe_dump(
                            {
                                "query": _query_with_order_id(),
                                "vs_points_seen": raw_value,
                            },
                            handle,
                            sort_keys=False,
                        )
                    sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
                    with self.assertRaisesRegex(EleanorException, expected):
                        sink.initialize()

    def test_begin_run_stamps_order_fields_and_is_idempotent(self):
        """Ensure begin_run is idempotent per object and stamps fields for each new order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            order = _minimal_order()
            first = sink.begin_run(order)
            second = sink.begin_run(order)
            self.assertEqual(first, 0)
            self.assertEqual(second, 0)
            self.assertEqual(order.id, 0)

            supplied = _minimal_order()
            supplied.eleanor_version = "caller-version"
            self.assertEqual(sink.begin_run(supplied), 1)
            self.assertEqual(supplied.id, 1)
            self.assertEqual(supplied.eleanor_version, "caller-version")

    def test_begin_run_raises_on_version_mismatch_for_reused_order_id(self):
        """Ensure persisted sidecar versions reject reusing an order id with a different eleanor_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            first = _minimal_order()
            first.id = 7
            first.eleanor_version = "v1"
            self.assertEqual(sink.begin_run(first), 7)
            restarted = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            restarted.initialize()

            mismatch = _minimal_order()
            mismatch.id = 7
            mismatch.eleanor_version = "v2"
            with self.assertRaisesRegex(EleanorException, "different version of Eleanor"):
                restarted.begin_run(mismatch)

    def test_begin_run_issues_sequential_ids_for_distinct_orders(self):
        """Ensure distinct order objects receive sequential IDs from one initialized sink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            first = _minimal_order()
            second = _minimal_order()
            self.assertEqual(sink.begin_run(first), 0)
            self.assertEqual(sink.begin_run(second), 1)

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 0, 1: 0})

    def test_begin_run_honors_explicit_order_id_and_resumes_from_max_key(self):
        """Ensure explicit order ids are accepted and subsequent implicit ids continue from max key + 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            explicit = _minimal_order()
            explicit.id = 42
            self.assertEqual(sink.begin_run(explicit), 42)

            implicit = _minimal_order()
            self.assertEqual(sink.begin_run(implicit), 43)

    def test_begin_run_before_initialize_writes_sidecar(self):
        """Ensure begin_run can persist sidecar state without initialize, but write_batch still requires initialize."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            order = _minimal_order()
            self.assertEqual(sink.begin_run(order), 0)
            self.assertFalse(os.path.exists(filename))
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 0})
            result = ComputeResult(point=_point(exit_code=0, order_id=None))
            with self.assertRaisesRegex(EleanorException, "requires initialize\\(\\)"):
                sink.write_batch(0, [result])

    def test_write_batch_success_appends_rows_converts_none_and_ticks_progress(self):
        """Ensure write_batch appends rows, maps None->\"\", preserves points, and returns outcomes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            order = _minimal_order()
            sink.begin_run(order)
            original_vs_points = order.vs_points

            r0 = ComputeResult(point=_point(exit_code=0, order_id=None))
            r1 = ComputeResult(point=_point(exit_code=5, order_id=None))
            progress = mock.Mock()
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"order_id": 1, "exit_code": None}, {"order_id": 1, "exit_code": 7}]),
                    iter([{"order_id": 1, "exit_code": 5}]),
                ],
            ):
                outcomes = sink.write_batch(0, [r0, r1], progress=progress)

            self.assertEqual(len(outcomes), 2)
            self.assertTrue(all(outcome.committed for outcome in outcomes))
            self.assertEqual(outcomes[0].exit_code, 0)
            self.assertEqual(outcomes[1].exit_code, 5)
            self.assertEqual(progress.tick.call_count, 2)
            self.assertIs(order.vs_points, original_vs_points)

            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["order_id", "exit_code"])
            self.assertEqual(rows[1], ["1", ""])
            self.assertEqual(rows[2], ["1", "7"])
            self.assertEqual(rows[3], ["1", "5"])
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 2})

    def test_write_batch_evaluates_each_point_against_order_copy(self):
        """Ensure each evaluate call receives a per-point Order shell, not the canonical Order object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            order = _minimal_order()
            sink.begin_run(order)
            original_vs_points = order.vs_points

            r0 = ComputeResult(point=_point(exit_code=0, order_id=None))
            r1 = ComputeResult(point=_point(exit_code=5, order_id=None))
            expected_points = [r0.point, r1.point]
            seen_roots: list[Order] = []

            def _fake_evaluate(_compiled: object, root: Order):
                expected = expected_points[len(seen_roots)]
                self.assertIsNot(root, order)
                self.assertIs(order.vs_points, original_vs_points)
                self.assertEqual(order.vs_points, [])
                self.assertEqual(root.vs_points, [expected])
                seen_roots.append(root)
                return iter([{"order_id": 1, "exit_code": expected.exit_code}])

            with mock.patch("eleanor.output.csv.evaluate", side_effect=_fake_evaluate):
                outcomes = sink.write_batch(0, [r0, r1])

            self.assertEqual(len(outcomes), 2)
            self.assertTrue(all(outcome.committed for outcome in outcomes))
            self.assertEqual(len(seen_roots), 2)
            self.assertIs(order.vs_points, original_vs_points)
            self.assertEqual(order.vs_points, [])

    def test_write_batch_failure_logs_traceback_reraises_and_keeps_zero_count_state(self):
        """Ensure evaluate failures are loud, re-raised, and preserve zero-count state for the active order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            order = _minimal_order()
            sink.begin_run(order)
            original_vs_points = order.vs_points

            result = ComputeResult(point=_point(exit_code=3, order_id=None))
            captured = io.StringIO()
            with (
                mock.patch("eleanor.output.csv.evaluate", side_effect=RuntimeError("boom")),
                mock.patch("eleanor.output.csv.sys.stderr", captured),
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    sink.write_batch(0, [result])

            text = captured.getvalue()
            self.assertIn("VS point index 0", text)
            self.assertIn("RuntimeError", text)
            self.assertIn("boom", text)
            self.assertIn("Traceback", text)
            self.assertIs(order.vs_points, original_vs_points)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 0})
            self.assertEqual(sink.begin_run(_minimal_order()), 1)

    def test_write_batch_failure_after_success_persists_progress_on_next_begin_run(self):
        """Ensure successful in-memory progress survives a later failure and is persisted on the next begin_run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            ok = ComputeResult(point=_point(exit_code=0, order_id=None))
            bad = ComputeResult(point=_point(exit_code=9, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"order_id": 1, "exit_code": 0}]), RuntimeError("explode")],
            ):
                with self.assertRaisesRegex(RuntimeError, "explode"):
                    sink.write_batch(0, [ok, bad])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            # On-disk sidecar still shows {0: 0} because the partial failure
            # skipped the end-of-batch flush; the in-memory count of 1 is
            # preserved and durably written on the next begin_run.
            self.assertEqual(schema["vs_points_seen"], {0: 0})
            self.assertEqual(sink.begin_run(_minimal_order()), 1)
            with open(_schema_path(filename)) as handle:
                persisted = yaml.safe_load(handle)
            self.assertEqual(persisted["vs_points_seen"], {0: 1, 1: 0})

    def test_csv_sink_is_importable_from_submodule(self):
        """Ensure CsvSink is accessible directly from eleanor.output.csv."""
        from eleanor.output.csv import CsvSink as sink_cls

        self.assertIsNotNone(sink_cls)

    def test_vs_points_seen_counter_is_per_order_not_global(self):
        """Ensure per-order ``vs_points_seen`` counters reset for each new order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()

            first_order = _minimal_order()
            sink.begin_run(first_order)
            r0 = ComputeResult(point=_point(exit_code=0, order_id=None))
            r1 = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"order_id": 0, "exit_code": 0}]),
                    iter([{"order_id": 0, "exit_code": 0}]),
                ],
            ):
                first_outcomes = sink.write_batch(0, [r0, r1])

            second_order = _minimal_order()
            sink.begin_run(second_order)
            r2 = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"order_id": 1, "exit_code": 0}])],
            ):
                second_outcomes = sink.write_batch(1, [r2])

            self.assertTrue(all(outcome.committed for outcome in first_outcomes))
            self.assertTrue(second_outcomes[0].committed)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 2, 1: 1})

    def test_write_batch_persists_advanced_vs_points_seen_for_order(self):
        """Ensure successful write_batch flushes the advanced per-order count to the sidecar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            r0 = ComputeResult(point=_point(exit_code=0, order_id=None))
            r1 = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"order_id": 1, "exit_code": 0}]),
                    iter([{"order_id": 1, "exit_code": 0}]),
                ],
            ):
                _ = sink.write_batch(0, [r0, r1])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 2})

    def test_initialize_resumes_existing_order_count_from_sidecar(self):
        """Ensure explicit order ids resume from persisted per-order counts in the sidecar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["order_id", "exit_code"])
            _write_sidecar(filename, _query_with_order_id(), vs_points_seen={10: 100})

            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            order = _minimal_order()
            order.id = 10
            sink.begin_run(order)

            r0 = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"order_id": 10, "exit_code": 0}])],
            ):
                outcomes = sink.write_batch(10, [r0])

            self.assertTrue(outcomes[0].committed)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {10: 101})

    def test_initialize_rejects_non_int_or_bool_vs_points_seen_entries(self):
        """Ensure initialize rejects sidecars with non-int or bool order counters."""
        for bad_value, label in [
            ("not-an-int", "string"),
            (True, "bool"),
        ]:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    filename = f"{tmpdir}/rows.csv"
                    with open(filename, "w", newline="") as handle:
                        csv.writer(handle).writerow(["order_id", "exit_code"])
                    with open(_schema_path(filename), "w") as handle:
                        yaml.safe_dump(
                            {
                                "query": _query_with_order_id(),
                                "vs_points_seen": {1: bad_value},
                            },
                            handle,
                            sort_keys=False,
                        )

                    sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
                    with self.assertRaisesRegex(EleanorException, "invalid count"):
                        sink.initialize()

    def test_initialize_rejects_invalid_order_versions_shapes(self):
        """Ensure initialize rejects non-mapping or invalid-key/value order_versions payloads."""
        cases: list[tuple[object, str]] = [
            ("not-a-mapping", "invalid order_versions"),
            ({True: "v1"}, "invalid key"),
            ({1: 5}, "invalid version"),
        ]
        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                with tempfile.TemporaryDirectory() as tmpdir:
                    filename = f"{tmpdir}/rows.csv"
                    with open(filename, "w", newline="") as handle:
                        csv.writer(handle).writerow(["order_id", "exit_code"])
                    with open(_schema_path(filename), "w") as handle:
                        yaml.safe_dump(
                            {
                                "query": _query_with_order_id(),
                                "vs_points_seen": {1: 0},
                                "order_versions": raw_value,
                            },
                            handle,
                            sort_keys=False,
                        )

                    sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
                    with self.assertRaisesRegex(EleanorException, expected):
                        sink.initialize()

    def test_write_batch_failure_after_empty_rows_keeps_order_count_unchanged(self):
        """Ensure empty evaluate output does not advance per-order counts across a later failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            # First result yields zero rows and does not consume the count;
            # second result raises in evaluate.
            empty = ComputeResult(point=_point(exit_code=0, order_id=None))
            bad = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([]), RuntimeError("boom")],
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    sink.write_batch(0, [empty, bad])

            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 0})

    def test_write_batch_skips_errored_compute_result(self):
        """Ensure ``ComputeResult.error`` produces a non-committed outcome with no row, no tick, no id consumed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            errored = ComputeResult(
                point=_point(exit_code=0, order_id=None),
                error=ErrorInfo(type_name="RuntimeError", message="worker died", traceback_text="tb"),
            )
            progress = mock.Mock()
            with mock.patch("eleanor.output.csv.evaluate") as mocked_evaluate:
                outcomes = sink.write_batch(0, [errored], progress=progress)

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
            self.assertEqual(schema["vs_points_seen"], {0: 0})

    def test_write_batch_handles_mixed_errored_and_healthy_batch(self):
        """Ensure healthy results in a mixed batch get per-order ids and errored ones are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            ok0 = ComputeResult(point=_point(exit_code=0, order_id=None))
            errored = ComputeResult(
                point=_point(exit_code=0, order_id=None),
                error=ErrorInfo(type_name="OSError", message="transport failed", traceback_text="tb"),
            )
            ok1 = ComputeResult(point=_point(exit_code=0, order_id=None))
            progress = mock.Mock()
            # ``evaluate`` is only invoked for the two healthy results.
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"order_id": 1, "exit_code": 0}]),
                    iter([{"order_id": 1, "exit_code": 0}]),
                ],
            ) as mocked_evaluate:
                outcomes = sink.write_batch(0, [ok0, errored, ok1], progress=progress)
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
            self.assertEqual(schema["vs_points_seen"], {0: 2})

    def test_write_batch_does_not_advance_count_when_evaluate_returns_no_rows(self):
        """Ensure empty evaluate output yields an uncommitted outcome and does not consume a point id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_order_id()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            empty = ComputeResult(point=_point(exit_code=0, order_id=None))
            one_row = ComputeResult(point=_point(exit_code=0, order_id=None))
            progress = mock.Mock()
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([]),
                    iter([{"order_id": 0, "exit_code": 0}]),
                ],
            ):
                outcomes = sink.write_batch(0, [empty, one_row], progress=progress)
            self.assertEqual([o.exit_code for o in outcomes], [0, 0])
            self.assertEqual([o.committed for o in outcomes], [False, True])
            self.assertEqual(progress.tick.call_count, 2)
            with open(_schema_path(filename)) as handle:
                schema = yaml.safe_load(handle)
            self.assertEqual(schema["vs_points_seen"], {0: 1})

    def test_write_batch_stamps_vs_index_columns_with_per_order_point_id(self):
        """Ensure query columns bound to ``vs_point.@index`` are overwritten with per-order point ids."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_vs_index_column()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            first = ComputeResult(point=_point(exit_code=0, order_id=None))
            second = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"order_id": 0, "vs_index": 99, "exit_code": 0}]),
                    iter([{"order_id": 0, "vs_index": 42, "exit_code": 0}]),
                ],
            ):
                outcomes = sink.write_batch(0, [first, second])
            self.assertTrue(all(outcome.committed for outcome in outcomes))
            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["order_id", "vs_index", "exit_code"])
            self.assertEqual(rows[1], ["0", "0", "0"])
            self.assertEqual(rows[2], ["0", "1", "0"])

    def test_classify_columns_partitions_index_and_binary(self):
        """Ensure column classification returns both vs-index and binary partitions."""
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
        vs_index_columns, binary_columns = _classify_columns(compiled)
        self.assertEqual(vs_index_columns, ["vs_index"])
        self.assertEqual(binary_columns, frozenset({"scratch_zip"}))

    def test_initialize_creates_asset_directories(self):
        """Ensure initialize creates per-column asset directories for binary columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_binary_column()))
            sink.initialize()
            self.assertTrue(os.path.isdir(f"{tmpdir}/scratch_zip"))

    def test_write_batch_extracts_binary_to_file_and_writes_path(self):
        """Ensure binary cells are written to disk and replaced with relative asset paths in CSV output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_binary_column()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            result = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"exit_code": 0, "scratch_zip": b"zip-bytes"}])],
            ):
                outcomes = sink.write_batch(0, [result])

            self.assertTrue(outcomes[0].committed)
            asset_file = f"{tmpdir}/scratch_zip/0_0.zip"
            self.assertTrue(os.path.exists(asset_file))
            with open(asset_file, "rb") as handle:
                self.assertEqual(handle.read(), b"zip-bytes")
            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["exit_code", "scratch_zip"])
            self.assertEqual(rows[1], ["0", "scratch_zip/0_0.zip"])

    def test_write_batch_binary_none_writes_blank(self):
        """Ensure None-valued binary cells remain blank and do not emit files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_binary_column()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            result = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[iter([{"exit_code": 0, "scratch_zip": None}])],
            ):
                outcomes = sink.write_batch(0, [result])

            self.assertTrue(outcomes[0].committed)
            self.assertFalse(os.path.exists(f"{tmpdir}/scratch_zip/0_0.zip"))
            with open(filename, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1], ["0", ""])

    def test_initialize_resume_creates_asset_directories(self):
        """Ensure initialize on an existing CSV with binary columns creates per-column asset directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            with open(filename, "w", newline="") as handle:
                csv.writer(handle).writerow(["exit_code", "scratch_zip"])
            _write_sidecar(filename, _query_with_binary_column(), vs_points_seen={0: 1})
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_binary_column()))
            sink.initialize()
            self.assertTrue(os.path.isdir(f"{tmpdir}/scratch_zip"))

    def test_binary_asset_naming_uses_order_and_point_counter(self):
        """Ensure extracted binary file names follow <column>/<order_id>_<point_counter>.zip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_binary_column()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            first = ComputeResult(point=_point(exit_code=0, order_id=None))
            second = ComputeResult(point=_point(exit_code=0, order_id=None))
            with mock.patch(
                "eleanor.output.csv.evaluate",
                side_effect=[
                    iter([{"exit_code": 0, "scratch_zip": b"one"}]),
                    iter([{"exit_code": 0, "scratch_zip": b"two"}]),
                ],
            ):
                outcomes = sink.write_batch(0, [first, second])

            self.assertTrue(all(outcome.committed for outcome in outcomes))
            self.assertTrue(os.path.exists(f"{tmpdir}/scratch_zip/0_0.zip"))
            self.assertTrue(os.path.exists(f"{tmpdir}/scratch_zip/0_1.zip"))
            with open(f"{tmpdir}/scratch_zip/0_0.zip", "rb") as handle:
                self.assertEqual(handle.read(), b"one")
            with open(f"{tmpdir}/scratch_zip/0_1.zip", "rb") as handle:
                self.assertEqual(handle.read(), b"two")

    def test_write_batch_binary_multi_row_uses_row_suffix(self):
        """Ensure multi-row binary outputs for one point use a row-index suffix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = f"{tmpdir}/rows.csv"
            sink = CsvSink(CsvConfig(filename=filename, query=_query_with_binary_column()))
            sink.initialize()
            sink.begin_run(_minimal_order())

            result = ComputeResult(point=_point(exit_code=0, order_id=None))
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
                outcomes = sink.write_batch(0, [result])

            self.assertTrue(outcomes[0].committed)
            self.assertTrue(os.path.exists(f"{tmpdir}/scratch_zip/0_0_0.zip"))
            self.assertTrue(os.path.exists(f"{tmpdir}/scratch_zip/0_0_1.zip"))
