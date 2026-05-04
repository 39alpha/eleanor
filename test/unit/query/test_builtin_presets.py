"""Tests for the canonical EQL preset bundle and ``compile_query(presets=...)``.

The canonical bundle is defined in ``eleanor.query.presets`` and the three
canonical presets (``run_metadata``, ``es_scalars``, ``aqueous_species_table``)
desugar against Eleanor's real data-model dataclasses (``Order``, ``ESPoint``,
``AqueousSpecies``). These tests exercise both the per-preset contract (args,
required aliases, error shapes) and the bundle wiring on ``compile_query``.
"""

import eleanor.query.presets as presets_module
from eleanor.equilibrium_space import AqueousSpecies
from eleanor.order import Order
from eleanor.query import (
    BUILTIN_PRESETS,
    ParseError,
    PresetScopeMissing,
    SplatUnknownField,
    UnknownPreset,
    compile_query,
)
from eleanor.query.columns import Preset
from eleanor.query.reflection import leaf_fields
from eleanor.query.scope import AmbientScopeTable

from ..common import TestCase


def _expected_es_scalar_names() -> list[str]:
    """Reflect the ESPoint scalar field names directly to keep tests data-driven."""
    from eleanor.equilibrium_space import Point as ESPoint

    return [leaf.name for leaf in leaf_fields(ESPoint)]


class TestBuiltinPresetsRegistry(TestCase):
    """
    Tests of ``BUILTIN_PRESETS`` shape and immutability.
    """

    def test_builtin_presets_lists_canonical_three_names(self):
        """
        Ensure the canonical bundle contains exactly the spec §17.5 names.
        """
        self.assertEqual(
            sorted(BUILTIN_PRESETS),
            ["aqueous_species_table", "es_scalars", "run_metadata"],
        )

    def test_builtin_presets_is_immutable_proxy(self):
        """
        Ensure callers can't mutate the canonical bundle in place.
        """
        with self.assertRaises(TypeError):
            BUILTIN_PRESETS["new"] = lambda _scope, _args: []  # pyright: ignore[reportIndexIssue]


