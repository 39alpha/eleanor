from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from .coercion import MissingPolicy, parse_missing_policy
from .errors import (
    ColumnNameCollision,
    InvalidFilter,
    InvalidFilterValue,
    InvalidMetaAccessor,
    InvalidPath,
    ParseError,
    SplatUnknownField,
    UnknownPreset,
    UnknownScope,
)
from .path import IterFilter, Path, Segment, parse_path, path_to_string
from .presets import PresetFn
from .reflection import DataclassField, DictField, LeafField, leaf_fields, owner_type, walk_path
from .scope import AmbientScopeTable

# Closed canonical set of meta-accessor names (spec §7.1). Update only
# alongside the spec.
_CANONICAL_META_ACCESSORS: frozenset[str] = frozenset({"index", "key"})

# Default empty bundle for callers that don't supply one. ``MappingProxyType``
# keeps the default safely immutable.
_EMPTY_PRESETS: Mapping[str, PresetFn] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class BarePath:
    pass


@dataclass(frozen=True, slots=True)
class Structured:
    pass


@dataclass(frozen=True, slots=True)
class Splat:
    alias: str
    prefix: str


@dataclass(frozen=True, slots=True)
class Preset:
    name: str


type ColumnSource = BarePath | Structured | Splat | Preset


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    path: Path
    on_missing: MissingPolicy | None
    default: object | None
    has_default: bool
    source: ColumnSource


def desugar_columns(
    entries: Sequence[object],
    scope_table: AmbientScopeTable,
    *,
    presets: Mapping[str, PresetFn] = _EMPTY_PRESETS,
) -> list[ColumnSpec]:
    """Lower a sequence of column entries to ``ColumnSpec`` instances.

    The file-level missing policy is applied at evaluation time via
    ``CompiledQuery.file_default_policy``; specs only carry their explicit
    per-column ``on_missing`` override (or ``None`` to fall back to the
    file-level value at runtime), so this function does not need it.

    ``presets`` is the bundle in effect for any ``{preset: name}`` entries
    encountered (spec §10.2). Callers that don't use presets can omit it; the
    default is the empty bundle, which causes any preset reference to raise
    ``UnknownPreset``. ``compile_query`` passes ``BUILTIN_PRESETS`` here by
    default.
    """
    specs: list[ColumnSpec] = []
    for entry in entries:
        specs.extend(_desugar_entry(entry, scope_table, presets))
    return specs


def assign_column_names(specs: list[ColumnSpec]) -> list[ColumnSpec]:
    resolved_names: list[str] = []
    implicit_groups: dict[str, list[int]] = defaultdict(list)

    for index, spec in enumerate(specs):
        if spec.name:
            resolved_names.append(spec.name)
            continue
        default_name = _default_column_name(spec.path)
        resolved_names.append(default_name)
        implicit_groups[default_name].append(index)

    for default_name, indices in implicit_groups.items():
        if len(indices) <= 1:
            continue
        for index in indices:
            alias = specs[index].path.segments[0].name
            resolved_names[index] = f"{alias}_{default_name}"

    by_name: dict[str, list[int]] = defaultdict(list)
    for index, name in enumerate(resolved_names):
        by_name[name].append(index)

    for name, indices in by_name.items():
        if len(indices) <= 1:
            continue
        paths = [path_to_string(specs[index].path) for index in indices]
        raise ColumnNameCollision(name, paths)

    return [replace(spec, name=resolved_names[index]) for index, spec in enumerate(specs)]


