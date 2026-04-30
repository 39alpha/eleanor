import csv
import os.path
import sys
import traceback
from collections.abc import Mapping, Sequence
from typing import override

import yaml

import eleanor.variable_space as vs

from ...exceptions import EleanorException
from ...order import Order
from ...progress import ProgressHandle
from ...query import CompiledQuery, compile_query, evaluate
from ...query.reflection import DataclassField
from ...typing import cast
from ...version import __version__
from ..interface import ComputeResult, OutputSink, WriteOutcome
from .config import CsvConfig


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


def _require_int_field(schema: dict[str, object], schema_path: str, name: str) -> int:
    """Read ``name`` from ``schema`` and reject anything that is not a true int.

    ``isinstance(x, bool)`` matches because ``bool`` subclasses ``int`` in
    Python, so an explicit second check is required to keep ``True``/``False``
    out of the schema.
    """
    value = schema.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EleanorException(f'csv schema "{schema_path}" has invalid {name}: {value!r}')
    return value


def _write_schema(
    schema_path: str,
    query: dict[str, object],
    *,
    next_order_id: int,
    next_vs_point_id: int,
) -> None:
    payload = {
        "query": query,
        "next_order_id": next_order_id,
        "next_vs_point_id": next_vs_point_id,
    }
    with open(schema_path, "w") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _find_order_id_column(compiled: CompiledQuery) -> str | None:
    order_id_column: str | None = None
    point_order_id_column: str | None = None
    for spec in compiled.columns:
        path = spec.path
        if path.meta is not None or len(path.segments) != 2:
            continue
        head_alias = path.segments[0].name
        tail_name = path.segments[1].name
        if head_alias not in compiled.scope_table:
            continue
        head_scope = compiled.scope_table[head_alias]
        kind = head_scope.type_kind
        if not isinstance(kind, DataclassField):
            continue
        if head_alias == "order" and tail_name == "id" and kind.dataclass_type is Order:
            order_id_column = spec.name
            continue
        if tail_name == "order_id" and kind.dataclass_type is vs.Point:
            point_order_id_column = spec.name
    if order_id_column is not None:
        return order_id_column
    return point_order_id_column


