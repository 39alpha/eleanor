import copy
import csv
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self, cast, override

import yaml

import eleanor.variable_space as vs
from eleanor.exceptions import EleanorException
from eleanor.order import Order
from eleanor.output.interface import AbstractOutputSink, ComputeResult, WriteOutcome
from eleanor.output.settings import OutputSinkSettings
from eleanor.progress import ProgressHandle
from eleanor.query import CompiledQuery, compile_query, evaluate
from eleanor.query.reflection import DataclassField, LeafField
from eleanor.typing import StrPath
from eleanor.util import guard_is_dict, guard_is_path, require_dict, require_path


@dataclass(kw_only=True)
class CsvSinkSettings(OutputSinkSettings):
    filename: Path
    query: dict[str, object]

    def __post_init__(self) -> None:
        super().__post_init__()

        guard_is_path(self.filename, "filename")
        guard_is_dict(self.query, "query")

    @classmethod
    @override
    def from_dict(cls, raw: dict[str, object]) -> Self:
        base_settings = OutputSinkSettings.from_dict(raw)
        filename = require_path(raw.get("filename"), "filename")
        query: dict[str, object] = require_dict(raw.get("query"), "query")

        return cls(
            verbose=base_settings.verbose,
            filename=filename,
            query=query,
        )


def _schema_path(filename: Path) -> Path:
    return filename.with_name(filename.stem + "_schema.yaml")


def _write_csv_header(filename: Path, columns: list[str]) -> None:
    with filename.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)