class TestRunMetadataPreset(TestCase):
    """
    Tests for the canonical ``run_metadata`` preset.
    """

    def test_run_metadata_emits_fixed_columns(self):
        """
        Ensure ``run_metadata`` emits the seven leaf columns enumerated in spec
        §10.3, with column names matching path terminals.
        """
        compiled = compile_query(
            Order,
            {"row_scope": "order", "columns": [{"preset": "run_metadata"}]},
        )
        self.assertEqual(
            [c.spec.name for c in compiled.compiled_columns],
            ["id", "tag", "name", "creator", "notes", "eleanor_version", "create_date"],
        )

    def test_run_metadata_columns_attributed_to_preset(self):
        """
        Ensure the preset stamps its own name on every emitted column's source.
        """
        compiled = compile_query(
            Order,
            {"row_scope": "order", "columns": [{"preset": "run_metadata"}]},
        )
        for column in compiled.compiled_columns:
            self.assertEqual(column.spec.source, Preset(name="run_metadata"))

    def test_run_metadata_rejects_arguments(self):
        """
        Ensure ``run_metadata`` rejects any argument; it is parameter-free.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "order",
                    "columns": [{"preset": "run_metadata", "extra": 1}],
                },
            )

    def test_run_metadata_missing_order_alias_raises_preset_scope_missing(self):
        """
        Ensure the defensive ``order`` alias check fires when called against
        a malformed scope table that omits the root binding.
        """
        with self.assertRaises(PresetScopeMissing) as cm:
            presets_module._preset_run_metadata(AmbientScopeTable(), {})
        self.assertEqual(cm.exception.preset, "run_metadata")
        self.assertEqual(cm.exception.missing_alias, "order")


class TestEsScalarsPreset(TestCase):
    """
    Tests for the canonical ``es_scalars`` preset.
    """

    def test_es_scalars_default_emits_all_es_leaves(self):
        """
        Ensure ``es_scalars`` with no arguments emits one column per ``ESPoint``
        leaf field.
        """
        compiled = compile_query(
            Order,
            {"row_scope": "es", "columns": [{"preset": "es_scalars"}]},
        )
        self.assertEqual(
            [c.spec.name for c in compiled.compiled_columns],
            _expected_es_scalar_names(),
        )

    def test_es_scalars_exclude_filters_named_fields(self):
        """
        Ensure ``exclude`` removes named scalars from the output.
        """
        compiled = compile_query(
            Order,
            {
                "row_scope": "es",
                "columns": [
                    {"preset": "es_scalars", "exclude": ["charge_discrepancy", "sigma"]},
                ],
            },
        )
        names = {c.spec.name for c in compiled.compiled_columns}
        self.assertNotIn("charge_discrepancy", names)
        self.assertNotIn("sigma", names)
        self.assertIn("pH", names)

    def test_es_scalars_include_restricts_to_named_fields(self):
        """
        Ensure ``include`` restricts the output to the named scalars.
        """
        compiled = compile_query(
            Order,
            {
                "row_scope": "es",
                "columns": [
                    {"preset": "es_scalars", "include": ["pH", "temperature"]},
                ],
            },
        )
        self.assertEqual(
            [c.spec.name for c in compiled.compiled_columns],
            ["temperature", "pH"],
        )

    def test_es_scalars_include_and_exclude_are_mutually_exclusive(self):
        """
        Ensure passing both ``include`` and ``exclude`` raises ``ParseError``.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {"preset": "es_scalars", "include": ["pH"], "exclude": ["sigma"]},
                    ],
                },
            )

    def test_es_scalars_unknown_args_raise_parse_error(self):
        """
        Ensure unknown extra arguments are rejected at compile time.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [{"preset": "es_scalars", "garbage": 1}],
                },
            )

    def test_es_scalars_unknown_field_raises_splat_unknown_field(self):
        """
        Ensure naming a non-existent ESPoint scalar in ``include`` or
        ``exclude`` raises ``SplatUnknownField`` against the ``es`` alias.
        """
        with self.assertRaises(SplatUnknownField) as include_cm:
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [{"preset": "es_scalars", "include": ["not_a_field"]}],
                },
            )
        self.assertEqual(include_cm.exception.alias, "es")
        self.assertEqual(include_cm.exception.field, "not_a_field")

        with self.assertRaises(SplatUnknownField):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [{"preset": "es_scalars", "exclude": ["not_a_field"]}],
                },
            )

    def test_es_scalars_name_list_must_be_strings(self):
        """
        Ensure non-list and non-string-list arguments raise ``ParseError``.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [{"preset": "es_scalars", "include": "pH"}],
                },
            )
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [{"preset": "es_scalars", "exclude": ["pH", 7]}],
                },
            )

    def test_es_scalars_missing_es_alias_raises_preset_scope_missing(self):
        """
        Ensure the preset rejects a scope table that lacks ``es``.
        """
        with self.assertRaises(PresetScopeMissing) as cm:
            presets_module._preset_es_scalars(AmbientScopeTable(), {})
        self.assertEqual(cm.exception.preset, "es_scalars")
        self.assertEqual(cm.exception.missing_alias, "es")

    def test_es_scalars_non_dataclass_es_alias_raises_parse_error(self):
        """
        Ensure the defensive non-dataclass guard fires when ``es`` is bound
        to a non-dataclass kind. Surfaces a clean ``ParseError`` rather than
        an opaque attribute error.
        """
        from eleanor.query.path import Path
        from eleanor.query.reflection import LeafField

        table = AmbientScopeTable()
        table.add(
            "es",
            Path(segments=tuple()),
            LeafField(name="es", declared_type=int, optional=False),
            terminal=True,
        )
        with self.assertRaises(ParseError):
            presets_module._preset_es_scalars(table, {})


