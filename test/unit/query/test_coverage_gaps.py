from dataclasses import dataclass
from typing import Dict, List
from unittest import mock

import eleanor.query.aliases as aliases_module
import eleanor.query.columns as columns_module
import eleanor.query.compiler as compiler_module
import eleanor.query.evaluator as evaluator_module
import eleanor.query.reflection as reflection_module
import eleanor.query.scope as scope_module
from eleanor.query import compile_query, evaluate
from eleanor.query.columns import BarePath, ColumnSpec
from eleanor.query.compiler import (
    CompiledColumn,
    CompiledIterFilter,
    CompiledMatchFilter,
    CompiledPath,
    CompiledPredicate,
)
from eleanor.query.errors import (
    AliasCollision,
    AmbiguousRowScope,
    ColumnNameCollision,
    InvalidFilter,
    InvalidFilterValue,
    InvalidMetaAccessor,
    InvalidPath,
    InvalidRowScope,
    MultipleMatchError,
    ParseError,
    PathMissError,
    PresetScopeMissing,
    SplatUnknownField,
    UnknownPreset,
    UnknownRowScope,
    UnknownScope,
)
from eleanor.query.path import MetaSegment, Path, Predicate, Segment, parse_path, predicate_text
from eleanor.query.reflection import DataclassField, DictField, LeafField, ListField, StepInfo, classify_field
from eleanor.query.scope import AmbientScopeTable

from ..common import TestCase
from .models import Chemistry, Point, Sample, make_sample


@dataclass
class NumberRoot:
    numbers: list[int]


@dataclass
class BucketRoot:
    buckets: dict[int, Point]


@dataclass
class SingleRoot:
    point: Point


@dataclass
class AxisRoot:
    axes: list[Point]
    axises: list[Point]


@dataclass
class LeafMapRoot:
    point_map: dict[str, int]


@dataclass
class _CollidingShortFormRoot:
    """Root type whose ``vses`` field singularizes to ``vs``—the short form
    of ``vs_point``—to exercise ``validate_short_forms_for_root``'s collision
    branch.
    """

    vses: list[Point]


@dataclass
class _RecursiveRoot:
    """Self-referential root used to force the BFS in
    ``enumerate_shortname_paths`` to hit ``_DEFAULT_SHORTNAME_MAX_DEPTH`` and
    surface the depth-limit hint via ``UnknownRowScope``.
    """

    next: "_RecursiveRoot | None"


class TestAliasesCoverage(TestCase):
    """
    Additional alias-logic coverage for remaining singularization and validation branches.
    """

    def test_singularize_remaining_suffix_branches(self):
        """
        Ensure singularize handles "men", trailing "s", and "ss" preservation branches.
        """
        self.assertEqual(aliases_module.singularize("women"), "woman")
        self.assertEqual(aliases_module.singularize("cars"), "car")
        self.assertEqual(aliases_module.singularize("glass"), "glass")
        self.assertEqual(aliases_module.aliases_for("cars"), ("car",))


class TestCoercionCoverage(TestCase):
    """
    Additional coercion coverage for float-failure and unsupported target branches.
    """

    def test_coerce_filter_value_rejects_invalid_float_and_unsupported_target(self):
        """
        Ensure float parse failures and non-supported target types raise InvalidFilterValue.
        """
        from eleanor.query.coercion import coerce_filter_value

        with self.assertRaises(InvalidFilterValue):
            coerce_filter_value(float, "bad", path="p", predicate="f=bad")
        with self.assertRaises(InvalidFilterValue):
            coerce_filter_value(bytes, "xyz", path="p", predicate="b=xyz")


class TestPathCoverage(TestCase):
    """
    Additional parser coverage for remaining parse error branches.
    """

    def test_parse_path_remaining_error_branches(self):
        """
        Ensure parser reports malformed filters, values, identifiers, and escapes.
        """
        with self.assertRaises(ParseError):
            parse_path(" ")
        with self.assertRaises(ParseError):
            parse_path("point$")
        with self.assertRaises(ParseError):
            parse_path("point[")
        with self.assertRaises(ParseError):
            parse_path("point[a=1 ;]")
        with self.assertRaises(ParseError):
            parse_path("point[a=1,b=2")
        with self.assertRaises(ParseError):
            parse_path("point[a=]")
        with self.assertRaises(ParseError):
            parse_path("point[a=")
        with self.assertRaises(ParseError):
            parse_path('point[a="abc')
        with self.assertRaises(ParseError):
            parse_path('point[a="abc\\')
        with self.assertRaises(ParseError):
            parse_path("1point")
        with self.assertRaises(ParseError):
            parse_path("point[a:1]")
        with self.assertRaises(ParseError):
            parse_path("point[a=1,")
        with self.assertRaises(ParseError):
            parse_path("point[*")
        parsed = parse_path("point[a=1,b=2]")
        self.assertEqual(len(parsed.segments[0].filters), 1)


