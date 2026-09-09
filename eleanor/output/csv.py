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
from eleanor.exceptions import EleanorError
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
        raise EleanorError(msg)
    return {str(k): v for k, v in cast(dict[object, object], raw).items()}


def _require_vs_points_seen(schema: dict[str, object], schema_path: Path) -> dict[int, int]:
    vs_points_seen = schema.get("vs_points_seen", {})

    if not isinstance(vs_points_seen, dict):
        msg = f"csv schema {schema_path!r} has invalid vs_points_seen"
        raise EleanorError(msg)

    for key, value in cast(dict[object, object], vs_points_seen).items():
        if not isinstance(key, int) or isinstance(key, bool):
            msg = f"csv schema {schema_path!r} has invalid key {key!r}"
            raise EleanorError(msg)
        if not isinstance(value, int) or isinstance(value, bool):
            msg = f"csv schema {schema_path!r} has invalid count for {key}: {value!r}"
            raise EleanorError(msg)

    return cast(dict[int, int], vs_points_seen)


def _require_order_versions(schema: dict[str, object], schema_path: Path) -> dict[int, str]:
    order_versions = schema.get("order_versions", {})

    if not isinstance(order_versions, dict):
        msg = f"csv schema {schema_path!r} has invalid order_versions"
        raise EleanorError(msg)

    for key, value in cast(dict[object, object], order_versions).items():
        if not isinstance(key, int) or isinstance(key, bool):
            msg = f"csv schema {schema_path!r} has invalid key {key!r}"
            raise EleanorError(msg)
        if not isinstance(value, str):
            msg = f"csv schema {schema_path!r} has invalid version for {key}: {value!r}"
            raise EleanorError(msg)

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


@dataclass(slots=True, frozen=True)
class CsvPrepared:
    """One VS point's evaluated rows, or the error that stopped them.

    Query evaluation is by far the expensive half of writing a CSV row set
    (a wide query costs on the order of a second per VS point), and it is
    pure: it reads the compiled query and the order, and touches neither the
    point counter, the file, nor the sidecar. So it runs in the worker and
    only the resulting rows cross the process boundary.

    ``error`` carries a per-point evaluation failure instead of raising, so
    one bad point no longer discards the whole chunk's rows.
    """

    rows: list[Mapping[str, object]]
    exit_code: int
    error: str | None = None


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
    def __getstate__(self) -> dict[str, object]:
        """Drop the compiled query when crossing into a worker.

        ``prepare_batch`` runs in a worker, so the sink is pickled once per
        chunk. :class:`CompiledQuery` holds reflection state that is bulky to
        pickle and cheap to rebuild -- ``compile_query`` is memoised -- so it
        is re-derived on first use in the worker instead.
        """
        state: dict[str, object] = dict(self.__dict__)
        del state["_compiled"]
        return state

    def __setstate__(self, state: dict[str, object]) -> None:
        for key, value in state.items():
            setattr(self, key, value)
        self._compiled = compile_query(Order, self.settings.query)

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
            raise EleanorError(msg)

        schema = _read_schema(schema_file)
        self._vs_points_seen = _require_vs_points_seen(schema, schema_file)
        self._order_versions = _require_order_versions(schema, schema_file)

        existing_header = _read_csv_header(filename)
        if existing_header != self._columns:
            msg = f"csv header does not match configured query columns: expected {self._columns!r}, found {existing_header!r}"
            raise EleanorError(msg)
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
            raise EleanorError(msg)
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
    def prepare_batch(self, order_id: int, results: Sequence[ComputeResult]) -> Sequence[CsvPrepared]:
        """Evaluate the query for each point; return its rows.

        Runs in a worker. Pure with respect to sink state: the shallow
        ``Order`` copy is discarded, and the point counter, the CSV file and
        the sidecar are all left to :meth:`commit_batch`.

        ``order_id`` is honoured as given rather than read from ``self``: the
        worker's copy of the sink may have no active order, and a sink must not
        assume there is only one.
        """
        if self._order is None:
            msg = "csv sink prepare_batch called before begin_run"
            raise EleanorError(msg)

        prepared: list[CsvPrepared] = []
        for index, result in enumerate(results):
            if result.error is not None:
                prepared.append(
                    CsvPrepared(rows=[], exit_code=-1, error=result.error.message),
                )
                continue

            order = copy.copy(self._order)
            order.id = order_id
            order.vs_points = [result.point]

            try:
                rows = list(evaluate(self._compiled, order))
            except Exception as error:
                # Report and record rather than raise: a query that fails on
                # one point should not discard the rest of the chunk's rows.
                print(
                    f"CsvSink.prepare_batch failed for VS point index {index}: {type(error).__name__}: {error}",
                    file=sys.stderr,
                )
                traceback.print_exc(file=sys.stderr)
                prepared.append(CsvPrepared(rows=[], exit_code=-1, error=str(error)))
                continue

            prepared.append(CsvPrepared(rows=rows, exit_code=result.point.exit_code))

        return prepared

    @override
    def commit_batch(
        self,
        order_id: int,
        prepared: Sequence[object],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        """Stamp the per-order point index onto each row set and append it.

        Runs in the parent, which is what lets ``_vs_points_seen`` stay a
        single authoritative counter: it feeds both the ``@index`` column and
        the binary-asset filenames, so it cannot be handed to concurrent
        workers.
        """
        filename = self.settings.filename

        if self._order is None:
            msg = "csv sink commit_batch called before begin_run"
            raise EleanorError(msg)

        if not filename.exists():
            msg = "csv sink commit_batch requires initialize() to create the CSV header"
            raise EleanorError(msg)

        if order_id not in self._vs_points_seen:
            msg = f"csv sink commit_batch called for unknown order id {order_id}"
            raise EleanorError(msg)

        outcomes: list[WriteOutcome] = []
        # One handle for the whole batch rather than one per row set. The
        # ``with`` block still flushes on the way out of an exception, so
        # partial-write semantics are unchanged.
        with filename.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._columns)
            for item in cast("Sequence[CsvPrepared]", prepared):
                if item.error is not None:
                    outcomes.append(
                        WriteOutcome(exit_code=item.exit_code, committed=False, error_message=item.error),
                    )
                    continue

                current_point_id = self._vs_points_seen[order_id]
                rows = _extract_binary_assets(
                    filename,
                    self._binary_columns,
                    order_id,
                    current_point_id,
                    item.rows,
                )
                rows = _prepare_rows(self._columns, self._vs_index_columns, current_point_id, rows)
                for row in rows:
                    writer.writerow(row)
                handle.flush()

                committed = False
                if rows:
                    self._rows_written = True
                    committed = True
                    self._vs_points_seen[order_id] += 1
                outcomes.append(WriteOutcome(exit_code=item.exit_code, committed=committed))
                if progress is not None:
                    progress.tick()

        _write_schema(
            self._schema_file,
            self.settings.query,
            vs_points_seen=self._vs_points_seen,
            order_versions=self._order_versions,
        )
        return outcomes

    @override
    def finalize_run(self) -> None:
        return None

    @override
    def supports_worker_commit(self) -> bool:
        return False

    @override
    def supports_progress(self) -> bool:
        return True


__all__ = [
    "CsvPrepared",
    "CsvSink",
    "CsvSinkSettings",
]