class TestAqueousSpeciesTablePreset(TestCase):
    """
    Tests for the canonical ``aqueous_species_table`` preset.
    """

    def _aqs_field_names(self) -> list[str]:
        return [leaf.name for leaf in leaf_fields(AqueousSpecies)]

    def test_aqueous_species_table_emits_cross_product(self):
        """
        Ensure the preset emits one column per ``(name, field)`` pair, named
        ``<field>_<name>`` and pathed via ``es.aqueous_species[name=<name>]``.
        """
        compiled = compile_query(
            Order,
            {
                "row_scope": "es",
                "columns": [
                    {
                        "preset": "aqueous_species_table",
                        "names": ["Ca+2", "Cl-"],
                        "fields": ["log_molality", "log_activity"],
                    },
                ],
            },
        )
        self.assertEqual(
            [c.spec.name for c in compiled.compiled_columns],
            [
                "log_molality_Ca+2",
                "log_activity_Ca+2",
                "log_molality_Cl-",
                "log_activity_Cl-",
            ],
        )

    def test_aqueous_species_table_quotes_names_with_unsafe_chars(self):
        """
        Ensure species names that contain characters illegal under the
        ``Unquoted`` production (whitespace, ``=``, ``,``, ``]``, ``"``) are
        emitted as quoted-string predicate values so the generated path still
        parses. Column names retain the raw species name verbatim.
        """
        compiled = compile_query(
            Order,
            {
                "row_scope": "es",
                "columns": [
                    {
                        "preset": "aqueous_species_table",
                        "names": ["weird name", 'has"quote'],
                        "fields": ["log_molality"],
                    },
                ],
            },
        )
        self.assertEqual(
            [c.spec.name for c in compiled.compiled_columns],
            ["log_molality_weird name", 'log_molality_has"quote'],
        )
        # Each compiled column's path predicate should preserve the raw name
        # via the quoted form, so the predicate's coerced value matches the
        # input name byte-for-byte.
        for column, expected in zip(compiled.compiled_columns, ["weird name", 'has"quote'], strict=True):
            terminal_filters = column.compiled_path.segments[-2].filters
            assert len(terminal_filters) == 1
            match_filter = terminal_filters[0]
            from eleanor.query.compiler import CompiledMatchFilter

            assert isinstance(match_filter, CompiledMatchFilter)
            self.assertEqual(match_filter.predicates[0].coerced_value, expected)
            self.assertTrue(match_filter.predicates[0].value_quoted)

    def test_aqueous_species_table_requires_both_args(self):
        """
        Ensure missing ``names`` or ``fields`` raises ``ParseError``.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {"preset": "aqueous_species_table", "fields": ["log_molality"]},
                    ],
                },
            )
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [{"preset": "aqueous_species_table", "names": ["Ca+2"]}],
                },
            )

    def test_aqueous_species_table_rejects_empty_lists(self):
        """
        Ensure empty ``names`` or ``fields`` raise ``ParseError``.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {"preset": "aqueous_species_table", "names": [], "fields": ["log_molality"]},
                    ],
                },
            )
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {"preset": "aqueous_species_table", "names": ["Ca+2"], "fields": []},
                    ],
                },
            )

    def test_aqueous_species_table_rejects_unknown_field(self):
        """
        Ensure ``fields`` entries are validated against ``AqueousSpecies``'s
        leaf fields.
        """
        with self.assertRaises(ParseError) as cm:
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {
                            "preset": "aqueous_species_table",
                            "names": ["Ca+2"],
                            "fields": ["not_a_field"],
                        },
                    ],
                },
            )
        self.assertIn("not_a_field", str(cm.exception))
        # All AqueousSpecies leaves should appear in the diagnostic.
        for leaf in self._aqs_field_names():
            self.assertIn(leaf, str(cm.exception))

    def test_aqueous_species_table_rejects_unknown_extra_args(self):
        """
        Ensure unknown extra arguments are rejected at compile time.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {
                            "preset": "aqueous_species_table",
                            "names": ["Ca+2"],
                            "fields": ["log_molality"],
                            "garbage": 1,
                        },
                    ],
                },
            )

    def test_aqueous_species_table_rejects_non_string_names_and_fields(self):
        """
        Ensure non-list / non-string-list arguments raise ``ParseError``.
        """
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {
                            "preset": "aqueous_species_table",
                            "names": "Ca+2",
                            "fields": ["log_molality"],
                        },
                    ],
                },
            )
        with self.assertRaises(ParseError):
            compile_query(
                Order,
                {
                    "row_scope": "es",
                    "columns": [
                        {
                            "preset": "aqueous_species_table",
                            "names": ["Ca+2"],
                            "fields": ["log_molality", 7],
                        },
                    ],
                },
            )

    def test_aqueous_species_table_missing_es_alias_raises_preset_scope_missing(self):
        """
        Ensure the preset rejects a scope table that lacks ``es``.
        """
        with self.assertRaises(PresetScopeMissing) as cm:
            presets_module._preset_aqueous_species_table(AmbientScopeTable(), {})
        self.assertEqual(cm.exception.preset, "aqueous_species_table")
        self.assertEqual(cm.exception.missing_alias, "es")


class TestCompileQueryPresetsParameter(TestCase):
    """
    Tests for the ``compile_query(presets=...)`` parameter (spec §10.2).
    """

    def test_default_uses_canonical_bundle(self):
        """
        Ensure ``presets=None`` (the default) resolves canonical names.
        """
        compiled = compile_query(
            Order,
            {"row_scope": "order", "columns": [{"preset": "run_metadata"}]},
        )
        self.assertEqual(len(compiled.compiled_columns), 7)

    def test_explicit_canonical_bundle_works(self):
        """
        Ensure passing ``BUILTIN_PRESETS`` explicitly behaves identically to
        the default.
        """
        compiled = compile_query(
            Order,
            {"row_scope": "order", "columns": [{"preset": "run_metadata"}]},
            presets=BUILTIN_PRESETS,
        )
        self.assertEqual(len(compiled.compiled_columns), 7)

    def test_empty_bundle_disables_canonical_presets(self):
        """
        Ensure ``presets={}`` disables presets entirely so canonical names
        raise ``UnknownPreset``.
        """
        with self.assertRaises(UnknownPreset) as cm:
            compile_query(
                Order,
                {"row_scope": "order", "columns": [{"preset": "run_metadata"}]},
                presets={},
            )
        self.assertEqual(cm.exception.name, "run_metadata")

    def test_custom_bundle_replaces_canonical(self):
        """
        Ensure a caller-supplied bundle is the only one in effect; canonical
        names are unavailable when not present in the supplied mapping.
        """

        def custom_preset(scope_table, args):
            _ = scope_table
            _ = args
            return [{"path": "order.id", "name": "custom_id"}]

        bundle = {"custom": custom_preset}
        compiled = compile_query(
            Order,
            {"row_scope": "order", "columns": [{"preset": "custom"}]},
            presets=bundle,
        )
        self.assertEqual([c.spec.name for c in compiled.compiled_columns], ["custom_id"])

        # Canonical preset name is unavailable under the custom bundle.
        with self.assertRaises(UnknownPreset):
            compile_query(
                Order,
                {"row_scope": "order", "columns": [{"preset": "run_metadata"}]},
                presets=bundle,
            )

    def test_custom_bundle_supports_recursive_preset_expansion(self):
        """
        Ensure a custom preset that emits another preset entry resolves the
        inner reference under the same bundle (spec §10).
        """

        def outer(scope_table, args):
            _ = scope_table
            _ = args
            return [{"preset": "inner"}]

        def inner(scope_table, args):
            _ = scope_table
            _ = args
            return [{"path": "order.id", "name": "inner_id"}]

        compiled = compile_query(
            Order,
            {"row_scope": "order", "columns": [{"preset": "outer"}]},
            presets={"outer": outer, "inner": inner},
        )
        self.assertEqual([c.spec.name for c in compiled.compiled_columns], ["inner_id"])
