"""Canonical EQL preset bundle for Eleanor's data model.

Per spec §10, presets desugar a single ``{preset: name, ...}`` directive into
a list of column entries. This module supplies the canonical bundle that
``compile_query`` defaults to (``BUILTIN_PRESETS``) and the ``PresetFn`` type
callers should use when supplying a custom bundle via ``compile_query(...,
presets=...)``.

There is no global registry. Bundles are plain ``Mapping[str, PresetFn]``
values; the canonical bundle is a ``MappingProxyType`` view to keep callers
from accidentally mutating it.
"""

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import cast

from eleanor.equilibrium_space import AqueousSpecies
from eleanor.query.errors import ParseError, PresetScopeMissing, SplatUnknownField
from eleanor.query.path import quote_predicate_value
from eleanor.query.reflection import DataclassField, leaf_fields
from eleanor.query.scope import AmbientScopeTable

# Preset functions take the ambient scope table and the directive's argument
# mapping; they return a sequence of column entries that ``desugar_columns``
# can re-process (strings or mapping records).
type PresetFn = Callable[[AmbientScopeTable, Mapping[str, object]], Sequence[object]]


def _preset_run_metadata(scope_table: AmbientScopeTable, args: Mapping[str, object]) -> Sequence[object]:
    """Canonical preset: emit fixed leaf columns describing the source ``Order``.

    The column list is closed by spec §10.3 and is intentionally hard-coded
    here. This makes it a fourth landing site for ``Order`` schema changes
    (alongside the postgres ``ColumnDef``, the dataclass annotation, and
    ``docs/database.qmd`` -- see ``AGENTS.md``): adding or removing a
    metadata leaf on ``Order`` requires updating this list and spec §10.3
    in the same change.
    """
    if args:
        raise ParseError(
            f"preset 'run_metadata' takes no arguments (got: {sorted(args)})",
            position=None,
        )
    if "order" not in scope_table:
        # The spec guarantees ``order`` is always bound (§7); guard defensively
        # so a malformed scope table surfaces as ``PresetScopeMissing`` rather
        # than as an opaque ``UnknownScope`` later in column validation.
        raise PresetScopeMissing("run_metadata", "order")
    return [
        "order.id",
        "order.tags",
        "order.name",
        "order.creator",
        "order.notes",
        "order.eleanor_version",
        "order.create_date",
    ]


def _preset_es_scalars(scope_table: AmbientScopeTable, args: Mapping[str, object]) -> Sequence[object]:
    """Canonical preset: emit one column per scalar leaf of the ``es`` scope."""
    if "es" not in scope_table:
        raise PresetScopeMissing("es_scalars", "es")

    extra = sorted(set(args) - {"include", "exclude"})
    if extra:
        raise ParseError(f"preset 'es_scalars' unknown args: {extra}", position=None)
    if "include" in args and "exclude" in args:
        raise ParseError(
            "preset 'es_scalars' include/exclude are mutually exclusive",
            position=None,
        )

    include = _coerce_name_list(args["include"], "es_scalars", "include") if "include" in args else None
    exclude = _coerce_name_list(args["exclude"], "es_scalars", "exclude") if "exclude" in args else None

    scope = scope_table["es"]
    if not isinstance(scope.type_kind, DataclassField):
        # Defensive: ``es`` is the singularized alias of ``es_points``, which
        # row_scope resolution only binds when it points at an ``ESPoint``
        # dataclass node. Surface a clean error if a caller has wired up a
        # non-canonical scope table that breaks this assumption.
        raise ParseError(
            "preset 'es_scalars' requires 'es' to refer to a dataclass scope",
            position=None,
        )

    leaves = leaf_fields(scope.type_kind.dataclass_type)
    available = [leaf.name for leaf in leaves]

    if include is not None:
        for name in include:
            if name not in available:
                raise SplatUnknownField("es", name, available)
        allowed = set(include)
        leaves = [leaf for leaf in leaves if leaf.name in allowed]
    elif exclude is not None:
        for name in exclude:
            if name not in available:
                raise SplatUnknownField("es", name, available)
        denied = set(exclude)
        leaves = [leaf for leaf in leaves if leaf.name not in denied]

    return [f"es.{leaf.name}" for leaf in leaves]


def _preset_aqueous_species_table(scope_table: AmbientScopeTable, args: Mapping[str, object]) -> Sequence[object]:
    """Canonical preset: cross-product columns over ``names`` × ``fields``."""
    if "es" not in scope_table:
        raise PresetScopeMissing("aqueous_species_table", "es")

    extra = sorted(set(args) - {"names", "fields"})
    if extra:
        raise ParseError(f"preset 'aqueous_species_table' unknown args: {extra}", position=None)
    if "names" not in args:
        raise ParseError("preset 'aqueous_species_table' requires 'names'", position=None)
    if "fields" not in args:
        raise ParseError("preset 'aqueous_species_table' requires 'fields'", position=None)

    names = _coerce_name_list(args["names"], "aqueous_species_table", "names")
    fields = _coerce_name_list(args["fields"], "aqueous_species_table", "fields")
    if not names:
        raise ParseError(
            "preset 'aqueous_species_table' 'names' must be a non-empty list",
            position=None,
        )
    if not fields:
        raise ParseError(
            "preset 'aqueous_species_table' 'fields' must be a non-empty list",
            position=None,
        )

    aqs_leaves = [leaf.name for leaf in leaf_fields(AqueousSpecies)]
    available_text = ", ".join(aqs_leaves)
    for field in fields:
        if field not in aqs_leaves:
            raise ParseError(
                f"preset 'aqueous_species_table': field '{field}' is not a scalar field of "
                + f"AqueousSpecies (available: {available_text})",
                position=None,
            )

    specs: list[object] = []
    for name in names:
        # Names like ``Ca+2`` and ``HCO3-`` parse as bare unquoted predicate
        # values, but the spec puts no constraint on the ``names`` list, so a
        # name containing whitespace, ``=``, ``,``, ``]``, or ``"`` would
        # otherwise produce a malformed path that ``parse_path`` rejects with
        # an unhelpful ``ParseError``. ``quote_predicate_value`` keeps the
        # bare form when it's safe and quotes otherwise.
        quoted_name = quote_predicate_value(name)
        for field in fields:
            specs.append(
                {
                    "path": f"es.aqueous_species[name={quoted_name}].{field}",
                    "name": f"{field}_{name}",
                },
            )
    return specs


def _coerce_name_list(value: object, preset: str, key: str) -> list[str]:
    """Validate ``value`` as ``list[str]`` for preset arguments."""
    if not isinstance(value, list):
        raise ParseError(f"preset '{preset}' '{key}' must be a list of strings", position=None)
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise ParseError(f"preset '{preset}' '{key}' must be a list of strings", position=None)
    # Runtime ``all(isinstance(...))`` narrows every element to ``str``; the
    # cast communicates that to the type checker without an unreachable
    # per-element re-filter.
    return cast(list[str], items)


BUILTIN_PRESETS: Mapping[str, PresetFn] = MappingProxyType(
    {
        "run_metadata": _preset_run_metadata,
        "es_scalars": _preset_es_scalars,
        "aqueous_species_table": _preset_aqueous_species_table,
    },
)
"""Canonical preset bundle (spec §10.3).

Pass ``presets=BUILTIN_PRESETS`` to ``compile_query`` (or omit the argument)
to use the canonical set. Pass ``presets={}`` to disable presets entirely;
pass a custom ``Mapping[str, PresetFn]`` to use an alternative bundle.
"""
