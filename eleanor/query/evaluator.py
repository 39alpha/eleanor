from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import cast

from eleanor.query.coercion import MissingPolicy
from eleanor.query.compiler import (
    CompiledColumn,
    CompiledIterFilter,
    CompiledMatchFilter,
    CompiledPath,
    CompiledPredicate,
    CompiledQuery,
)
from eleanor.query.errors import MultipleMatchError, PathMissError
from eleanor.query.path import Path, path_to_string

_MISS = object()
_MISSING_ATTR = object()


@dataclass(frozen=True, slots=True)
class IterPosition:
    """Spec §7.1: per-iter-binding meta info threaded through the row walk.

    ``index`` is the 0-based position within the iter source container.
    ``key`` is the dict key at the current iteration; ``None`` for list-iter
    aliases. Validator guarantees ``@key`` is only requested for dict-iter
    aliases, so ``key`` is never read when it is ``None`` from a query path.
    """

    index: int
    key: object | None


def evaluate(compiled: CompiledQuery, root: object) -> Iterator[Mapping[str, object]]:
    aliases_by_path = _aliases_by_path(compiled)
    if len(compiled.row_scope_compiled_path.segments) == 0:
        # ``resolve_row_scope`` already binds both ``order`` and ``self`` to
        # the empty path for a root-scope query, so iterating
        # ``aliases_by_path[Path(())]`` is sufficient; no separate
        # ``self``-injection fallback is needed.
        binding: dict[str, object] = {}
        for alias in aliases_by_path.get(Path(segments=tuple()), []):
            binding[alias] = root
        # Empty row_scope binds no iter aliases; meta_binding is empty. The
        # validator rejects meta paths anchored on a non-iter-bound alias,
        # so this is consistent.
        yield _evaluate_row(compiled, binding, {}, row_index=0)
        return

    for row_index, (binding, meta_binding) in enumerate(_iter_row_scope_bindings(compiled, root, aliases_by_path)):
        yield _evaluate_row(compiled, binding, meta_binding, row_index=row_index)


def _evaluate_row(
    compiled: CompiledQuery,
    binding: dict[str, object],
    meta_binding: Mapping[str, IterPosition],
    *,
    row_index: int,
) -> Mapping[str, object]:
    row: dict[str, object] = {}
    for compiled_column in compiled.compiled_columns:
        value, missing, missing_segment = _evaluate_column_path(compiled_column, binding, meta_binding)
        if not missing:
            row[compiled_column.spec.name] = value
            continue

        policy = compiled_column.spec.on_missing or compiled.file_default_policy
        row[compiled_column.spec.name] = _missing_value(policy, compiled_column, row_index, missing_segment)
    return row


def _iter_row_scope_bindings(
    compiled: CompiledQuery,
    root: object,
    aliases_by_path: Mapping[Path, list[str]],
) -> Iterator[tuple[dict[str, object], dict[str, IterPosition]]]:
    binding: dict[str, object] = {}
    meta_binding: dict[str, IterPosition] = {}
    for alias in aliases_by_path.get(Path(segments=tuple()), []):
        binding[alias] = root

    row_scope_text = path_to_string(compiled.row_scope_compiled_path.path)
    yield from _walk_row_scope(
        compiled.row_scope_compiled_path,
        root,
        index=0,
        binding=binding,
        meta_binding=meta_binding,
        aliases_by_path=aliases_by_path,
        row_scope_text=row_scope_text,
    )


