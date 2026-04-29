import dataclasses
import sys
import types
from dataclasses import dataclass
from typing import TypeGuard, cast, get_args, get_origin, get_type_hints

from .aliases import singularize
from .coercion import coerce_filter_value
from .errors import InvalidFilter, InvalidPath
from .path import IterFilter, MatchFilter, Path, Predicate, Segment, match_filter_text, path_to_string, predicate_text


@dataclass(frozen=True, slots=True)
class LeafField:
    name: str
    declared_type: type[object]
    optional: bool


@dataclass(frozen=True, slots=True)
class DataclassField:
    name: str
    dataclass_type: type[object]
    optional: bool


@dataclass(frozen=True, slots=True)
class ListField:
    name: str
    element_type: object
    element_kind: "FieldKind"
    optional: bool


@dataclass(frozen=True, slots=True)
class DictField:
    name: str
    key_type: object
    value_type: object
    value_kind: "FieldKind"
    optional: bool


type FieldKind = LeafField | DataclassField | ListField | DictField


@dataclass(frozen=True, slots=True)
class StepInfo:
    segment: Segment
    kind_before: FieldKind | None
    kind_after: FieldKind
    alias: str
    # Kind produced by resolving ``segment.name`` against the parent type,
    # *before* any of the segment's filters are applied. For an iter-filtered
    # segment ``foo[*]`` whose parent declares ``foo: list[T]``, this is the
    # ``ListField`` for ``foo``; ``kind_after`` is the post-filter element
    # kind. Consumers that need to know whether an iter-bound alias was
    # iterating a list vs a dict (e.g. spec §7.1 meta-accessor validation)
    # consult this field.
    segment_kind: FieldKind


def unwrap_optional(t: object) -> tuple[object, bool]:
    origin = get_origin(t)
    if not _is_union_origin(origin):
        return t, False

    args = get_args(t)
    if len(args) != 2 or type(None) not in args:
        return t, False

    if args[0] is type(None):
        return args[1], True
    return args[0], True


def classify_field(name: str, declared: object) -> FieldKind:
    inner, optional = unwrap_optional(declared)

    if is_dataclass_type(inner):
        return DataclassField(name=name, dataclass_type=inner, optional=optional)

    origin = get_origin(inner)
    if origin is list:
        args = get_args(inner)
        element_declared = args[0] if len(args) == 1 else object
        element_kind = classify_field(name, element_declared)
        return ListField(name=name, element_type=element_declared, element_kind=element_kind, optional=optional)

    if origin is dict:
        args = get_args(inner)
        key_type = args[0] if len(args) == 2 else object
        value_declared = args[1] if len(args) == 2 else object
        value_kind = classify_field(name, value_declared)
        return DictField(
            name=name, key_type=key_type, value_type=value_declared, value_kind=value_kind, optional=optional
        )

    declared_type = inner if isinstance(inner, type) else object
    return LeafField(name=name, declared_type=declared_type, optional=optional)


def dataclass_fields(t: type[object]) -> list[FieldKind]:
    if not is_dataclass_type(t):
        return []
    field_kinds: list[FieldKind] = []
    hints = _resolve_hints(t)
    for field in dataclasses.fields(t):  # pyright: ignore[reportArgumentType]
        declared = hints.get(field.name, field.type)
        field_kinds.append(classify_field(field.name, declared))
    return field_kinds


def leaf_fields(t: type[object]) -> list[LeafField]:
    return [field for field in dataclass_fields(t) if isinstance(field, LeafField)]


def walk_path(start_type: type[object], path: Path) -> list[StepInfo]:
    path_text = path_to_string(path)
    current_kind: FieldKind = DataclassField(name="__root__", dataclass_type=start_type, optional=False)
    steps: list[StepInfo] = []

    for index, segment in enumerate(path.segments):
        kind_before = None if index == 0 else current_kind
        segment_kind = resolve_segment_kind(current_kind, segment.name, path_text)
        kind_after = _apply_filters(segment_kind, segment.filters, path_text, segment.name)
        alias = singularize(segment.name) if _contains_iter_filter(segment) else segment.name
        steps.append(
            StepInfo(
                segment=segment,
                kind_before=kind_before,
                kind_after=kind_after,
                alias=alias,
                segment_kind=segment_kind,
            )
        )
        current_kind = kind_after

    return steps


def is_dataclass_type(t: object) -> TypeGuard[type[object]]:
    return dataclasses.is_dataclass(t) and isinstance(t, type)


def resolve_segment_kind(current: FieldKind, segment_name: str, path_text: str) -> FieldKind:
    """Resolve a single path segment against ``current`` to its FieldKind.

    Raises ``InvalidPath`` if ``current`` is not a dataclass or if the
    segment name does not name a field on it.
    """
    if not isinstance(current, DataclassField):
        raise InvalidPath(path_text, segment_name, owner_type(current))

    for field in dataclass_fields(current.dataclass_type):
        if field.name == segment_name:
            return field

    raise InvalidPath(path_text, segment_name, current.dataclass_type)


def apply_iter_filter(kind: FieldKind, path_text: str, segment_name: str) -> FieldKind:
    """Apply an iter filter (``[*]``) to ``kind``, returning the element kind.

    Raises ``InvalidFilter`` if ``kind`` is not iterable.
    """
    if isinstance(kind, ListField):
        return kind.element_kind
    if isinstance(kind, DictField):
        return kind.value_kind
    raise InvalidFilter(path_text, segment_name, "*")


