from collections.abc import Iterable, Mapping
from types import MappingProxyType

SHORT_FORMS: Mapping[str, str] = MappingProxyType(
    {
        "vs_point": "vs",
        "es_point": "es",
    },
)
SHORT_FORM_INVERSE: Mapping[str, str] = MappingProxyType({short: default for default, short in SHORT_FORMS.items()})

# Closed table of irregular plural → singular suffix mappings consulted before
# the algorithmic rules in `singularize`. See spec §5.4. Suffix matching is
# case-insensitive; the surrounding prefix retains its original case while the
# matched suffix is replaced with the corresponding singular suffix from the
# table. Modify only alongside the spec.
_IRREGULAR_FORMS: Mapping[str, str] = MappingProxyType(
    {
        "species": "species",
        "axes": "axis",
    },
)

_KNOWN_SEGMENT_NAMES: tuple[str, ...] = (
    "vs_points",
    "es_points",
    "aqueous_species",
    "pure_solids",
    "solid_solutions",
    "end_members",
    "elements",
    "species",
    "reactants",
    "gases",
    "redox_reactions",
    "custom_properties",
)


def singularize(name: str) -> str:
    lower = name.lower()
    for plural_suffix, singular_suffix in _IRREGULAR_FORMS.items():
        if lower.endswith(plural_suffix):
            return f"{name[: -len(plural_suffix)]}{singular_suffix}"
    if lower.endswith("ies"):
        return f"{name[:-3]}y"
    if lower.endswith(("ses", "xes", "zes", "ches", "shes")):
        return name[:-2]
    if lower.endswith("men"):
        return f"{name[:-3]}man"
    if lower.endswith("s") and not lower.endswith("ss"):
        return name[:-1]
    return name


def aliases_for(name: str) -> tuple[str] | tuple[str, str]:
    """Return the default alias for ``name``, plus the short form if registered.

    The result is always non-empty: a single-element tuple when no short form
    is defined, or a two-element ``(default, short)`` tuple when one is. The
    explicit ``tuple[str] | tuple[str, str]`` return type lets callers index
    ``[0]`` without a typing escape hatch.
    """
    default_alias = singularize(name)
    short_alias = SHORT_FORMS.get(default_alias)
    if short_alias is None:
        return (default_alias,)
    return (default_alias, short_alias)


def _validate_short_forms_static(
    short_forms: Mapping[str, str],
    short_form_inverse: Mapping[str, str],
    known_names: Iterable[str],
) -> None:
    """Verify ``short_forms`` is internally consistent against ``known_names``.

    Raises ``AssertionError`` if (a) two short-form keys map to the same
    short-form value (so ``short_form_inverse`` would have collapsed them) or
    (b) any short-form value collides with a default alias derived from
    ``known_names``. This is a startup sanity check on the curated tables;
    the live-reflection counterpart is
    ``scope.validate_short_forms_for_root``.
    """
    default_aliases = {singularize(name) for name in known_names}
    if len(short_forms) != len(short_form_inverse):
        msg = "short-form aliases must be unique"
        raise AssertionError(msg)

    collisions = sorted(short for short in short_form_inverse if short in default_aliases)
    if collisions:
        joined = ", ".join(collisions)
        msg = f"short-form aliases collide with default aliases: {joined}"
        raise AssertionError(msg)


def validate_short_forms() -> None:
    """Verify the curated module-level short-form tables at import time."""
    _validate_short_forms_static(SHORT_FORMS, SHORT_FORM_INVERSE, _KNOWN_SEGMENT_NAMES)


validate_short_forms()