def _walk_row_scope(
    compiled_path: CompiledPath,
    node: object,
    *,
    index: int,
    binding: dict[str, object],
    meta_binding: dict[str, IterPosition],
    aliases_by_path: Mapping[Path, list[str]],
    row_scope_text: str,
) -> Iterator[tuple[dict[str, object], dict[str, IterPosition]]]:
    if index >= len(compiled_path.segments):
        yield binding, meta_binding
        return
    if node is None:
        return

    segment = compiled_path.segments[index]
    child = _get_attr(node, segment.name)
    if len(segment.filters) == 0:
        # row_scope segments without filters: ``None`` means we can't descend.
        # Always treat None as a miss (terminal-None handling lives in
        # ``_evaluate_column_path``, not here). No iter binding is produced.
        values_with_meta: list[tuple[object, IterPosition | None]] = [] if child is None else [(child, None)]
    else:
        values_with_meta = _segment_values_with_meta(child, segment.filters, path_text=row_scope_text)
    if not values_with_meta:
        return

    prefix = Path(segments=compiled_path.path.segments[: index + 1])
    aliases_at_prefix = aliases_by_path.get(prefix, [])
    for value, position in values_with_meta:
        next_binding = dict(binding)
        next_meta = dict(meta_binding)
        for alias in aliases_at_prefix:
            next_binding[alias] = value
            if position is not None:
                next_meta[alias] = position
        yield from _walk_row_scope(
            compiled_path,
            value,
            index=index + 1,
            binding=next_binding,
            meta_binding=next_meta,
            aliases_by_path=aliases_by_path,
            row_scope_text=row_scope_text,
        )


def _evaluate_column_path(
    compiled_column: CompiledColumn,
    binding: Mapping[str, object],
    meta_binding: Mapping[str, IterPosition],
) -> tuple[object, bool, str]:
    compiled_path = compiled_column.compiled_path
    if len(compiled_path.segments) == 0:
        return None, True, "<root>"

    head = compiled_path.segments[0]
    start = binding.get(head.name, _MISS)
    if start is _MISS:
        return None, True, head.name

    meta = compiled_path.path.meta
    if meta is not None:
        # Spec §7.1: meta-accessor terminal. The validator guarantees the
        # head alias is iter-bound, so ``meta_binding`` always has an entry
        # at runtime; the ``get`` lookup below mirrors the head ``binding``
        # lookup above for parallelism.
        position = meta_binding.get(head.name)
        if position is None:
            return None, True, head.name
        if meta.name == "index":
            return position.index, False, ""
        # Validator guarantees ``@key`` is only on dict-iter aliases, so
        # ``position.key`` is set whenever this branch executes.
        return position.key, False, ""

    values: list[object] = [start]
    path_text = path_to_string(compiled_path.path)
    for index, segment in enumerate(compiled_path.segments[1:], start=1):
        is_terminal = index == len(compiled_path.segments) - 1
        next_values: list[object] = []
        for value in values:
            child = _get_attr(value, segment.name)
            if len(segment.filters) == 0:
                # No filters: ``child`` *is* the segment's value. ``None`` is
                # a miss for non-terminal segments (we cannot descend through
                # it) but a legitimate leaf value for the terminal segment
                # of a column path.
                if child is None and not is_terminal:
                    continue
                next_values.append(child)
                continue
            next_values.extend(_segment_values(child, segment.filters, path_text=path_text))
        if len(next_values) == 0:
            return None, True, segment.name
        values = next_values

    # Per spec §8, column paths cannot contain iter filters; match filters
    # match exactly 0 or 1 element (or raise MultipleMatchError). Combined
    # with the early return on empty next_values above, `values` always
    # contains exactly one element at this point.
    return values[0], False, ""


def _segment_values(
    value: object,
    filters: tuple[CompiledIterFilter | CompiledMatchFilter, ...],
    *,
    path_text: str,
) -> list[object]:
    """Apply a non-empty sequence of compiled filters to ``value``.

    Callers handle the no-filter case directly because they need to make
    different decisions about ``None`` (e.g., terminal-None vs. miss).
    A ``None`` ``value`` here is always a miss because filters can't be
    applied to it.
    """
    assert len(filters) > 0, "_segment_values must be called with non-empty filters"
    if value is None:
        return []

    states: list[object] = [value]
    for filter_expr in filters:
        next_states: list[object] = []
        for state in states:
            if isinstance(filter_expr, CompiledIterFilter):
                next_states.extend(_iter_filter_values(state))
                continue
            match = _match_filter_value(state, filter_expr, path_text)
            if match is _MISS:
                continue
            next_states.append(match)
        states = next_states
        if len(states) == 0:
            return []
    return states


