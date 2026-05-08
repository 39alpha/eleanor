import copy
import csv
import os.path
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict, override

import yaml

import eleanor.variable_space as vs

from ..exceptions import EleanorConfigurationException, EleanorException
from ..order import Order
from ..progress import ProgressHandle
from ..query import CompiledQuery, compile_query, evaluate
from ..query.reflection import DataclassField
from ..typing import cast
from ..version import __version__
from .interface import ComputeResult, OutputSink, WriteOutcome


class CsvArgsRaw(TypedDict, total=False):
    filename: str
    query: dict[str, object]


@dataclass(frozen=True, init=False)
class CsvConfig(object):
    filename: str
    query: dict[str, object]

    def __init__(self, filename: object, query: object):
        if not isinstance(filename, str):
            raise EleanorConfigurationException('output.args.filename must be a string for output type "csv"')
        if not isinstance(query, dict):
            raise EleanorConfigurationException('output.args.query must be a mapping for output type "csv"')
        typed_query: dict[str, object] = {str(k): v for k, v in cast(dict[object, object], query).items()}
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "query", typed_query)

    @staticmethod
    def from_raw(raw: CsvArgsRaw) -> "CsvConfig":
        return CsvConfig(
            filename=raw.get("filename"),
            query=raw.get("query"),
        )