def owner_type(kind: FieldKind) -> type[object]:
    """Return the user-facing owner type for ``kind`` for use in error messages.

    DataclassField/LeafField pass through their declared type; ListField and
    DictField collapse to the bare ``list``/``dict`` types since the element
    type alone is not informative for ``InvalidPath`` messages.
    """
    if isinstance(kind, DataclassField):
        return kind.dataclass_type
    if isinstance(kind, LeafField):
        return kind.declared_type
    if isinstance(kind, ListField):
        return list
    return dict


def coercion_target(candidate: object) -> type[object]:
    """Narrow ``candidate`` to a ``type`` for ``coerce_filter_value``.

    Generic parameters or other non-type annotations fall back to ``object``,
    which ``coerce_filter_value`` handles by raising ``InvalidFilterValue``.
    """
    if isinstance(candidate, type):
        return candidate
    return object


def _resolve_hints(t: type[object]) -> dict[str, object]:
    module = sys.modules[t.__module__]
    hints = get_type_hints(t, globalns=vars(module))
    return cast(dict[str, object], hints)


def _apply_filters(
    kind: FieldKind, filters: tuple[IterFilter | MatchFilter, ...], path_text: str, segment_name: str
) -> FieldKind:
    current = kind
    for filter_expr in filters:
        if isinstance(filter_expr, IterFilter):
            current = apply_iter_filter(current, path_text, segment_name)
            continue
        current, _ = resolve_match_filter(current, filter_expr, path_text, segment_name)
    return current


def resolve_match_filter(
    kind: FieldKind, filter_expr: MatchFilter, path_text: str, segment_name: str
) -> tuple[FieldKind, list[tuple[Predicate, object]]]:
    """Validate ``filter_expr`` against ``kind`` and resolve each predicate.

    Dispatches on whether ``kind`` is a ``ListField`` or ``DictField`` and
    runs per-kind validation:

    - ``ListField``: ``element_kind`` must be a ``DataclassField``; each
      predicate field must name a ``LeafField`` on that dataclass.
    - ``DictField``: a predicate field of ``"key"`` is coerced against
      ``key_type``; otherwise the field must name a ``LeafField`` on the
      value's dataclass type (if any).

    For each predicate, the matching declared type is coerced via
    ``coerce_filter_value``. The function returns the post-filter
    ``FieldKind`` (the element/value kind) along with a list of
    ``(predicate, coerced_value)`` tuples in input order.

    Raises ``InvalidFilter`` if ``kind`` is neither list nor dict, or if any
    predicate references an unknown or non-leaf field.
    Raises ``InvalidFilterValue`` (propagated from ``coerce_filter_value``)
    if a predicate value can't be coerced to the target type.

    This helper is the single source of truth for match-filter validation;
    both ``walk_path`` (via ``_apply_filters``) and the compiler
    (``compiler._compile_match_filter``) call into it.
    """
    if isinstance(kind, ListField):
        resolved = _resolve_list_match(kind, filter_expr, path_text, segment_name)
        return kind.element_kind, resolved
    if isinstance(kind, DictField):
        resolved = _resolve_dict_match(kind, filter_expr, path_text, segment_name)
        return kind.value_kind, resolved
    raise InvalidFilter(path_text, segment_name, match_filter_text(filter_expr))


def _resolve_list_match(
    kind: ListField, filter_expr: MatchFilter, path_text: str, segment_name: str
) -> list[tuple[Predicate, object]]:
    if not isinstance(kind.element_kind, DataclassField):
        raise InvalidFilter(path_text, segment_name, match_filter_text(filter_expr))

    available = {field.name: field for field in dataclass_fields(kind.element_kind.dataclass_type)}
    resolved: list[tuple[Predicate, object]] = []
    for predicate in filter_expr.predicates:
        target = available.get(predicate.field)
        if target is None or not isinstance(target, LeafField):
            raise InvalidFilter(path_text, segment_name, predicate_text(predicate))
        coerced = coerce_filter_value(
            coercion_target(target.declared_type),
            predicate.value,
            path=path_text,
            predicate=predicate_text(predicate),
        )
        resolved.append((predicate, coerced))
    return resolved


def _resolve_dict_match(
    kind: DictField, filter_expr: MatchFilter, path_text: str, segment_name: str
) -> list[tuple[Predicate, object]]:
    available: dict[str, FieldKind] = {}
    if isinstance(kind.value_kind, DataclassField):
        available = {field.name: field for field in dataclass_fields(kind.value_kind.dataclass_type)}

    resolved: list[tuple[Predicate, object]] = []
    for predicate in filter_expr.predicates:
        if predicate.field == "key":
            coerced = coerce_filter_value(
                coercion_target(kind.key_type),
                predicate.value,
                path=path_text,
                predicate=predicate_text(predicate),
            )
            resolved.append((predicate, coerced))
            continue

        target = available.get(predicate.field)
        if target is None or not isinstance(target, LeafField):
            raise InvalidFilter(path_text, segment_name, predicate_text(predicate))
        coerced = coerce_filter_value(
            coercion_target(target.declared_type),
            predicate.value,
            path=path_text,
            predicate=predicate_text(predicate),
        )
        resolved.append((predicate, coerced))
    return resolved


def _contains_iter_filter(segment: Segment) -> bool:
    return any(isinstance(filter_expr, IterFilter) for filter_expr in segment.filters)


def _is_union_origin(origin: object) -> bool:
    return origin is types.UnionType or str(origin) == "typing.Union"
