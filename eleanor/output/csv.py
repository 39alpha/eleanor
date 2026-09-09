import copy
import csv
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self, cast, override
from uuid import UUID, uuid4

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
from eleanor.util import guard_is_dict, guard_is_path, is_list_of, require_dict, require_path

ID_COLUMNS: frozenset[str] = frozenset({"order_id", "point_id"})


@dataclass(kw_only=True)
class CsvSinkSettings(OutputSinkSettings):
    filename: Path
    query: dict[str, object]
    id_columns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()

        guard_is_path(self.filename, "filename")
        guard_is_dict(self.query, "query")

        if not is_list_of(self.id_columns, str):
            msg = "id_columns must be a list of strings"
            raise EleanorError(msg)

        unknown = [name for name in self.id_columns if name not in ID_COLUMNS]
        if unknown:
            choices = ", ".join(sorted(ID_COLUMNS))
            msg = f"unknown id_columns {unknown}; choose from {choices}"
            raise EleanorError(msg)

        duplicates = sorted({name for name in self.id_columns if self.id_columns.count(name) > 1})
        if duplicates:
            msg = f"duplicate id_columns: {', '.join(duplicates)}"
            raise EleanorError(msg)

    @classmethod
    @override
    def from_dict(cls, raw: dict[str, object]) -> Self:
        base_settings = OutputSinkSettings.from_dict(raw)
        filename = require_path(raw.get("filename"), "filename")
        query: dict[str, object] = require_dict(raw.get("query"), "query")
        raw_id_columns = raw.get("id_columns", [])
        if not is_list_of(raw_id_columns, str):
            msg = "id_columns must be a list of strings"
            raise EleanorError(msg)

        return cls(
            verbose=base_settings.verbose,
            filename=filename,
            query=query,
            id_columns=list(cast("list[str]", raw_id_columns)),
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


def _require_vs_points_seen(schema: dict[str, object], schema_path: Path) -> dict[str, int]:
    """Read the per-run point counters, keyed by the string form of the run id.

    The keys are ``str(UUID)`` rather than the ids themselves so the sidecar
    round-trips through plain YAML scalars.
    """
    vs_points_seen = schema.get("vs_points_seen", {})

    if not isinstance(vs_points_seen, dict):
        msg = f"csv schema {schema_path!r} has invalid vs_points_seen"
        raise EleanorError(msg)

    for key, value in cast(dict[object, object], vs_points_seen).items():
        if not isinstance(key, str):
            msg = f"csv schema {schema_path!r} has invalid key {key!r}"
            raise EleanorError(msg)
        if not isinstance(value, int) or isinstance(value, bool):
            msg = f"csv schema {schema_path!r} has invalid count for {key}: {value!r}"
            raise EleanorError(msg)

    return cast(dict[str, int], vs_points_seen)


def _require_order_versions(schema: dict[str, object], schema_path: Path) -> dict[str, str]:
    order_versions = schema.get("order_versions", {})

    if not isinstance(order_versions, dict):
        msg = f"csv schema {schema_path!r} has invalid order_versions"
        raise EleanorError(msg)

    for key, value in cast(dict[object, object], order_versions).items():
        if not isinstance(key, str):
            msg = f"csv schema {schema_path!r} has invalid key {key!r}"
            raise EleanorError(msg)
        if not isinstance(value, str):
            msg = f"csv schema {schema_path!r} has invalid version for {key}: {value!r}"
            raise EleanorError(msg)

    return cast(dict[str, str], order_versions)


def _write_schema(
    schema_path: Path,
    query: dict[str, object],
    *,
    vs_points_seen: dict[str, int],
    order_versions: dict[str, str],
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


def _binary_columns(compiled: CompiledQuery) -> frozenset[str]:
    """Names of the compiled columns whose terminal leaf is declared ``bytes``.

    These are the columns whose cells are written out as sidecar files and
    replaced by a relative path; see :func:`_extract_binary_assets`.
    """
    return frozenset(
        column.spec.name
        for column in compiled.compiled_columns
        if column.spec.path.meta is None
        and isinstance(column.terminal_kind, LeafField)
        and column.terminal_kind.declared_type is bytes
    )


def _reject_vs_point_index_columns(compiled: CompiledQuery) -> None:
    """Reject ``@index`` anchored on ``vs.Point``, pointing at ``id_columns``.

    This sink evaluates the query one VS point at a time, against an ``Order``
    copy whose ``vs_points`` holds only that point, so EQL's own ``@index`` is
    always ``0`` here -- it describes a position in a one-element list. The
    sink used to overwrite those columns with its own per-run counter, which
    made the emitted value silently disagree with the path that asked for it.
    That counter is now the ``point_id`` entry of ``id_columns``, so the
    overwrite is gone and the misleading path is refused outright.
    """
    for column in compiled.compiled_columns:
        path = column.spec.path
        if path.meta is None or path.meta.name != "index" or len(path.segments) == 0:
            continue
        head_alias = path.segments[0].name
        if head_alias not in compiled.scope_table:
            continue
        head_kind = compiled.scope_table[head_alias].type_kind
        if isinstance(head_kind, DataclassField) and head_kind.dataclass_type is vs.Point:
            msg = (
                f"csv query column {column.spec.name!r} uses {head_alias}.@index, which is always 0 "
                f"because this sink evaluates one VS point at a time; use id_columns: [point_id] instead"
            )
            raise EleanorError(msg)


def _prepare_rows(
    columns: list[str],
    id_values: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
) -> Sequence[Mapping[str, object]]:
    """Project each row onto ``columns``, filling the sink-owned id columns.

    ``id_values`` wins over anything the query produced: those column names are
    reserved for the sink and rejected as query column names at construction.
    """
    cooked: list[Mapping[str, object]] = []
    for row in rows:
        cooked_row = {column: ("" if (v := row.get(column)) is None else v) for column in columns}
        cooked_row.update(id_values)
        cooked.append(cooked_row)
    return cooked


def _extract_binary_assets(
    filename: Path,
    binary_columns: frozenset[str],
    order_id: UUID,
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


class CsvSink(AbstractOutputSink[UUID]):
    """Appends query-projected rows to a CSV file, with a YAML sidecar.

    Its ids are UUIDs. There is no sequence here to draw an integer from --
    the only durable state is the sidecar -- and a UUID keeps two runs
    appending to the same file from ever colliding on an id, which a
    ``max(seen) + 1`` scheme cannot promise. The ids reach the CSV through
    ``id_columns`` rather than through the query: identity belongs to this
    sink, not to the object graph EQL projects.
    """

    settings: CsvSinkSettings
    _compiled: CompiledQuery
    _columns: list[str]
    _id_columns: list[str]
    _order_id: UUID | None
    _order: Order | None
    _schema_file: Path
    _binary_columns: frozenset[str]
    _vs_points_seen: dict[str, int]
    _order_versions: dict[str, str]

    def __init__(self, settings: CsvSinkSettings) -> None:
        self.settings = settings
        self._compiled = compile_query(Order, settings.query)
        _reject_vs_point_index_columns(self._compiled)

        query_columns = [spec.name for spec in self._compiled.columns]
        self._id_columns = list(settings.id_columns)
        collisions = sorted(set(self._id_columns) & set(query_columns))
        if collisions:
            msg = f"id_columns collide with query column names: {', '.join(collisions)}"
            raise EleanorError(msg)

        self._columns = self._id_columns + query_columns
        self._order_id = None
        self._order = None
        self._schema_file = _schema_path(settings.filename)
        self._binary_columns = _binary_columns(self._compiled)
        self._vs_points_seen = {}
        self._order_versions = {}

    @override
    def __getstate__(self) -> dict[str, object]:
        state: dict[str, object] = dict(self.__dict__)
        del state["_compiled"]
        if self._order is not None:
            order = copy.copy(self._order)
            order.vs_points = []
            state["_order"] = order
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

    @override
    def begin_run(self, order: Order, *, requested_id: str | None = None) -> UUID:
        """Mint a UUID for a new run, or resume the one ``requested_id`` names.

        A resumable run is one the sidecar knows about, so a token must parse
        as a UUID *and* already have a point counter; otherwise there is no
        run here to extend and appending under it would silently start a new
        one inside the same file.
        """
        query = self.settings.query
        schema_file = self._schema_file
        if self._order is order:
            assert self._order_id is not None
            return self._order_id

        if requested_id is None:
            order_id = uuid4()
        else:
            try:
                order_id = UUID(requested_id)
            except ValueError as error:
                msg = f"csv sink order id must be a UUID, got {requested_id!r}"
                raise EleanorError(msg) from error
            if str(order_id) not in self._vs_points_seen:
                msg = f"csv sink has no order {order_id} to extend in {schema_file.name}"
                raise EleanorError(msg)

        key = str(order_id)
        existing_version = self._order_versions.get(key)
        if existing_version is not None and order.eleanor_version != existing_version:
            msg = "cannot extend an order generated by a different version of Eleanor"
            raise EleanorError(msg)
        self._order_versions[key] = order.eleanor_version

        self._vs_points_seen[key] = self._vs_points_seen.get(key, 0)
        _write_schema(
            schema_file,
            query,
            vs_points_seen=self._vs_points_seen,
            order_versions=self._order_versions,
        )

        self._order = order
        self._order_id = order_id

        return order_id

    @override
    def prepare_batch(self, order_id: UUID, results: Sequence[ComputeResult]) -> Sequence[CsvPrepared]:
        """Evaluate the query for each point; return its rows.

        Runs in a worker. Pure with respect to sink state: the shallow
        ``Order`` copy is discarded, and the point counter, the CSV file and
        the sidecar are all left to :meth:`commit_batch`.

        ``order_id`` is not needed to evaluate the query -- the id columns are
        filled in by :meth:`commit_batch`, which owns the point counter that
        one of them carries.
        """
        _ = order_id

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

    def _id_values(self, order_id: UUID, point_id: int) -> Mapping[str, object]:
        """The value for each configured id column, for one VS point's rows.

        Every row of a single point shares both values: the run id is constant
        for the run, and the point counter identifies the point, not the row.
        """
        available: Mapping[str, object] = {"order_id": str(order_id), "point_id": point_id}
        return {name: available[name] for name in self._id_columns}

    @override
    def commit_batch(
        self,
        order_id: UUID,
        prepared: Sequence[object],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        """Fill each row set's id columns and append it.

        Runs in the parent, which is what lets ``_vs_points_seen`` stay a
        single authoritative counter: it feeds both the ``point_id`` column
        and the binary-asset filenames, so it cannot be handed to concurrent
        workers.
        """
        filename = self.settings.filename

        if self._order is None:
            msg = "csv sink commit_batch called before begin_run"
            raise EleanorError(msg)

        if not filename.exists():
            msg = "csv sink commit_batch requires initialize() to create the CSV header"
            raise EleanorError(msg)

        key = str(order_id)
        if key not in self._vs_points_seen:
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

                current_point_id = self._vs_points_seen[key]
                rows = _extract_binary_assets(
                    filename,
                    self._binary_columns,
                    order_id,
                    current_point_id,
                    item.rows,
                )
                rows = _prepare_rows(
                    self._columns,
                    self._id_values(order_id, current_point_id),
                    rows,
                )
                for row in rows:
                    writer.writerow(row)
                handle.flush()

                committed = False
                if rows:
                    committed = True
                    self._vs_points_seen[key] += 1
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
    def target_key(self) -> object:
        """The CSV file, resolved so two spellings of one path still collide."""
        return self.settings.filename.resolve()

    @override
    def supports_worker_commit(self) -> bool:
        return False

    @override
    def supports_background_commit(self) -> bool:
        return True

    @override
    def supports_progress(self) -> bool:
        return True


__all__ = [
    "CsvPrepared",
    "CsvSink",
    "CsvSinkSettings",
]