class TestErrorsCoverage(TestCase):
    """
    Exercise __str__ branches for query-specific structured exceptions.
    """

    def test_query_error_string_representations(self):
        """
        Ensure all query error types render expected user-facing messages.
        """
        self.assertIn("position 4", str(ParseError("bad", position=4)))
        self.assertEqual(str(ParseError("bad")), "bad")
        self.assertIn("unknown row_scope", str(UnknownRowScope("x")))
        self.assertIn("ambiguous row_scope", str(AmbiguousRowScope("x", ["a", "b"])))
        self.assertIn("invalid row_scope", str(InvalidRowScope("x", "why")))
        self.assertIn("invalid path", str(InvalidPath("x", "y", dict)))
        self.assertIn("invalid filter", str(InvalidFilter("x", "y", "z")))
        self.assertIn("invalid filter value", str(InvalidFilterValue("x", "p", "v", int)))
        self.assertIn("unknown scope alias", str(UnknownScope("a", ["b"])))
        self.assertIn("alias collision", str(AliasCollision("a", ["x", "y"])))
        self.assertIn("column name collision", str(ColumnNameCollision("c", ["x", "y"])))
        self.assertIn("splat on", str(SplatUnknownField("a", "f", ["g"])))
        self.assertIn("requires missing alias", str(PresetScopeMissing("p", "x")))
        self.assertIn("unknown preset", str(UnknownPreset("p")))
        self.assertIn("invalid meta-accessor", str(InvalidMetaAccessor("a.@b", "b", "because")))
        self.assertIn("@b", str(InvalidMetaAccessor("a.@b", "b", "because")))
        self.assertIn("path miss", str(PathMissError(1, "c", "s")))
        self.assertIn("multiple matches", str(MultipleMatchError("p", "k=1", 2)))


class TestReflectionCoverage(TestCase):
    """
    Additional reflection coverage for private helper and rare validation branches.
    """

    def test_classification_and_non_dataclass_helpers(self):
        """
        Ensure generic type fallback classification and non-dataclass reflection behavior.
        """
        self.assertEqual(reflection_module.dataclass_fields(dict), [])
        self.assertEqual(reflection_module.unwrap_optional(int | str), (int | str, False))
        self.assertEqual(reflection_module.unwrap_optional(type(None) | int), (int, True))
        # Multi-arm unions (3+) and 2-arm unions without ``None`` both fall
        # through to ``(t, False)`` per ``unwrap_optional``'s contract.
        self.assertEqual(reflection_module.unwrap_optional(int | str | None), (int | str | None, False))

        # typing.List / typing.Dict are deprecated as of 3.9 but they are the
        # natural way to exercise classify_field's empty-args fallback for the
        # list/dict origin branches: get_origin returns list/dict but get_args
        # is empty. Modern lowercase `list`/`dict` (bare) take a different path
        # (LeafField), so they don't substitute here.
        list_kind = classify_field("x", List)
        dict_kind = classify_field("y", Dict)
        self.assertIsInstance(list_kind, ListField)
        self.assertIsInstance(dict_kind, DictField)

        # ``coercion_target`` falls back to ``object`` for non-type annotations.
        # End-to-end paths always go through the live ``classify_field``, which
        # produces ``LeafField.declared_type: type[object]``, so the fallback
        # is unreachable from queries; cover it directly.
        self.assertIs(reflection_module.coercion_target("not_a_type"), object)
        self.assertFalse(reflection_module._is_union_origin(None))

    def test_walk_path_additional_invalid_filter_branches(self):
        """
        Ensure list/dict filter validation rejects unknown, non-leaf, and key coercion failures.
        """
        with self.assertRaises(InvalidFilter):
            reflection_module.walk_path(NumberRoot, parse_path("numbers[index=1]"))
        with self.assertRaises(InvalidFilter):
            reflection_module.walk_path(LeafMapRoot, parse_path("point_map[value=1]"))
        with self.assertRaises(InvalidFilterValue):
            reflection_module.walk_path(BucketRoot, parse_path("buckets[key=abc]"))
        with self.assertRaises(InvalidFilter):
            reflection_module.walk_path(Sample, parse_path("point_map[chemistry=1]"))
        with self.assertRaises(InvalidFilterValue):
            reflection_module.walk_path(Sample, parse_path("point_map[index=abc]"))
        with self.assertRaises(InvalidFilter):
            reflection_module.walk_path(Sample, parse_path("point.index[id=1]"))

    def test_walk_path_invalid_path_reports_container_owner_type(self):
        """
        Ensure unresolved segments on list/dict/leaf kinds raise InvalidPath
        whose owner_type is rendered in the error message. This exercises the
        list/dict/leaf branches of ``reflection.owner_type`` end-to-end.
        """
        with self.assertRaises(InvalidPath) as list_cm:
            reflection_module.walk_path(Sample, parse_path("points.chemistry"))
        self.assertIs(list_cm.exception.owner_type, list)
        self.assertIn("list", str(list_cm.exception))

        with self.assertRaises(InvalidPath) as dict_cm:
            reflection_module.walk_path(Sample, parse_path("point_map.index"))
        self.assertIs(dict_cm.exception.owner_type, dict)
        self.assertIn("dict", str(dict_cm.exception))

        # Descending past a leaf field reports the leaf's declared type.
        with self.assertRaises(InvalidPath) as leaf_cm:
            reflection_module.walk_path(Sample, parse_path("point.index.something"))
        self.assertIs(leaf_cm.exception.owner_type, int)
        self.assertIn("int", str(leaf_cm.exception))


