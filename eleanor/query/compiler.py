from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from eleanor.query.coercion import MissingPolicy, parse_missing_policy
from eleanor.query.columns import ColumnSpec, assign_column_names, desugar_columns, validate_column_paths
from eleanor.query.errors import ParseError
from eleanor.query.path import IterFilter, MatchFilter, Path, Segment, path_to_string
from eleanor.query.presets import BUILTIN_PRESETS, PresetFn
from eleanor.query.reflection import (
    DataclassField,
    FieldKind,
    apply_iter_filter,
    resolve_match_filter,
    resolve_segment_kind,
)
from eleanor.query.scope import AmbientScopeTable, resolve_row_scope, validate_short_forms_for_root

CURRENT_VERSION = 1


@dataclass(frozen=True, slots=True)
class CompiledPredicate:
    field: str
    value: str
    value_quoted: bool
    coerced_value: object


@dataclass(frozen=True, slots=True)
class CompiledIterFilter:
    pass


@dataclass(frozen=True, slots=True)
class CompiledMatchFilter:
    predicates: tuple[CompiledPredicate, ...]


type CompiledFilter = CompiledIterFilter | CompiledMatchFilter


@dataclass(frozen=True, slots=True)
class CompiledSegment:
    name: str
    filters: tuple[CompiledFilter, ...]


@dataclass(frozen=True, slots=True)
class CompiledPath:
    path: Path
    segments: tuple[CompiledSegment, ...]


@dataclass(frozen=True, slots=True)
class CompiledColumn:
    spec: ColumnSpec
    compiled_path: CompiledPath
    terminal_kind: FieldKind | None


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    root_type: type[object]
    row_scope_path: Path
    scope_table: AmbientScopeTable
    columns: tuple[ColumnSpec, ...]
    file_default_policy: MissingPolicy
    version: int
    row_scope_compiled_path: CompiledPath
    compiled_columns: tuple[CompiledColumn, ...]


def compile_query(
    root_type: type[object],
    query: Mapping[str, object],
    *,
    presets: Mapping[str, PresetFn] | None = None,
    allow_container_terminals: bool = False,
) -> CompiledQuery:
    """Compile ``query`` against ``root_type`` and return a ``CompiledQuery``.

    ``presets`` selects the preset bundle in effect for this compile (spec
    §10.2). ``None`` means "use the canonical bundle" (``BUILTIN_PRESETS``);
    an empty mapping disables presets entirely so any ``{preset: name}``
    directive raises ``UnknownPreset``; any other ``Mapping[str, PresetFn]``
    is used as-is. Distinguishing ``None`` from ``{}`` lets callers
    explicitly opt out of the canonical bundle without re-registering.
    """
    allowed_keys = {"row_scope", "columns", "on_missing", "version"}
    unknown_keys = sorted(key for key in query if key not in allowed_keys)
    if unknown_keys:
        raise ParseError(f"unknown query keys: {', '.join(unknown_keys)}", position=None)

    if "row_scope" not in query:
        raise ParseError("missing required key: row_scope", position=None)
    if "columns" not in query:
        raise ParseError("missing required key: columns", position=None)

    version = _parse_version(query.get("version", CURRENT_VERSION))
    file_default_policy = (
        parse_missing_policy(query["on_missing"]) if "on_missing" in query else parse_missing_policy("blank")
    )

    _validate_short_forms_for_root_cached(root_type)

    row_scope_path, scope_table = resolve_row_scope(root_type, query["row_scope"])

    raw_columns = query["columns"]
    if not isinstance(raw_columns, Sequence) or isinstance(raw_columns, (str, bytes)):
        raise ParseError("columns must be a sequence", position=None)

    bundle = BUILTIN_PRESETS if presets is None else presets
    desugared = desugar_columns(raw_columns, scope_table, presets=bundle)
    validate_column_paths(desugared, scope_table, allow_container_terminals=allow_container_terminals)
    named_columns = assign_column_names(desugared)

    compiled_row_scope = _compile_row_scope(root_type, row_scope_path)
    compiled_columns = tuple(_compile_column(spec, scope_table) for spec in named_columns)

    return CompiledQuery(
        root_type=root_type,
        row_scope_path=row_scope_path,
        scope_table=scope_table,
        columns=tuple(named_columns),
        file_default_policy=file_default_policy,
        version=version,
        row_scope_compiled_path=compiled_row_scope,
        compiled_columns=compiled_columns,
    )