def _max_order_id_in_csv(filename: str, column_name: str) -> int | None:
    max_seen: int | None = None
    with open(filename, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            value = row.get(column_name)
            if value is None or value == "":
                continue
            try:
                parsed = int(value)
            except ValueError as exc:
                raise EleanorException(
                    f'csv column "{column_name}" contains a non-integer order id value: {value!r}'
                ) from exc
            if max_seen is None or parsed > max_seen:
                max_seen = parsed
    return max_seen


def _append_rows(filename: str, columns: list[str], rows: Sequence[Mapping[str, object]]) -> None:
    with open(filename, "a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        for row in rows:
            cooked = {column: ("" if (v := row.get(column)) is None else v) for column in columns}
            writer.writerow(cooked)


class CsvSink(OutputSink):
    config: CsvConfig
    _compiled: CompiledQuery
    _columns: list[str]
    _next_order_id: int | None
    # ``_next_vs_point_id`` is the persisted counter handed out as
    # ``WriteOutcome.point_id`` so navigators have a non-None id per vs point.
    # Stored alongside ``next_order_id`` in the schema sidecar and refreshed
    # at end of every successful :meth:`write_batch` call. Persistence is
    # batch-granular by design (per-row fsync would dominate the CSV append
    # cost); callers who need bulletproof durability should use the postgres
    # sink instead.
    _next_vs_point_id: int
    _order_id: int | None
    _order: Order | None
    _schema_file: str
    _rows_written: bool

    def __init__(self, config: CsvConfig):
        self.config = config
        self._compiled = compile_query(Order, config.query)
        self._columns = [spec.name for spec in self._compiled.columns]
        self._next_order_id = None
        self._next_vs_point_id = 1
        self._order_id = None
        self._order = None
        self._schema_file = _schema_path(config.filename)
        self._rows_written = False

    @override
    def initialize(self) -> None:
        if not os.path.exists(self.config.filename):
            _write_csv_header(self.config.filename, self._columns)
            _write_schema(
                self._schema_file,
                self.config.query,
                next_order_id=1,
                next_vs_point_id=1,
            )
            self._next_order_id = 1
            self._next_vs_point_id = 1
            self._order_id = None
            self._order = None
            self._rows_written = False
            return

        if not os.path.exists(self._schema_file):
            raise EleanorException(
                f'csv file "{self.config.filename}" exists but companion schema "{self._schema_file}" is missing'
            )

        schema = _read_schema(self._schema_file)
        next_order_id = _require_int_field(schema, self._schema_file, "next_order_id")
        next_vs_point_id = _require_int_field(schema, self._schema_file, "next_vs_point_id")

        existing_header = _read_csv_header(self.config.filename)
        if existing_header != self._columns:
            raise EleanorException(
                "csv header does not match configured query columns: "
                + f"expected {self._columns!r}, found {existing_header!r}"
            )

        # TODO: validate schema["query"] matches this sink's raw query exactly.
        order_id_column = _find_order_id_column(self._compiled)
        if order_id_column is not None:
            max_seen = _max_order_id_in_csv(self.config.filename, order_id_column)
            if max_seen is not None and max_seen != next_order_id - 1:
                raise EleanorException(
                    "csv order-id validation failed: "
                    + f"max seen {max_seen} but schema next_order_id is {next_order_id}"
                )

        self._next_order_id = next_order_id
        self._next_vs_point_id = next_vs_point_id
        self._order_id = None
        self._order = None
        self._rows_written = False

    @override
    def begin_run(self, order: Order) -> int:
        if self._order is order:
            assert self._order_id is not None
            return self._order_id
        if self._next_order_id is None:
            raise EleanorException("csv sink is not initialized")
        order_id = self._next_order_id
        _write_schema(
            self._schema_file,
            self.config.query,
            next_order_id=order_id + 1,
            next_vs_point_id=self._next_vs_point_id,
        )
        self._next_order_id = order_id + 1
        if order.eleanor_version is None:
            order.eleanor_version = __version__
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
        # ``self._order`` non-None implies we have run through ``initialize``
        # and ``begin_run``, so ``self._next_order_id`` is also non-None. Pin
        # that for the type checker before the trailing sidecar write below.
        assert self._next_order_id is not None

        outcomes: list[WriteOutcome] = []
        for index, result in enumerate(results):
            if result.error is not None:
                # Transport-level failure: the worker reported a hard error
                # and ``result.point`` may be partially constructed, so it is
                # not safe to walk it through ``evaluate``. Mirror the
                # PostgresSink rolled-back-savepoint convention
                # (``point_id=None``, ``committed=False``, ``exit_code=-1``)
                # so navigators don't count this point as completed and
                # ``RunStats`` counts it as failed. The sink-side counter is
                # NOT advanced -- a transport failure didn't claim a point
                # id, and the sidecar therefore needs no update for it.
                outcomes.append(
                    WriteOutcome(
                        point_id=None,
                        exit_code=-1,
                        committed=False,
                        error_message=result.error.message,
                    )
                )
                continue

            order = self._order
            assert order is not None
            original_vs_points = order.vs_points
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
                    schema = _read_schema(self._schema_file)
                    next_order_id = _require_int_field(schema, self._schema_file, "next_order_id")
                    # Decrement ``next_order_id`` only; the in-memory
                    # ``_next_vs_point_id`` already reflects any point ids
                    # consumed earlier in this batch (e.g. results that
                    # produced zero rows but still claimed ids), and those
                    # consumed ids must not be re-issued on the retry.
                    _write_schema(
                        self._schema_file,
                        self.config.query,
                        next_order_id=next_order_id - 1,
                        next_vs_point_id=self._next_vs_point_id,
                    )
                    self._next_order_id = next_order_id - 1
                    self._order = None
                    self._order_id = None
                raise
            finally:
                order.vs_points = original_vs_points
            _append_rows(self.config.filename, self._columns, rows)
            if rows:
                self._rows_written = True
            point_id = self._next_vs_point_id
            self._next_vs_point_id += 1
            outcomes.append(
                WriteOutcome(
                    point_id=point_id,
                    exit_code=result.point.exit_code,
                    committed=True,
                )
            )
            if progress is not None:
                progress.tick()

        # Persist the (possibly advanced) ``next_vs_point_id`` once at the
        # end of the batch. ``next_order_id`` is rewritten too for symmetry;
        # ``begin_run`` already wrote the same value, so this is idempotent.
        _write_schema(
            self._schema_file,
            self.config.query,
            next_order_id=self._next_order_id,
            next_vs_point_id=self._next_vs_point_id,
        )
        return outcomes

    @override
    def finalize_run(self) -> None:
        return None

    @override
    def finalize(self) -> None:
        return None

    @override
    def supports_worker_writes(self) -> bool:
        return False

    @override
    def supports_progress(self) -> bool:
        return True