class TestScopeCoverage(TestCase):
    """
    Additional scope coverage for table helpers, traversal limits, and terminal validation.
    """

    def test_ambient_scope_table_helpers(self):
        """
        Ensure table helpers report aliases/items and require missing aliases correctly.
        """
        table = AmbientScopeTable()
        kind = DataclassField(name="order", dataclass_type=Sample, optional=False)
        table.add("order", Path(segments=tuple()), kind, terminal=False)
        table.add("order", Path(segments=tuple()), kind, terminal=True)
        self.assertEqual(table.available_aliases(), ["order"])
        self.assertEqual(len(table.items()), 1)
        self.assertIs(table.require("preset", "order").type_kind, kind)
        with self.assertRaises(PresetScopeMissing):
            table.require("preset", "missing")

    def test_enumerate_shortname_paths_depth_and_state_branches(self):
        """
        Ensure shortname enumeration handles depth cutoff and non-dataclass continuation.
        """
        self.assertEqual(scope_module.enumerate_shortname_paths(SingleRoot, "point", max_depth=0), [])
        self.assertTrue(len(scope_module.enumerate_shortname_paths(AxisRoot, "axis")) >= 1)
        self.assertEqual(len(scope_module.enumerate_shortname_paths(NumberRoot, "number")), 1)

    def test_resolve_row_scope_additional_terminal_cases(self):
        """
        Ensure row_scope resolution handles None input, no-filter segments, and terminal helper branches.
        """
        with self.assertRaises(ParseError):
            scope_module.resolve_row_scope(SingleRoot, None)
        resolved, table = scope_module.resolve_row_scope(SingleRoot, "point")
        self.assertEqual(len(resolved.segments), 1)
        self.assertIn("point", table)
        self.assertEqual(len(scope_module.resolve_row_scope(NumberRoot, "numbers[*]")[0].segments), 1)

        fake_steps: list[StepInfo] = []
        nonempty_path = Path(segments=(Segment(name="x", filters=tuple()),))
        self.assertFalse(scope_module._valid_row_scope_terminal(nonempty_path, fake_steps))
        self.assertTrue(scope_module._valid_row_scope_terminal(Path(segments=tuple()), []))

    def test_validate_short_forms_for_root_rejects_colliding_default_alias(self):
        """
        Ensure a field whose default alias singularizes to a registered short-form
        value (e.g., ``vses``→``vs``) raises ``AliasCollision`` with the offending
        path. Exercises ``scope.validate_short_forms_for_root``'s collision and
        raise branches end-to-end via reflection.
        """
        with self.assertRaises(AliasCollision) as cm:
            scope_module.validate_short_forms_for_root(_CollidingShortFormRoot)
        self.assertEqual(cm.exception.alias, "vs")
        self.assertIn("vses", cm.exception.paths[0])

    def test_validate_short_forms_for_root_passes_for_clean_model(self):
        """
        Ensure ``Sample`` (which has no fields singularizing to ``vs``/``es``)
        validates without raising. Also covers the ``next_type is None`` and
        ``next_type in visited`` short-circuit branches via the leaf field
        ``Point.index`` and the back-references ``Sample.points`` /
        ``Sample.point_map``.
        """
        scope_module.validate_short_forms_for_root(Sample)

    def test_validate_short_forms_for_root_skips_walk_when_table_empty(self):
        """
        Ensure the early-return short-circuit triggers when no short forms are
        registered. We patch ``SHORT_FORM_INVERSE`` to an empty mapping so the
        walk is skipped entirely.
        """
        with mock.patch.object(scope_module, "SHORT_FORM_INVERSE", {}):
            scope_module.validate_short_forms_for_root(_CollidingShortFormRoot)

    def test_unknown_row_scope_includes_depth_hint_when_cap_hit(self):
        """
        Ensure ``UnknownRowScope`` carries a depth-limit hint when the BFS hit
        the depth cap before finding (or failing to find) the shortname.
        Uses a self-referential dataclass whose tree is unbounded so the BFS
        always hits the default cap.
        """
        with self.assertRaises(UnknownRowScope) as cm:
            scope_module.resolve_row_scope(_RecursiveRoot, "missing")
        self.assertIsNotNone(cm.exception.hint)
        self.assertIn("depth limit", str(cm.exception))

    def test_resolve_row_scope_shortname_validates_terminal(self):
        """
        Ensure shortname-resolved paths are run through the row_scope terminal
        validator. The current shortname enumerator only emits valid terminals,
        so we patch the diagnostic helper to return a leaf-terminal path and
        verify ``resolve_row_scope`` rejects it with ``InvalidRowScope``.
        """
        leaf_path = parse_path("point.index")
        with (
            mock.patch.object(scope_module, "_enumerate_with_diagnostic", return_value=([leaf_path], False)),
            self.assertRaises(InvalidRowScope),
        ):
            scope_module.resolve_row_scope(Sample, "index")