def validate_column_paths(
    specs: list[ColumnSpec],
    scope_table: AmbientScopeTable,
    *,
    allow_container_terminals: bool,
) -> None:
    for spec in specs:
        path = spec.path
        path_text = path_to_string(path)
        if len(path.segments) == 0:
            raise InvalidPath(path_text, "<root>", object)

        head = path.segments[0]
        if len(head.filters) != 0:
            raise InvalidFilter(path_text, head.name, "filters are not allowed on aliases")

        if path.meta is not None:
            _validate_meta_path(path, path_text, head, scope_table)
            continue

        for segment in path.segments[1:]:
            for filter_expr in segment.filters:
                if isinstance(filter_expr, IterFilter):
                    raise InvalidFilter(
                        path_text,
                        segment.name,
                        "iter filter [*] is not allowed in column paths",
                    )

        if head.name not in scope_table:
            raise UnknownScope(head.name, scope_table.available_aliases())

        current_kind = scope_table[head.name].type_kind
        terminal_kind = current_kind

        if len(path.segments) > 1:
            tail = Path(segments=path.segments[1:])
            if not isinstance(current_kind, DataclassField):
                raise InvalidPath(path_text, tail.segments[0].name, owner_type(current_kind))
            try:
                steps = walk_path(current_kind.dataclass_type, tail)
            except InvalidPath as exc:
                raise InvalidPath(path_text, exc.segment, exc.owner_type) from exc
            except InvalidFilter as exc:
                raise InvalidFilter(path_text, exc.segment, exc.predicate) from exc
            except InvalidFilterValue as exc:
                raise InvalidFilterValue(path_text, exc.predicate, exc.value, exc.target_type) from exc

            if len(steps) > 0:
                terminal_kind = steps[-1].kind_after

        if allow_container_terminals:
            continue
        if not isinstance(terminal_kind, LeafField):
            raise InvalidPath(path_text, path.segments[-1].name, owner_type(terminal_kind))


def _validate_meta_path(path: Path, path_text: str, head: Segment, scope_table: AmbientScopeTable) -> None:
    """Spec §7.1: enforce shape and binding requirements for meta-accessor paths.

    A column with a meta terminal must be exactly ``<alias>.@<name>``: a
    single-segment alias head with no filters, plus a meta accessor whose
    name is in the canonical set, anchored on an iter-bound alias. ``@key``
    additionally requires the alias to iterate a ``dict[K, V]``.
    """
    assert path.meta is not None
    accessor = path.meta.name
    if head.name not in scope_table:
        raise UnknownScope(head.name, scope_table.available_aliases())
    if len(path.segments) != 1:
        raise InvalidMetaAccessor(
            path_text,
            accessor,
            f"meta-accessor must follow an alias directly (e.g. <alias>.@{accessor})",
        )
    scope = scope_table[head.name]
    if scope.iter_source_kind is None:
        raise InvalidMetaAccessor(
            path_text,
            accessor,
            f"alias '{head.name}' is not iter-bound; meta-accessors require an iterative [*] segment",
        )
    if accessor not in _CANONICAL_META_ACCESSORS:
        raise InvalidMetaAccessor(
            path_text,
            accessor,
            f"unknown meta-accessor; expected one of {sorted(_CANONICAL_META_ACCESSORS)}",
        )
    if accessor == "key" and not isinstance(scope.iter_source_kind, DictField):
        raise InvalidMetaAccessor(
            path_text,
            accessor,
            f"@key requires a dict iter scope; '{head.name}' iterates a list",
        )


def _desugar_entry(
    entry: object,
    scope_table: AmbientScopeTable,
    presets: Mapping[str, PresetFn],
) -> list[ColumnSpec]:
    if isinstance(entry, str):
        return [
            ColumnSpec(
                name="",
                path=parse_path(entry),
                on_missing=None,
                default=None,
                has_default=False,
                source=BarePath(),
            )
        ]

    if not isinstance(entry, Mapping):
        raise ParseError("column entry must be a string or mapping", position=None)
    typed_entry = cast(Mapping[object, object], entry)
    mapping_entry: dict[object, object] = dict(typed_entry)

    shape_keys = [key for key in ("path", "splat", "preset") if key in mapping_entry]
    if len(shape_keys) != 1:
        raise ParseError("column mapping must contain exactly one of path/splat/preset", position=None)
    if "path" in mapping_entry:
        return [_structured_column(mapping_entry)]
    if "splat" in mapping_entry:
        return _expand_splat(mapping_entry, scope_table)
    return _expand_preset(mapping_entry, scope_table, presets)


def _structured_column(entry: Mapping[object, object]) -> ColumnSpec:
    raw_path = entry.get("path")
    if not isinstance(raw_path, str):
        raise ParseError("structured column requires string path", position=None)

    name = ""
    if "name" in entry:
        raw_name = entry.get("name")
        if not isinstance(raw_name, str):
            raise ParseError("structured column name must be a string", position=None)
        name = raw_name

    on_missing: MissingPolicy | None = None
    if "on_missing" in entry:
        on_missing = parse_missing_policy(entry.get("on_missing"))

    has_default = "default" in entry
    default = entry.get("default") if has_default else None

    return ColumnSpec(
        name=name,
        path=parse_path(raw_path),
        on_missing=on_missing,
        default=default,
        has_default=has_default,
        source=Structured(),
    )


