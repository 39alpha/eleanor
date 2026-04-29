from eleanor.query.columns import (
    BarePath,
    Preset,
    Splat,
    Structured,
    assign_column_names,
    desugar_columns,
    validate_column_paths,
)
from eleanor.query.errors import (
    ColumnNameCollision,
    InvalidFilter,
    InvalidMetaAccessor,
    InvalidPath,
    ParseError,
    SplatUnknownField,
    UnknownPreset,
    UnknownScope,
)
from eleanor.query.scope import resolve_row_scope

from ..common import TestCase
from .models import Sample


class TestColumns(TestCase):
    """
    Tests for column spec desugaring, naming, and validation.
    """

    def _point_scope(self):
        _, table = resolve_row_scope(Sample, "points[*]")
        return table

    def test_desugar_columns_supports_string_and_structured_entries(self):
        """
        Ensure bare path and structured mapping entries produce expected source kinds.
        """
        table = self._point_scope()
        specs = desugar_columns(
            [
                "point.index",
                {"path": "point.chemistry.ph", "name": "ph", "on_missing": "null", "default": 0.0},
            ],
            table,
        )
        self.assertIsInstance(specs[0].source, BarePath)
        self.assertIsInstance(specs[1].source, Structured)
        self.assertEqual(specs[1].name, "ph")
        self.assertEqual(specs[1].on_missing, "null")
        self.assertEqual(specs[1].default, 0.0)

    def test_desugar_columns_rejects_invalid_shape(self):
        """
        Ensure column mappings must contain exactly one shape discriminator.
        """
        table = self._point_scope()
        with self.assertRaises(ParseError):
            desugar_columns([{"name": "x"}], table)
        with self.assertRaises(ParseError):
            desugar_columns([{"path": "point.index", "splat": "point"}], table)

    def test_desugar_columns_splat_and_preset_expansions(self):
        """
        Ensure splat and preset entries expand into generated column specs with source metadata.
        """
        table = self._point_scope()

        def basic_preset(scope_table, args):
            _ = scope_table
            _ = args
            return [{"path": "point.index", "name": "point_idx"}]

        specs = desugar_columns(
            [
                {"splat": "point", "include": ["index"], "prefix": "pt_"},
                {"preset": "basic"},
            ],
            table,
            presets={"basic": basic_preset},
        )

        self.assertTrue(any(isinstance(spec.source, Splat) for spec in specs))
        self.assertTrue(any(isinstance(spec.source, Preset) for spec in specs))
        self.assertTrue(any(spec.name == "pt_index" for spec in specs))
        self.assertTrue(any(spec.name == "point_idx" for spec in specs))

    def test_desugar_columns_unknown_preset_raises(self):
        """
        Ensure a preset directive whose name isn't in the bundle in effect
        raises ``UnknownPreset``. Default bundle for ``desugar_columns`` is
        empty, so any preset name resolves as unknown.
        """
        table = self._point_scope()
        with self.assertRaises(UnknownPreset):
            desugar_columns([{"preset": "missing"}], table)

    def test_nested_preset_preserves_inner_source_attribution(self):
        """
        Ensure a preset that emits another preset entry (or a splat) leaves
        the inner expansion's source intact instead of overwriting it with
        the outer preset's name. Bare-path / structured entries inside the
        outer preset still get stamped with the outer preset's name.
        """
        table = self._point_scope()

        def inner_preset(scope_table, args):
            _ = scope_table
            _ = args
            return [{"path": "point.index", "name": "inner_idx"}]

        def outer_preset(scope_table, args):
            _ = scope_table
            _ = args
            return [
                {"preset": "inner"},
                {"splat": "point", "include": ["index"], "prefix": "outer_"},
                {"path": "point.index", "name": "outer_direct"},
            ]

        bundle = {"inner": inner_preset, "outer": outer_preset}
        specs = desugar_columns([{"preset": "outer"}], table, presets=bundle)
        sources_by_name = {spec.name: spec.source for spec in specs}
        self.assertEqual(sources_by_name["inner_idx"], Preset(name="inner"))
        self.assertEqual(sources_by_name["outer_index"], Splat(alias="point", prefix="outer_"))
        self.assertEqual(sources_by_name["outer_direct"], Preset(name="outer"))

    def test_desugar_columns_splat_rejects_unknown_field(self):
        """
        Ensure splat include/exclude lists reject unknown fields.
        """
        table = self._point_scope()
        with self.assertRaises(SplatUnknownField):
            desugar_columns([{"splat": "point", "include": ["missing"]}], table)

    def test_assign_column_names_disambiguates_implicit_duplicates(self):
        """
        Ensure implicit duplicate terminal names get alias-prefixed disambiguation.
        """
        table = self._point_scope()
        specs = desugar_columns(["point.chemistry.ph", "self.chemistry.ph"], table)
        named = assign_column_names(specs)
        self.assertEqual({spec.name for spec in named}, {"point_ph", "self_ph"})

    def test_assign_column_names_rejects_explicit_name_collisions(self):
        """
        Ensure explicit duplicate names across columns raise ColumnNameCollision.
        """
        table = self._point_scope()
        specs = desugar_columns(
            [
                {"path": "point.index", "name": "dup"},
                {"path": "self.index", "name": "dup"},
            ],
            table,
        )
        with self.assertRaises(ColumnNameCollision):
            assign_column_names(specs)

    def test_validate_column_paths_checks_alias_filters_and_terminal_kind(self):
        """
        Ensure validation rejects unknown aliases, alias filters, and container terminals by default.
        """
        table = self._point_scope()
        with self.assertRaises(UnknownScope):
            validate_column_paths(
                desugar_columns(["ghost.index"], table), table, allow_container_terminals=False
            )
        with self.assertRaises(InvalidFilter):
            validate_column_paths(
                desugar_columns(["point[index=1].index"], table),
                table,
                allow_container_terminals=False,
            )
        with self.assertRaises(InvalidPath):
            validate_column_paths(
                desugar_columns(["point.minerals"], table), table, allow_container_terminals=False
            )

    def test_validate_column_paths_can_allow_container_terminals(self):
        """
        Ensure container terminal paths are accepted when explicitly enabled.
        """
        table = self._point_scope()
        specs = desugar_columns(["point.minerals"], table)
        validate_column_paths(specs, table, allow_container_terminals=True)

    def test_validate_column_paths_rejects_iter_filters_in_columns(self):
        """
        Ensure iter filters [*] are rejected anywhere in column paths (spec §8).
        """
        table = self._point_scope()
        with self.assertRaises(InvalidFilter):
            validate_column_paths(
                desugar_columns(["point.minerals[*]"], table),
                table,
                allow_container_terminals=True,
            )
        with self.assertRaises(InvalidFilter):
            validate_column_paths(
                desugar_columns(["point.minerals[*].name"], table),
                table,
                allow_container_terminals=False,
            )

    def test_validate_column_paths_accepts_index_meta_on_iter_alias(self):
        """
        Ensure ``<iter-alias>.@index`` validates cleanly against an iter-bound
        alias produced by a list row_scope (spec §7.1).
        """
        table = self._point_scope()
        specs = desugar_columns(["point.@index"], table)
        validate_column_paths(specs, table, allow_container_terminals=False)

    def test_validate_column_paths_accepts_key_meta_on_dict_iter_alias(self):
        """
        Ensure ``<dict-iter-alias>.@key`` and ``.@index`` validate cleanly
        against a dict-iter row_scope.
        """
        _, table = resolve_row_scope(Sample, "point_map[*]")
        specs = desugar_columns(["point_map.@index", "point_map.@key"], table)
        validate_column_paths(specs, table, allow_container_terminals=False)

    def test_validate_column_paths_rejects_meta_on_non_iter_alias(self):
        """
        Ensure meta-accessors anchored on a non-iter-bound alias (here
        ``order`` from a list-iter row_scope) raise ``InvalidMetaAccessor``.
        """
        table = self._point_scope()
        with self.assertRaises(InvalidMetaAccessor) as cm:
            validate_column_paths(
                desugar_columns(["order.@index"], table),
                table,
                allow_container_terminals=False,
            )
        self.assertEqual(cm.exception.accessor, "index")
        self.assertIn("order", cm.exception.reason)

    def test_validate_column_paths_rejects_unknown_meta_name(self):
        """
        Ensure unknown ``@<name>`` accessors raise ``InvalidMetaAccessor``.
        """
        table = self._point_scope()
        with self.assertRaises(InvalidMetaAccessor) as cm:
            validate_column_paths(
                desugar_columns(["point.@bogus"], table),
                table,
                allow_container_terminals=False,
            )
        self.assertEqual(cm.exception.accessor, "bogus")
        self.assertIn("unknown meta-accessor", cm.exception.reason)

    def test_validate_column_paths_rejects_key_meta_on_list_iter(self):
        """
        Ensure ``@key`` on a list-iter alias raises ``InvalidMetaAccessor``.
        """
        table = self._point_scope()
        with self.assertRaises(InvalidMetaAccessor) as cm:
            validate_column_paths(
                desugar_columns(["point.@key"], table),
                table,
                allow_container_terminals=False,
            )
        self.assertEqual(cm.exception.accessor, "key")
        self.assertIn("dict iter scope", cm.exception.reason)

    def test_validate_column_paths_rejects_meta_after_extra_segment(self):
        """
        Ensure a meta-accessor preceded by more than the alias head (e.g.
        ``alias.field.@index``) raises ``InvalidMetaAccessor``. Spec §7.1
        only allows ``<alias>.@<name>``; deeper paths are not legal because
        ``@index`` reports the position of the iter-bound alias, not of an
        intermediate value.
        """
        table = self._point_scope()
        with self.assertRaises(InvalidMetaAccessor) as cm:
            validate_column_paths(
                desugar_columns(["point.chemistry.@index"], table),
                table,
                allow_container_terminals=False,
            )
        self.assertEqual(cm.exception.accessor, "index")

    def test_validate_column_paths_meta_with_unknown_alias_raises_unknown_scope(self):
        """
        Ensure a meta-accessor whose head alias is not in the scope table
        raises ``UnknownScope`` (consistent with non-meta paths). Catches
        the alias-resolution step inside ``_validate_meta_path``.
        """
        table = self._point_scope()
        with self.assertRaises(UnknownScope):
            validate_column_paths(
                desugar_columns(["ghost.@index"], table),
                table,
                allow_container_terminals=False,
            )