class TestColumnsCoverage(TestCase):
    """
    Additional columns coverage for rare desugaring and validation branches.
    """

    def _point_scope(self):
        return scope_module.resolve_row_scope(Sample, "points[*]")[1]

    def test_validate_column_paths_wraps_tail_walk_errors(self):
        """
        Ensure path/filter/value errors in tail walking are re-raised with full path context.
        """
        table = self._point_scope()
        with self.assertRaises(InvalidPath):
            columns_module.validate_column_paths(
                columns_module.desugar_columns(["point.nope"], table),
                table,
                allow_container_terminals=False,
            )
        with self.assertRaises(InvalidFilter):
            columns_module.validate_column_paths(
                columns_module.desugar_columns(["point.chemistry[*]"], table),
                table,
                allow_container_terminals=False,
            )
        with self.assertRaises(InvalidFilterValue):
            columns_module.validate_column_paths(
                columns_module.desugar_columns(["point.minerals[amount=abc].amount"], table),
                table,
                allow_container_terminals=False,
            )

    def test_validate_column_paths_non_dataclass_and_empty_path(self):
        """
        Ensure non-dataclass heads and empty paths are rejected.
        """
        number_table = scope_module.resolve_row_scope(NumberRoot, "numbers[*]")[1]
        specs = columns_module.desugar_columns(["number.value"], number_table)
        with self.assertRaises(InvalidPath):
            columns_module.validate_column_paths(specs, number_table, allow_container_terminals=False)

        empty_spec = ColumnSpec(
            name="empty",
            path=Path(segments=tuple()),
            on_missing=None,
            default=None,
            has_default=False,
            source=BarePath(),
        )
        with self.assertRaises(InvalidPath):
            columns_module.validate_column_paths([empty_spec], self._point_scope(), allow_container_terminals=False)

    def test_desugar_additional_error_branches(self):
        """
        Ensure desugaring rejects invalid entry types and malformed structured columns.
        """
        table = self._point_scope()
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([123], table)
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"path": 7}], table)
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"path": "point.index", "name": 5}], table)

    def test_splat_additional_error_and_filtering_branches(self):
        """
        Ensure splat handling covers alias typing, scope typing, include/exclude, and on_missing parsing.
        """
        table = self._point_scope()
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"splat": 7}], table)
        with self.assertRaises(UnknownScope):
            columns_module.desugar_columns([{"splat": "ghost"}], table)
        with self.assertRaises(ParseError):
            columns_module.desugar_columns(
                [{"splat": "point", "include": ["index"], "exclude": ["index"]}],
                table,
            )
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"splat": "point", "on_missing": "nope"}], table)
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"splat": "point", "include": 3}], table)
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"splat": "point", "include": ["index", 3]}], table)
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"splat": "point", "prefix": 3}], table)

        number_table = scope_module.resolve_row_scope(NumberRoot, "numbers[*]")[1]
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"splat": "number"}], number_table)

        specs = columns_module.desugar_columns([{"splat": "point", "exclude": ["index"]}], table)
        self.assertTrue(all(spec.name != "index" for spec in specs))

    def test_preset_entry_requires_string_name(self):
        """
        Ensure non-string preset entries raise ParseError before lookup.
        """
        table = self._point_scope()
        with self.assertRaises(ParseError):
            columns_module.desugar_columns([{"preset": 1}], table)

    def test_validate_column_paths_dataclass_terminal_reports_class_name(self):
        """
        Ensure a column path that ends at a non-leaf dataclass field raises
        ``InvalidPath`` whose ``owner_type`` is the dataclass type. This
        exercises the ``DataclassField`` branch of ``reflection.owner_type``
        via ``validate_column_paths`` (the existing ``point.minerals`` test
        in ``test_columns`` covers the ``ListField`` branch).
        """
        table = self._point_scope()
        with self.assertRaises(InvalidPath) as cm:
            columns_module.validate_column_paths(
                columns_module.desugar_columns(["point.chemistry"], table),
                table,
                allow_container_terminals=False,
            )
        self.assertIs(cm.exception.owner_type, Chemistry)
        self.assertIn("Chemistry", str(cm.exception))