def _read_csv_header(filename: Path) -> list[str]:
    with filename.open(newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            return []


def _read_schema(schema_path: Path) -> dict[str, object]:
    with schema_path.open() as handle:
        raw = cast(object, yaml.safe_load(handle))
    if not isinstance(raw, dict):
        msg = f"csv schema {schema_path!r} must be a mapping"
        raise EleanorException(msg)
    return {str(k): v for k, v in cast(dict[object, object], raw).items()}


def _require_vs_points_seen(schema: dict[str, object], schema_path: Path) -> dict[int, int]:
    vs_points_seen = schema.get("vs_points_seen", {})

    if not isinstance(vs_points_seen, dict):
        msg = f"csv schema {schema_path!r} has invalid vs_points_seen"
        raise EleanorException(msg)

    for key, value in cast(dict[object, object], vs_points_seen).items():
        if not isinstance(key, int) or isinstance(key, bool):
            msg = f"csv schema {schema_path!r} has invalid key {key!r}"
            raise EleanorException(msg)
        if not isinstance(value, int) or isinstance(value, bool):
            msg = f"csv schema {schema_path!r} has invalid count for {key}: {value!r}"
            raise EleanorException(msg)

    return cast(dict[int, int], vs_points_seen)


def _require_order_versions(schema: dict[str, object], schema_path: Path) -> dict[int, str]:
    order_versions = schema.get("order_versions", {})

    if not isinstance(order_versions, dict):
        msg = f"csv schema {schema_path!r} has invalid order_versions"
        raise EleanorException(msg)

    for key, value in cast(dict[object, object], order_versions).items():
        if not isinstance(key, int) or isinstance(key, bool):
            msg = f"csv schema {schema_path!r} has invalid key {key!r}"
            raise EleanorException(msg)
        if not isinstance(value, str):
            msg = f"csv schema {schema_path!r} has invalid version for {key}: {value!r}"
            raise EleanorException(msg)

    return cast(dict[int, str], order_versions)


def _write_schema(
    schema_path: Path,
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
    with schema_path.open("w") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _asset_dir(csv_filename: Path, column_name: StrPath) -> Path:
    return (csv_filename.parent / column_name).resolve()


def _classify_columns(compiled: CompiledQuery) -> tuple[list[str], frozenset[str]]:
    """Partition compiled columns into (vs_index_columns, binary_columns).

    A column is a vs_index column iff its path's meta is ``@index`` and the
    head alias resolves to ``vs.Point``. A column is a binary column iff its
    terminal ``FieldKind`` is ``LeafField`` with ``declared_type is bytes``.
    The two sets are disjoint by construction since the binary check requires
    ``path.meta is None``.
    """
    vs_index_columns: list[str] = []
    binary_columns: set[str] = set()
    for column in compiled.compiled_columns:
        spec = column.spec
        path = spec.path

        if path.meta is not None:
            if path.meta.name != "index":
                continue
            if len(path.segments) == 0:
                continue
            head_alias = path.segments[0].name
            if head_alias not in compiled.scope_table:
                continue
            head_kind = compiled.scope_table[head_alias].type_kind
            if isinstance(head_kind, DataclassField) and head_kind.dataclass_type is vs.Point:
                vs_index_columns.append(spec.name)
            continue

        terminal_kind = column.terminal_kind
        if isinstance(terminal_kind, LeafField) and terminal_kind.declared_type is bytes:
            binary_columns.add(spec.name)
    return vs_index_columns, frozenset(binary_columns)


def _prepare_rows(
    columns: list[str],
    vs_index_columns: list[str],
    vs_index: int,
    rows: Sequence[Mapping[str, object]],
) -> Sequence[Mapping[str, object]]:
    cooked: list[Mapping[str, object]] = []
    for row in rows:
        cooked_row = {column: ("" if (v := row.get(column)) is None else v) for column in columns}
        for column in vs_index_columns:
            cooked_row[column] = vs_index
        cooked.append(cooked_row)
    return cooked


def _extract_binary_assets(
    filename: Path,
    binary_columns: frozenset[str],
    order_id: int,
    point_counter: int,
    rows: Sequence[Mapping[str, object]],
) -> Sequence[Mapping[str, object]]:
    """Write each row's binary cells to disk and replace them with relative paths.

    Returns a row sequence with the same shape as ``rows`` but with each
    binary-column ``bytes`` value replaced by the relative path string
    ``"<column>/<order_id>_<point_counter>[_<row_index>].zip"``. ``None``
    values are passed through untouched and no file is written.

    Failure semantics: this function is not transactional with the
    subsequent ``_append_rows`` write. If ``_append_rows`` raises after
    extraction has written one or more files, those files remain on disk
    as orphans (no CSV row references them). On retry, the same
    ``order_id``/``point_counter`` regenerates the same filenames and
    overwrites the orphans, so the steady-state outcome is correct.
    """
    if len(binary_columns) == 0 or len(rows) == 0:
        return rows

    binary_value_counts = {
        column: sum(1 for row in rows if isinstance(row.get(column), bytes)) for column in binary_columns
    }
    binary_value_indexes = dict.fromkeys(binary_columns, 0)
    extracted_rows: list[dict[str, object]] = []
    for row in rows:
        cooked_row = dict(row)
        for column in binary_columns:
            value = cooked_row.get(column)
            if not isinstance(value, bytes):
                continue
            row_index = binary_value_indexes[column]
            binary_value_indexes[column] += 1
            suffix = "" if binary_value_counts[column] == 1 else f"_{row_index}"
            asset_filename = f"{order_id}_{point_counter}{suffix}.zip"
            with (_asset_dir(filename, column) / asset_filename).open("wb") as handle:
                _ = handle.write(value)
            cooked_row[column] = f"{column}/{asset_filename}"
        extracted_rows.append(cooked_row)
    return extracted_rows


def _append_rows(filename: Path, columns: list[str], rows: Sequence[Mapping[str, object]]) -> None:
    with filename.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        for row in rows:
            writer.writerow(row)


class CsvSink(AbstractOutputSink):
    settings: CsvSinkSettings
    _compiled: CompiledQuery
    _columns: list[str]
    _order_id: int | None
    _order: Order | None
    _schema_file: Path
    _rows_written: bool
    _vs_index_columns: list[str]
    _binary_columns: frozenset[str]
    _vs_points_seen: dict[int, int]
    _order_versions: dict[int, str]

    def __init__(self, settings: CsvSinkSettings) -> None:
        self.settings = settings
        self._compiled = compile_query(Order, settings.query)
        self._columns = [spec.name for spec in self._compiled.columns]
        self._order_id = None
        self._order = None
        self._schema_file = _schema_path(settings.filename)
        self._rows_written = False
        self._vs_index_columns, self._binary_columns = _classify_columns(self._compiled)
        self._vs_points_seen = {}
        self._order_versions = {}

    @override
    def initialize(self) -> None:
        filename = self.settings.filename
        schema_file = self._schema_file

        if not filename.exists():
            _write_csv_header(filename, self._columns)
            for column in self._binary_columns:
                _asset_dir(filename, column).mkdir(parents=True, exist_ok=True)
            self._vs_points_seen = {}
            self._order_versions = {}
            _write_schema(
                schema_file,
                self.settings.query,
                vs_points_seen=self._vs_points_seen,
                order_versions=self._order_versions,
            )
            self._order_id = None
            self._order = None
            self._rows_written = False
            return

        if not schema_file.exists():
            msg = f"csv file {filename!r} exists but companion schema {schema_file!r} is missing"
            raise EleanorException(msg)

        schema = _read_schema(schema_file)
        self._vs_points_seen = _require_vs_points_seen(schema, schema_file)
        self._order_versions = _require_order_versions(schema, schema_file)

        existing_header = _read_csv_header(filename)
        if existing_header != self._columns:
            msg = f"csv header does not match configured query columns: expected {self._columns!r}, found {existing_header!r}"
            raise EleanorException(msg)
        for column in self._binary_columns:
            _asset_dir(filename, column).mkdir(parents=True, exist_ok=True)

        self._order_id = None
        self._order = None
        self._rows_written = False

    @override
    def begin_run(self, order: Order) -> int:
        query = self.settings.query
        schema_file = self._schema_file
        if self._order is order:
            assert self._order_id is not None
            return self._order_id

        order_id = order.id if order.id is not None else max(self._vs_points_seen.keys() or [-1]) + 1

        existing_version = self._order_versions.get(order_id)
        if existing_version is not None and order.eleanor_version != existing_version:
            msg = "cannot extend an order generated by a different version of Eleanor"
            raise EleanorException(msg)
        self._order_versions[order_id] = order.eleanor_version

        self._vs_points_seen[order_id] = self._vs_points_seen.get(order_id, 0)
        _write_schema(
            schema_file,
            query,
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
        filename = self.settings.filename
        schema_file = self._schema_file

        if self._order is None:
            msg = "csv sink write_batch called before begin_run"
            raise EleanorException(msg)

        if not filename.exists():
            msg = "csv sink write_batch requires initialize() to create the CSV header"
            raise EleanorException(msg)

        assert self._order_id is not None
        assert self._order_id in self._vs_points_seen

        outcomes: list[WriteOutcome] = []
        for index, result in enumerate(results):
            if result.error is not None:
                outcomes.append(
                    WriteOutcome(
                        exit_code=-1,
                        committed=False,
                        error_message=result.error.message,
                    ),
                )
                continue

            order = copy.copy(self._order)
            assert order is not None
            order.vs_points = [result.point]

            try:
                rows = list(evaluate(self._compiled, order))
            except Exception as error:
                print(
                    f"CsvSink.write_batch failed for VS point index {index}: {type(error).__name__}: {error}",
                    file=sys.stderr,
                )
                traceback.print_exc(file=sys.stderr)
                if not self._rows_written:
                    _write_schema(
                        schema_file,
                        self.settings.query,
                        vs_points_seen=self._vs_points_seen,
                        order_versions=self._order_versions,
                    )
                    self._order = None
                    self._order_id = None
                raise
            current_point_id = self._vs_points_seen[self._order_id]
            rows = _extract_binary_assets(
                filename,
                self._binary_columns,
                self._order_id,
                current_point_id,
                rows,
            )
            rows = _prepare_rows(self._columns, self._vs_index_columns, current_point_id, rows)
            _append_rows(filename, self._columns, rows)
            committed = False
            if rows:
                self._rows_written = True
                committed = True
                self._vs_points_seen[self._order_id] += 1
            outcomes.append(
                WriteOutcome(
                    exit_code=result.point.exit_code,
                    committed=committed,
                ),
            )
            if progress is not None:
                progress.tick()

        _write_schema(
            schema_file,
            self.settings.query,
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


__all__ = [
    "CsvSink",
    "CsvSinkSettings",
]