def _segment_values_with_meta(
    value: object,
    filters: tuple[CompiledIterFilter | CompiledMatchFilter, ...],
    *,
    path_text: str,
) -> list[tuple[object, IterPosition | None]]:
    """Like ``_segment_values`` but pairs each value with its iter position.

    Used by the row_scope walker to bind ``IterPosition`` for iter-bound
    aliases (spec §7.1). The position reflects the OUTERMOST iter filter
    in the chain (the one that introduced the alias). For chains with no
    iter filter, every produced value carries position ``None``.
    """
    assert len(filters) > 0, "_segment_values_with_meta must be called with non-empty filters"
    if value is None:
        return []

    states: list[tuple[object, IterPosition | None]] = [(value, None)]
    for filter_expr in filters:
        next_states: list[tuple[object, IterPosition | None]] = []
        for state, position in states:
            if isinstance(filter_expr, CompiledIterFilter):
                if position is None:
                    if isinstance(state, list):
                        for i, item in enumerate(cast(list[object], state)):
                            next_states.append((item, IterPosition(index=i, key=None)))
                    elif isinstance(state, dict):
                        for i, (k, v) in enumerate(cast(dict[object, object], state).items()):
                            next_states.append((v, IterPosition(index=i, key=k)))
                    # else: non-iterable -> empty (consistent with ``_iter_filter_values``).
                else:
                    # Inner [*] in a multi-filter segment: preserve the outer
                    # position by convention. The spec does not define @index
                    # semantics for double-iteration on a single segment; this
                    # branch is unreachable from normal Eleanor data models.
                    for sub in _iter_filter_values(state):
                        next_states.append((sub, position))
            else:
                match = _match_filter_value(state, filter_expr, path_text)
                if match is _MISS:
                    continue
                next_states.append((match, position))
        if not next_states:
            return []
        states = next_states
    return states


def _iter_filter_values(state: object) -> list[object]:
    if isinstance(state, list):
        values = cast(list[object], state)
        return [item for item in values]
    if isinstance(state, dict):
        values = cast(dict[object, object], state).values()
        return [item for item in values]
    return []


def _match_filter_value(state: object, filter_expr: CompiledMatchFilter, path_text: str) -> object:
    matches: list[object] = []
    if isinstance(state, list):
        for item in cast(list[object], state):
            if _list_item_matches(item, filter_expr.predicates):
                matches.append(item)
    elif isinstance(state, dict):
        for key, value in cast(dict[object, object], state).items():
            if _dict_item_matches(key, value, filter_expr.predicates):
                matches.append(value)
    else:
        return _MISS

    if len(matches) == 0:
        return _MISS
    if len(matches) > 1:
        raise MultipleMatchError(path_text, _compiled_match_text(filter_expr), len(matches))
    return matches[0]


def _list_item_matches(item: object, predicates: tuple[CompiledPredicate, ...]) -> bool:
    for predicate in predicates:
        actual = getattr(item, predicate.field, _MISSING_ATTR)
        if actual is _MISSING_ATTR or actual != predicate.coerced_value:
            return False
    return True


def _dict_item_matches(key: object, value: object, predicates: tuple[CompiledPredicate, ...]) -> bool:
    for predicate in predicates:
        if predicate.field == "key":
            actual = key
        else:
            actual = getattr(value, predicate.field, _MISSING_ATTR)
        if actual is _MISSING_ATTR or actual != predicate.coerced_value:
            return False
    return True


def _get_attr(node: object, name: str) -> object:
    if node is None:
        return None
    value = getattr(node, name, _MISSING_ATTR)
    if value is _MISSING_ATTR:
        return None
    return value


def _aliases_by_path(compiled: CompiledQuery) -> dict[Path, list[str]]:
    aliases: dict[Path, list[str]] = defaultdict(list)
    for alias, scope_entry in compiled.scope_table.items():
        aliases[scope_entry.path].append(alias)
    return aliases


def _missing_value(policy: MissingPolicy, column: CompiledColumn, row_index: int, segment: str) -> object:
    if policy == "blank":
        return None
    if policy == "null":
        if column.spec.has_default:
            return column.spec.default
        return None
    raise PathMissError(row_index, column.spec.name, segment)


def _compiled_match_text(filter_expr: CompiledMatchFilter) -> str:
    return ",".join(_compiled_predicate_text(predicate) for predicate in filter_expr.predicates)


def _compiled_predicate_text(predicate: CompiledPredicate) -> str:
    if predicate.value_quoted:
        escaped = predicate.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{predicate.field}="{escaped}"'
    return f"{predicate.field}={predicate.value}"