class TestCompilerCoverage(TestCase):
    """
    Additional compiler coverage for private helper branches and rare filter failure modes.
    """

    def test_compile_query_missing_required_keys(self):
        """
        Ensure missing row_scope and columns keys both raise ParseError.
        """
        with self.assertRaises(ParseError):
            compile_query(Sample, {"columns": []})
        with self.assertRaises(ParseError):
            compile_query(Sample, {"row_scope": "order"})

    def test_compile_query_rejects_bool_version(self):
        """
        Ensure ``version: True`` is rejected even though ``True == 1``
        evaluates true under Python's ``bool``-is-``int`` quirk.
        """
        with self.assertRaises(ParseError):
            compile_query(Sample, {"row_scope": "order", "columns": [], "version": True})
        with self.assertRaises(ParseError):
            compile_query(Sample, {"row_scope": "order", "columns": [], "version": False})

    def test_compile_column_private_empty_and_single_segment_paths(self):
        """
        Ensure _compile_column handles empty and single-segment paths.
        """
        table = scope_module.resolve_row_scope(Sample, "order")[1]
        empty_spec = ColumnSpec(
            name="empty",
            path=Path(segments=tuple()),
            on_missing=None,
            default=None,
            has_default=False,
            source=BarePath(),
        )
        self.assertEqual(len(compiler_module._compile_column(empty_spec, table).compiled_path.segments), 0)

        single_spec = ColumnSpec(
            name="single",
            path=parse_path("order"),
            on_missing=None,
            default=None,
            has_default=False,
            source=BarePath(),
        )
        self.assertEqual(len(compiler_module._compile_column(single_spec, table).compiled_path.segments), 1)

    def test_compile_additional_filter_branches(self):
        """
        Ensure list/dict filter compile paths and failures cover remaining branches.
        """
        compiled = compile_query(
            Sample,
            {
                "row_scope": "order",
                "columns": [
                    {"path": "order.point_map[key=a].index", "name": "key_index"},
                ],
            },
        )
        self.assertEqual(len(compiled.compiled_columns), 1)

        with self.assertRaises(InvalidFilter):
            compile_query(Sample, {"row_scope": "order", "columns": ["order.point[*]"]})
        with self.assertRaises(InvalidFilter):
            compile_query(NumberRoot, {"row_scope": "order", "columns": ["order.numbers[index=1]"]})
        with self.assertRaises(InvalidFilter):
            compile_query(Sample, {"row_scope": "order", "columns": ["order.points[missing=1].index"]})
        with self.assertRaises(InvalidFilter):
            compile_query(Sample, {"row_scope": "order", "columns": ["order.points[chemistry=1].index"]})
        with self.assertRaises(InvalidFilter):
            compile_query(Sample, {"row_scope": "order", "columns": ["order.point_map[missing=1].index"]})
        with self.assertRaises(InvalidFilter):
            compile_query(Sample, {"row_scope": "order", "columns": ["order.point_map[chemistry=1].index"]})

    def test_resolve_match_filter_dispatch_and_validation(self):
        """
        Ensure ``reflection.resolve_match_filter`` raises ``InvalidFilter``
        for the leaf, list-without-dataclass-element, missing-list-field,
        and missing-dict-field branches. The compiler delegates to this
        helper so its match-filter validation is exercised here directly;
        the end-to-end query coverage in
        ``test_compile_additional_filter_branches`` exercises the same
        branches via ``compile_query``.
        """
        match_filter = compiler_module.MatchFilter((Predicate(field="x", value="1", value_quoted=False),))  # pyright: ignore[reportPrivateImportUsage]
        leaf = LeafField(name="v", declared_type=int, optional=False)
        with self.assertRaises(InvalidFilter):
            reflection_module.resolve_match_filter(leaf, match_filter, "p", "x")

        bad_list = ListField(name="n", element_type=int, element_kind=leaf, optional=False)
        with self.assertRaises(InvalidFilter):
            reflection_module.resolve_match_filter(bad_list, match_filter, "p", "n")

        good_list = ListField(
            name="points",
            element_type=Point,
            element_kind=DataclassField(name="point", dataclass_type=Point, optional=False),
            optional=False,
        )
        missing_filter = compiler_module.MatchFilter((Predicate(field="missing", value="1", value_quoted=False),))  # pyright: ignore[reportPrivateImportUsage]
        with self.assertRaises(InvalidFilter):
            reflection_module.resolve_match_filter(good_list, missing_filter, "p", "points")

        good_dict = DictField(
            name="points",
            key_type=str,
            value_type=Point,
            value_kind=DataclassField(name="point", dataclass_type=Point, optional=False),
            optional=False,
        )
        with self.assertRaises(InvalidFilter):
            reflection_module.resolve_match_filter(good_dict, missing_filter, "p", "points")

    def test_path_predicate_text_handles_quoted_values(self):
        """
        Ensure ``path.predicate_text`` escapes embedded quotes/backslashes for
        quoted-value predicates. Unquoted predicates are exercised broadly via
        ``path_to_string`` (see ``test_path``).
        """
        self.assertEqual(
            predicate_text(Predicate(field="k", value='v"w', value_quoted=True)),
            'k="v\\"w"',
        )