@lru_cache(maxsize=None)
def _validate_short_forms_for_root_cached(root_type: type[object]) -> None:
    """Run live-reflection short-form validation once per root type.

    The check is conceptually a startup-time invariant on the data model, but
    we don't see ``root_type`` until ``compile_query`` is called. Cache hits
    skip the BFS; cache misses run the walk and remember success.
    ``functools.lru_cache`` does not memoize raised exceptions, so a failing
    type re-validates on every call (which is the desired behavior - a fix
    to the data model takes effect immediately).
    """
    validate_short_forms_for_root(root_type)


def _parse_version(raw: object) -> int:
    # ``bool`` is a subclass of ``int`` in Python; ``True == 1`` and ``False == 0``
    # would otherwise sneak past the equality check.
    if isinstance(raw, int) and not isinstance(raw, bool) and raw == CURRENT_VERSION:
        return CURRENT_VERSION
    raise ParseError("unsupported query version", position=None)


def _compile_row_scope(root_type: type[object], path: Path) -> CompiledPath:
    if len(path.segments) == 0:
        return CompiledPath(path=path, segments=())
    start_kind: FieldKind = DataclassField(name="order", dataclass_type=root_type, optional=False)
    segments, _ = _compile_segments(start_kind, path.segments, path_to_string(path))
    return CompiledPath(path=path, segments=segments)


def _compile_column(spec: ColumnSpec, scope_table: AmbientScopeTable) -> CompiledColumn:
    path = spec.path
    if len(path.segments) == 0:
        return CompiledColumn(spec=spec, compiled_path=CompiledPath(path=path, segments=()), terminal_kind=None)

    head = path.segments[0]
    alias_scope = scope_table[head.name]
    compiled_head = CompiledSegment(name=head.name, filters=())
    if len(path.segments) == 1:
        compiled_path = CompiledPath(path=path, segments=(compiled_head,))
        return CompiledColumn(spec=spec, compiled_path=compiled_path, terminal_kind=alias_scope.type_kind)

    tail_segments, terminal_kind = _compile_segments(alias_scope.type_kind, path.segments[1:], path_to_string(path))
    compiled_path = CompiledPath(path=path, segments=(compiled_head, *tail_segments))
    return CompiledColumn(spec=spec, compiled_path=compiled_path, terminal_kind=terminal_kind)


def _compile_segments(
    start_kind: FieldKind,
    segments: tuple[Segment, ...],
    path_text: str,
) -> tuple[tuple[CompiledSegment, ...], FieldKind]:
    current = start_kind
    compiled: list[CompiledSegment] = []

    for segment in segments:
        segment_kind = resolve_segment_kind(current, segment.name, path_text)
        current_after_filters = segment_kind
        compiled_filters: list[CompiledFilter] = []

        for filter_expr in segment.filters:
            if isinstance(filter_expr, IterFilter):
                compiled_filters.append(CompiledIterFilter())
                current_after_filters = apply_iter_filter(current_after_filters, path_text, segment.name)
                continue

            compiled_filter, current_after_filters = _compile_match_filter(
                current_after_filters,
                filter_expr,
                path_text,
                segment.name,
            )
            compiled_filters.append(compiled_filter)

        compiled.append(CompiledSegment(name=segment.name, filters=tuple(compiled_filters)))
        current = current_after_filters

    return tuple(compiled), current


def _compile_match_filter(
    kind: FieldKind,
    filter_expr: MatchFilter,
    path_text: str,
    segment_name: str,
) -> tuple[CompiledMatchFilter, FieldKind]:
    """Compile a match filter into ``CompiledPredicate``s with cached coercions.

    Validation and coercion are delegated to ``reflection.resolve_match_filter``,
    which is the single source of truth for match-filter dispatch and per-kind
    rules. The compiler only wraps the resolved tuples into the compiled
    artifacts it needs at evaluation time.
    """
    post_kind, resolved = resolve_match_filter(kind, filter_expr, path_text, segment_name)
    compiled_predicates = tuple(
        CompiledPredicate(
            field=predicate.field,
            value=predicate.value,
            value_quoted=predicate.value_quoted,
            coerced_value=coerced,
        )
        for predicate, coerced in resolved
    )
    return CompiledMatchFilter(predicates=compiled_predicates), post_kind