def _schema_path(filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    if ext:
        return f"{stem}_schema.yaml"
    return f"{filename}_schema.yaml"


def _write_csv_header(filename: str, columns: list[str]) -> None:
    with open(filename, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)


def _read_csv_header(filename: str) -> list[str]:
    with open(filename, newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            return []


def _read_schema(schema_path: str) -> dict[str, object]:
    with open(schema_path) as handle:
        raw = cast(object, yaml.safe_load(handle))
    if not isinstance(raw, dict):
        raise EleanorException(f'csv schema "{schema_path}" must be a mapping')
    return {str(k): v for k, v in cast(dict[object, object], raw).items()}


def _require_vs_points_seen(schema: dict[str, object], schema_path: str) -> dict[int, int]:
    vs_points_seen = schema.get("vs_points_seen", {})

    if not isinstance(vs_points_seen, dict):
        raise EleanorException(f'csv schema "{schema_path}" has invalid vs_points_seen')

    for key, value in cast(dict[object, object], vs_points_seen).items():
        if not isinstance(key, int) or isinstance(key, bool):
            raise EleanorException(f'csv schema "{schema_path}" has invalid key {key!r}')
        if not isinstance(value, int) or isinstance(value, bool):
            raise EleanorException(f'csv schema "{schema_path}" has invalid count for {key}: {value!r}')

    return cast(dict[int, int], vs_points_seen)


def _require_order_versions(schema: dict[str, object], schema_path: str) -> dict[int, str]:
    order_versions = schema.get("order_versions", {})

    if not isinstance(order_versions, dict):
        raise EleanorException(f'csv schema "{schema_path}" has invalid order_versions')

    for key, value in cast(dict[object, object], order_versions).items():
        if not isinstance(key, int) or isinstance(key, bool):
            raise EleanorException(f'csv schema "{schema_path}" has invalid key {key!r}')
        if not isinstance(value, str):
            raise EleanorException(f'csv schema "{schema_path}" has invalid version for {key}: {value!r}')

    return cast(dict[int, str], order_versions)


def _write_schema(
    schema_path: str,
    query: dict[str, object],
    *,
    vs_points_seen: dict[int, int],
    order_versions: dict[int, str],
) -> None:
    payload = {
        "query": query,
        "vs_points_seen": vs_points_seen,
        "order_versions": order_versions,
    }
    with open(schema_path, "w") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _find_vs_index_columns(compiled: CompiledQuery) -> list[str]:
    index_columns: list[str] = []

    for spec in compiled.columns:
        path = spec.path
        if path.meta is None:
            continue
        head_alias = path.segments[0].name
        if head_alias not in compiled.scope_table:
            continue
        head_scope = compiled.scope_table[head_alias]
        kind = head_scope.type_kind
        if not isinstance(kind, DataclassField):
            continue

        if path.meta.name == "index" and kind.dataclass_type is vs.Point:
            index_columns.append(spec.name)

    return index_columns


def _prepare_rows(
    columns: list[str], vs_index_columns: list[str], vs_index: int, rows: Sequence[Mapping[str, object]]
) -> Sequence[Mapping[str, object]]:
    cooked: list[Mapping[str, object]] = []
    for row in rows:
        cooked_row = {column: ("" if (v := row.get(column)) is None else v) for column in columns}
        for column in vs_index_columns:
            cooked_row[column] = vs_index
        cooked.append(cooked_row)
    return cooked


def _append_rows(filename: str, columns: list[str], rows: Sequence[Mapping[str, object]]) -> None:
    with open(filename, "a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        for row in rows:
            writer.writerow(row)


class CsvSink(OutputSink):
    config: CsvConfig
    _compiled: CompiledQuery
    _columns: list[str]
    _order_id: int | None
    _order: Order | None
    _schema_file: str
    _rows_written: bool
    _vs_index_columns: list[str]
    _vs_points_seen: dict[int, int]
    _order_versions: dict[int, str]

    def __init__(self, config: CsvConfig):
        self.config = config
        self._compiled = compile_query(Order, config.query)
        self._columns = [spec.name for spec in self._compiled.columns]
        self._order_id = None
        self._order = None
        self._schema_file = _schema_path(config.filename)
        self._rows_written = False
        self._vs_index_columns = _find_vs_index_columns(self._compiled)
        self._vs_points_seen = {}
        self._order_versions = {}

    @override
    def initialize(self) -> None:
        if not os.path.exists(self.config.filename):
            _write_csv_header(self.config.filename, self._columns)
            self._vs_points_seen = {}
            self._order_versions = {}
            _write_schema(
                self._schema_file,
                self.config.query,
                vs_points_seen=self._vs_points_seen,
                order_versions=self._order_versions,
            )
            self._order_id = None
            self._order = None
            self._rows_written = False
            return

        if not os.path.exists(self._schema_file):
            raise EleanorException(
                f'csv file "{self.config.filename}" exists but companion schema "{self._schema_file}" is missing'
            )

        schema = _read_schema(self._schema_file)
        self._vs_points_seen = _require_vs_points_seen(schema, self._schema_file)
        self._order_versions = _require_order_versions(schema, self._schema_file)

        existing_header = _read_csv_header(self.config.filename)
        if existing_header != self._columns:
            raise EleanorException(
                "csv header does not match configured query columns: "
                + f"expected {self._columns!r}, found {existing_header!r}"
            )

        self._order_id = None
        self._order = None
        self._rows_written = False

    @override
    def begin_run(self, order: Order) -> int:
        if self._order is order:
            assert self._order_id is not None
            return self._order_id

        if order.id is None:
            order_id = max(self._vs_points_seen.keys() or [-1]) + 1
        else:
            order_id = order.id

        existing_version = self._order_versions.get(order_id)
        if existing_version is None:
            if order.eleanor_version is None:
                order.eleanor_version = __version__
        elif order.eleanor_version is None:
            order.eleanor_version = existing_version
        elif order.eleanor_version != existing_version:
            raise EleanorException("cannot extend an order generated by a different version of Eleanor")
        assert order.eleanor_version is not None
        self._order_versions[order_id] = order.eleanor_version

        self._vs_points_seen[order_id] = self._vs_points_seen.get(order_id, 0)
        _write_schema(
            self._schema_file,
            self.config.query,
            vs_points_seen=self._vs_points_seen,
            order_versions=self._order_versions,
        )

        order.id = order_id
        self._order = order
        self._order_id = order_id
        self._rows_written = False

        return order_id

    @override
    def write_batch(
        self,
        order_id: int,
        results: Sequence[ComputeResult],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        _ = order_id
        if self._order is None:
            raise EleanorException("csv sink write_batch called before begin_run")
        if not os.path.exists(self.config.filename):
            raise EleanorException("csv sink write_batch requires initialize() to create the CSV header")
        # ``self._order`` non-None implies we have run through ``initialize``
        # and ``begin_run``, so two things are true:
        #   1. self._order_id is not None
        #   2. self._vs_points_seen[self._order_id] does not raise a KeyError
        assert self._order_id is not None and self._order_id in self._vs_points_seen

        outcomes: list[WriteOutcome] = []
        for index, result in enumerate(results):
            if result.error is not None:
                # Transport-level failure: the worker reported a hard error
                # and ``result.point`` may be partially constructed, so it is
                # not safe to walk it through ``evaluate``. Mirror the
                # PostgresSink rolled-back-savepoint convention
                # (``committed=False``, ``exit_code=-1``) so ``RunStats``
                # counts it as failed. The sink-side counter is NOT advanced
                # for transport failures.
                outcomes.append(
                    WriteOutcome(
                        exit_code=-1,
                        committed=False,
                        error_message=result.error.message,
                    )
                )
                continue

            order = copy.copy(self._order)
            assert order is not None
            order.vs_points = [result.point]
            try:
                rows = list(evaluate(self._compiled, order))
            except Exception as error:
                print(
                    "CsvSink.write_batch failed for " + f"VS point index {index}: {type(error).__name__}: {error}",
                    file=sys.stderr,
                )
                traceback.print_exc(file=sys.stderr)
                if not self._rows_written:
                    _write_schema(
                        self._schema_file,
                        self.config.query,
                        vs_points_seen=self._vs_points_seen,
                        order_versions=self._order_versions,
                    )
                    self._order = None
                    self._order_id = None
                raise
            current_point_id = self._vs_points_seen[self._order_id]
            rows = _prepare_rows(self._columns, self._vs_index_columns, current_point_id, rows)
            _append_rows(self.config.filename, self._columns, rows)
            committed = False
            if rows:
                self._rows_written = True
                committed = True
                self._vs_points_seen[self._order_id] += 1
            outcomes.append(
                WriteOutcome(
                    exit_code=result.point.exit_code,
                    committed=committed,
                )
            )
            if progress is not None:
                progress.tick()

        _write_schema(
            self._schema_file,
            self.config.query,
            vs_points_seen=self._vs_points_seen,
            order_versions=self._order_versions,
        )
        return outcomes

    @override
    def finalize_run(self) -> None:
        return None

    @override
    def supports_worker_writes(self) -> bool:
        return False

    @override
    def supports_progress(self) -> bool:
        return True