def _expand_splat(entry: Mapping[object, object], scope_table: AmbientScopeTable) -> list[ColumnSpec]:
    alias = entry.get("splat")
    if not isinstance(alias, str):
        raise ParseError("splat alias must be a string", position=None)
    if alias not in scope_table:
        raise UnknownScope(alias, scope_table.available_aliases())

    scope = scope_table[alias]
    if not isinstance(scope.type_kind, DataclassField):
        raise ParseError(f'splat alias "{alias}" must refer to a dataclass scope', position=None)

    if "include" in entry and "exclude" in entry:
        raise ParseError("splat include/exclude are mutually exclusive", position=None)

    include = _read_name_list(entry, "include")
    exclude = _read_name_list(entry, "exclude")
    prefix = _read_prefix(entry)

    on_missing: MissingPolicy | None = None
    if "on_missing" in entry:
        on_missing = parse_missing_policy(entry.get("on_missing"))

    leaves = leaf_fields(scope.type_kind.dataclass_type)
    available = [leaf.name for leaf in leaves]

    if include is not None:
        _validate_splat_fields(alias, include, available)
        allowed = set(include)
        leaves = [leaf for leaf in leaves if leaf.name in allowed]
    elif exclude is not None:
        _validate_splat_fields(alias, exclude, available)
        denied = set(exclude)
        leaves = [leaf for leaf in leaves if leaf.name not in denied]

    specs: list[ColumnSpec] = []
    for leaf in leaves:
        specs.append(
            ColumnSpec(
                name=f"{prefix}{leaf.name}",
                path=parse_path(f"{alias}.{leaf.name}"),
                on_missing=on_missing,
                default=None,
                has_default=False,
                source=Splat(alias=alias, prefix=prefix),
            )
        )
    return specs


def _expand_preset(
    entry: Mapping[object, object],
    scope_table: AmbientScopeTable,
    presets: Mapping[str, PresetFn],
) -> list[ColumnSpec]:
    name = entry.get("preset")
    if not isinstance(name, str):
        raise ParseError("preset name must be a string", position=None)

    fn = presets.get(name)
    if fn is None:
        raise UnknownPreset(name)
    args: dict[str, object] = {
        str(key): value for key, value in entry.items() if isinstance(key, str) and key != "preset"
    }
    expanded = fn(scope_table, args)
    # Recursive expansion under the same bundle (spec §10): a preset's output
    # may itself contain preset/splat/structured/bare-path entries.
    specs = desugar_columns(expanded, scope_table, presets=presets)
    # Stamp this preset's name only on specs that originated from raw
    # ``BarePath`` / ``Structured`` entries within the preset's output.
    # Specs already attributed to an inner preset (or splat) keep their
    # original source so nested attribution is non-lossy.
    return [
        replace(spec, source=Preset(name=name)) if isinstance(spec.source, (BarePath, Structured)) else spec
        for spec in specs
    ]


def _read_name_list(entry: Mapping[object, object], key: str) -> list[str] | None:
    if key not in entry:
        return None
    value = entry.get(key)
    if not isinstance(value, list):
        raise ParseError(f"splat {key} must be a list of strings", position=None)
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise ParseError(f"splat {key} must be a list of strings", position=None)
    # The ``all(isinstance(...))`` check above narrows every element to ``str``
    # at runtime; the cast here just communicates that to the type checker
    # without an unreachable per-element re-filter.
    return cast(list[str], items)


def _read_prefix(entry: Mapping[object, object]) -> str:
    value = entry.get("prefix", "")
    if not isinstance(value, str):
        raise ParseError("splat prefix must be a string", position=None)
    return value


def _validate_splat_fields(alias: str, requested: list[str], available: list[str]) -> None:
    available_set = set(available)
    for field in requested:
        if field not in available_set:
            raise SplatUnknownField(alias, field, available)


def _default_column_name(path: Path) -> str:
    if path.meta is not None:
        return path.meta.name
    return path.segments[-1].name