class TestEvaluatorCoverage(TestCase):
    """
    Additional evaluator coverage for private helpers and defensive branches.
    """

    def test_walk_row_scope_no_filter_segment(self):
        """
        Ensure ``_walk_row_scope`` handles the no-filter row_scope segment
        case (e.g., row_scope resolving to a ``DataclassField`` such as
        ``SingleRoot.point``). The walker reaches the leaf binding and
        ``evaluate`` yields a single row.
        """
        compiled = compile_query(SingleRoot, {"row_scope": "point", "columns": ["self.index"]})
        rows = list(evaluate(compiled, SingleRoot(point=Point(index=42, chemistry=None, minerals=[]))))
        self.assertEqual(rows, [{"index": 42}])

    def test_walk_row_scope_none_and_empty_values_paths(self):
        """
        Ensure row-scope walker handles None nodes and empty filtered values.
        """
        compiled = compile_query(Sample, {"row_scope": "points[*]", "columns": ["point.index"]})
        aliases = evaluator_module._aliases_by_path(compiled)
        self.assertEqual(
            list(
                evaluator_module._walk_row_scope(
                    compiled.row_scope_compiled_path,
                    None,
                    index=0,
                    binding={},
                    meta_binding={},
                    aliases_by_path=aliases,
                    row_scope_text="points[*]",
                )
            ),
            [],
        )

        sample = make_sample()
        sample.points = []
        self.assertEqual(
            list(
                evaluator_module._walk_row_scope(
                    compiled.row_scope_compiled_path,
                    sample,
                    index=0,
                    binding={},
                    meta_binding={},
                    aliases_by_path=aliases,
                    row_scope_text="points[*]",
                )
            ),
            [],
        )

    def test_evaluate_column_and_segment_helper_branches(self):
        """
        Ensure column-path and segment helper edge branches are covered.
        """
        compiled = compile_query(Sample, {"row_scope": "order", "columns": ["order.point.index"]})
        spec = compiled.compiled_columns[0].spec

        empty_column = CompiledColumn(
            spec=ColumnSpec(
                name="empty",
                path=Path(segments=tuple()),
                on_missing=None,
                default=None,
                has_default=False,
                source=BarePath(),
            ),
            compiled_path=CompiledPath(path=Path(segments=tuple()), segments=tuple()),
        )
        self.assertTrue(evaluator_module._evaluate_column_path(empty_column, {"order": make_sample()}, {})[1])

        missing_alias_column = CompiledColumn(
            spec=spec,
            compiled_path=CompiledPath(
                path=parse_path("missing.index"),
                segments=(compiled.compiled_columns[0].compiled_path.segments[0],),
            ),
        )
        self.assertEqual(evaluator_module._evaluate_column_path(missing_alias_column, {}, {})[2], "order")

        # ``_segment_values`` requires non-empty filters; the no-filter
        # terminal-None / non-terminal-None handling lives in
        # ``_evaluate_column_path`` itself and is exercised end-to-end by
        # the column-path tests above. Here we cover the
        # ``value is None`` early return for the filter case.
        self.assertEqual(
            evaluator_module._segment_values(None, (CompiledIterFilter(),), path_text="x"),
            [],
        )

        container_column = compile_query(
            Sample,
            {"row_scope": "order", "columns": [{"path": "order.points", "name": "points"}]},
            allow_container_terminals=True,
        ).compiled_columns[0]
        value, missing, _ = evaluator_module._evaluate_column_path(container_column, {"order": make_sample()}, {})
        self.assertFalse(missing)
        self.assertIsInstance(value, list)

    def test_evaluate_column_path_meta_with_missing_meta_binding_misses(self):
        """
        Ensure ``_evaluate_column_path`` returns a miss when a meta-accessor's
        anchor alias is bound but absent from ``meta_binding``. The validator
        prevents this in normal flow, but the defensive branch fires if a
        caller hands the evaluator a binding/meta_binding pair out of sync.
        """
        meta_path = Path(segments=(Segment(name="point", filters=tuple()),), meta=MetaSegment(name="index"))
        meta_column = CompiledColumn(
            spec=ColumnSpec(
                name="position",
                path=meta_path,
                on_missing=None,
                default=None,
                has_default=False,
                source=BarePath(),
            ),
            compiled_path=CompiledPath(
                path=meta_path,
                segments=(compiler_module.CompiledSegment(name="point", filters=tuple()),),
            ),
        )
        # Anchor alias is in ``binding`` (so the head-lookup branch passes)
        # but absent from ``meta_binding``: defensive miss.
        value, missing, segment = evaluator_module._evaluate_column_path(meta_column, {"point": object()}, {})
        self.assertIsNone(value)
        self.assertTrue(missing)
        self.assertEqual(segment, "point")

    def test_segment_values_with_meta_short_circuits_on_none(self):
        """
        Ensure ``_segment_values_with_meta`` returns ``[]`` immediately when
        the input value is ``None``. Mirrors ``_segment_values`` semantics
        for the row-scope walker variant.
        """
        self.assertEqual(
            evaluator_module._segment_values_with_meta(None, (CompiledIterFilter(),), path_text="x"),
            [],
        )

    def test_segment_values_with_meta_inner_iter_preserves_outer_position(self):
        """
        Ensure that when a single segment carries two iter filters
        (``[*][*]`` over a ``list[list[T]]``), the outer iter establishes
        the iter position and inner iter filters preserve it. This is the
        defensive branch for the rare nested-iter-on-one-segment shape;
        normal Eleanor data models don't produce it but reflection does
        accept it, so the walker must handle it.
        """
        nested_lists = [["a", "b"], ["c"]]
        result = evaluator_module._segment_values_with_meta(
            nested_lists,
            (CompiledIterFilter(), CompiledIterFilter()),
            path_text="x",
        )
        # Outer index should match each leaf's containing list (0 for ``a``
        # and ``b``, 1 for ``c``); ``key`` is None throughout (list iter).
        self.assertEqual(
            [(value, position.index, position.key) for value, position in result if position is not None],
            [("a", 0, None), ("b", 0, None), ("c", 1, None)],
        )

    def test_segment_values_iter_filter_branch_is_reachable_via_helper(self):
        """
        Ensure ``_segment_values`` handles iter filters when invoked directly.
        Production code routes iter filters through ``_segment_values_with_meta``
        in the row-scope walker and rejects them in column paths, so this
        branch is only reachable via direct calls; the helper is still part
        of the module's stable surface.
        """
        self.assertEqual(
            evaluator_module._segment_values([1, 2, 3], (CompiledIterFilter(),), path_text="x"),
            [1, 2, 3],
        )

    def test_segment_values_with_meta_match_filter_branches(self):
        """
        Ensure ``_segment_values_with_meta`` handles match filters: a hit
        produces a ``(value, None)`` pair (no iter position introduced), and
        a miss is skipped via the ``continue`` branch, returning an empty
        result list. This covers the row-scope walker's behaviour for
        match-only row_scope segments such as ``points[index=1]``.
        """
        match_hit = CompiledMatchFilter(
            predicates=(CompiledPredicate(field="index", value="1", value_quoted=False, coerced_value=1),),
        )
        points = [
            Point(index=1, chemistry=None, minerals=[]),
            Point(index=2, chemistry=None, minerals=[]),
        ]
        result = evaluator_module._segment_values_with_meta(points, (match_hit,), path_text="points[index=1]")
        self.assertEqual([(value, position) for value, position in result], [(points[0], None)])

        match_miss = CompiledMatchFilter(
            predicates=(CompiledPredicate(field="index", value="99", value_quoted=False, coerced_value=99),),
        )
        self.assertEqual(
            evaluator_module._segment_values_with_meta(points, (match_miss,), path_text="points[index=99]"),
            [],
        )

    def test_iter_match_attr_and_missing_helpers(self):
        """
        Ensure iterable, match, attribute, and missing-value helper edge branches are covered.
        """
        self.assertEqual(evaluator_module._iter_filter_values([1, 2]), [1, 2])
        self.assertEqual(evaluator_module._iter_filter_values({"a": 1, "b": 2}), [1, 2])
        self.assertEqual(evaluator_module._iter_filter_values(7), [])

        filter_expr = CompiledMatchFilter(
            predicates=(CompiledPredicate(field="x", value='a"b', value_quoted=True, coerced_value=1),),
        )
        self.assertIs(evaluator_module._match_filter_value(7, filter_expr, "p"), evaluator_module._MISS)
        self.assertIs(evaluator_module._match_filter_value([object()], filter_expr, "p"), evaluator_module._MISS)
        self.assertEqual(evaluator_module._compiled_match_text(filter_expr), 'x="a\\"b"')

        self.assertEqual(
            evaluator_module._segment_values([object()], (filter_expr,), path_text="p"),
            [],
        )

        class Item:
            value = 1

        self.assertTrue(
            evaluator_module._dict_item_matches(
                "k",
                Item(),
                (CompiledPredicate(field="key", value="k", value_quoted=False, coerced_value="k"),),
            )
        )
        self.assertFalse(
            evaluator_module._dict_item_matches(
                "k",
                object(),
                (CompiledPredicate(field="value", value="1", value_quoted=False, coerced_value=1),),
            )
        )
        self.assertFalse(
            evaluator_module._list_item_matches(
                object(),
                (CompiledPredicate(field="value", value="1", value_quoted=False, coerced_value=1),),
            )
        )

        self.assertIsNone(evaluator_module._get_attr(None, "x"))
        self.assertIsNone(evaluator_module._get_attr(object(), "x"))

        column = compile_query(Sample, {"row_scope": "order", "columns": ["order.point.index"]}).compiled_columns[0]
        self.assertIsNone(evaluator_module._missing_value("blank", column, 0, "x"))
        self.assertIsNone(evaluator_module._missing_value("null", column, 0, "x"))

    def test_missing_value_error_policy_raises_path_miss(self):
        """
        Ensure on_missing=error still routes through PathMissError.
        """
        query: dict[str, object] = {
            "row_scope": "points[*]",
            "on_missing": "error",
            "columns": [{"path": "point.chemistry.ph", "name": "ph"}],
        }
        with self.assertRaises(PathMissError):
            list(evaluate(compile_query(Sample, query), make_sample()))
