from dataclasses import dataclass
from unittest import TestCase

from eleanor.query import compile_query, evaluate
from eleanor.query.errors import MultipleMatchError, ParseError, PathMissError
from eleanor.query.reflection import DataclassField, LeafField

from .models import Chemistry, Mineral, Point, Sample, make_sample


@dataclass
class _NestedRoot:
    """Two-level list nesting used to verify per-level @index bindings."""

    points: list[Point]


class TestCompilerEvaluator(TestCase):
    """
    Tests for compile_query and evaluate behavior beyond basic happy-path integration.
    """

    def test_compile_query_rejects_unknown_top_level_keys(self):
        """
        Ensure unknown query mapping keys raise ParseError during compile.
        """
        with self.assertRaises(ParseError):
            compile_query(Sample, {"row_scope": "order", "columns": [], "extra": 1})

    def test_compile_query_rejects_unsupported_version(self):
        """
        Ensure unsupported query versions are rejected.
        """
        with self.assertRaises(ParseError):
            compile_query(Sample, {"row_scope": "order", "columns": [], "version": 99})

    def test_compile_query_rejects_non_sequence_columns(self):
        """
        Ensure columns must be a sequence and not a scalar value.
        """
        with self.assertRaises(ParseError):
            compile_query(Sample, {"row_scope": "order", "columns": "order.point.index"})

    def test_evaluate_raises_path_miss_error_for_on_missing_error(self):
        """
        Ensure missing-path rows raise PathMissError when on_missing policy is error.
        """
        query: dict[str, object] = {
            "row_scope": "points[*]",
            "on_missing": "error",
            "columns": [{"path": "point.chemistry.ph", "name": "ph"}],
        }
        compiled = compile_query(Sample, query)
        with self.assertRaises(PathMissError):
            list(evaluate(compiled, make_sample()))

    def test_evaluate_supports_dict_key_predicate_matching(self):
        """
        Ensure dict filters can match by key and return the selected value branch.
        """
        query: dict[str, object] = {
            "row_scope": "order",
            "columns": ["order.point_map[key=c].index"],
        }
        compiled = compile_query(Sample, query)
        rows = list(evaluate(compiled, make_sample()))
        self.assertEqual(rows, [{"index": 3}])

    def test_evaluate_supports_dict_iter_row_scope(self):
        """
        Ensure row_scope using dict [*] iterates dict values in insertion order (spec §12.2).
        """
        query: dict[str, object] = {
            "row_scope": "point_map[*]",
            "columns": ["self.index"],
        }
        compiled = compile_query(Sample, query)
        rows = list(evaluate(compiled, make_sample()))
        self.assertEqual([row["index"] for row in rows], [1, 1, 3])

    def test_evaluate_raises_on_multiple_dict_filter_matches(self):
        """
        Ensure dict match filters that match multiple entries raise MultipleMatchError.
        """
        query: dict[str, object] = {
            "row_scope": "order",
            "columns": ["order.point_map[index=1].index"],
        }
        compiled = compile_query(Sample, query)
        with self.assertRaises(MultipleMatchError):
            list(evaluate(compiled, make_sample()))

    def test_evaluate_index_meta_accessor_for_list_iter(self):
        """
        Ensure ``<list-iter-alias>.@index`` produces the 0-based position of
        each row's iter-bound element within its parent list (spec §7.1).
        Default column name is ``index`` (without leading ``@``); explicit
        names are honoured as-is.
        """
        compiled = compile_query(
            Sample,
            {
                "row_scope": "points[*]",
                "columns": [
                    {"path": "point.@index", "name": "position"},
                    {"path": "point.index", "name": "point_index"},
                ],
            },
        )
        rows = list(evaluate(compiled, make_sample()))
        self.assertEqual(
            rows,
            [{"position": 0, "point_index": 1}, {"position": 1, "point_index": 2}],
        )

    def test_implicit_meta_and_field_names_collide_after_prefixing(self):
        """
        Ensure spec §8.5 collision detection fires when a meta-accessor and a
        same-name leaf field on the same alias both rely on default naming:
        both default to ``index``, both alias-prefix to ``point_index``, and
        the second pass raises ``ColumnNameCollision``.
        """
        from eleanor.query.errors import ColumnNameCollision

        with self.assertRaises(ColumnNameCollision):
            compile_query(
                Sample,
                {
                    "row_scope": "points[*]",
                    "columns": ["point.@index", "point.index"],
                },
            )

    def test_evaluate_index_and_key_meta_accessors_for_dict_iter(self):
        """
        Ensure ``<dict-iter-alias>.@index`` and ``.@key`` expose the 0-based
        insertion position and the dict key for each row of a dict row_scope.
        """
        query: dict[str, object] = {
            "row_scope": "point_map[*]",
            "columns": [
                {"path": "point_map.@index", "name": "position"},
                {"path": "point_map.@key", "name": "key"},
                "self.index",
            ],
        }
        compiled = compile_query(Sample, query)
        rows = list(evaluate(compiled, make_sample()))
        self.assertEqual(
            rows,
            [
                {"position": 0, "key": "a", "index": 1},
                {"position": 1, "key": "b", "index": 1},
                {"position": 2, "key": "c", "index": 3},
            ],
        )

    def test_evaluate_index_meta_for_nested_iters_per_alias(self):
        """
        Ensure each iter-bound alias in a nested row_scope carries its own
        ``@index``: the outer alias reports the outer position, the inner
        alias (and ``self``) report the inner position, refreshing per
        outer iteration.
        """
        sample = _NestedRoot(
            points=[
                Point(
                    index=10,
                    chemistry=None,
                    minerals=[Mineral(name="a", amount=1.0), Mineral(name="b", amount=2.0)],
                ),
                Point(
                    index=20,
                    chemistry=None,
                    minerals=[Mineral(name="c", amount=3.0)],
                ),
            ]
        )
        query: dict[str, object] = {
            "row_scope": "points[*].minerals[*]",
            "columns": [
                {"path": "point.@index", "name": "point_pos"},
                {"path": "mineral.@index", "name": "mineral_pos"},
                {"path": "self.@index", "name": "self_pos"},
                "mineral.name",
            ],
        }
        compiled = compile_query(_NestedRoot, query)
        rows = list(evaluate(compiled, sample))
        self.assertEqual(
            rows,
            [
                {"point_pos": 0, "mineral_pos": 0, "self_pos": 0, "name": "a"},
                {"point_pos": 0, "mineral_pos": 1, "self_pos": 1, "name": "b"},
                {"point_pos": 1, "mineral_pos": 0, "self_pos": 0, "name": "c"},
            ],
        )

    def test_evaluate_meta_accessor_default_column_name_strips_at(self):
        """
        Ensure the default column name for a meta-accessor terminal drops
        the leading ``@`` (spec §8.5).
        """
        compiled = compile_query(Sample, {"row_scope": "point_map[*]", "columns": ["point_map.@key"]})
        self.assertEqual([c.spec.name for c in compiled.compiled_columns], ["key"])

    def test_compiled_column_terminal_kind_leaf_path(self):
        """Ensure leaf terminal paths expose their resolved LeafField kind."""
        compiled = compile_query(Sample, {"row_scope": "order", "columns": ["order.point.index"]})
        terminal_kind = compiled.compiled_columns[0].terminal_kind
        self.assertIsInstance(terminal_kind, LeafField)
        assert isinstance(terminal_kind, LeafField)
        self.assertIs(terminal_kind.declared_type, int)
        self.assertFalse(terminal_kind.optional)

    def test_compiled_column_terminal_kind_optional_dataclass(self):
        """Ensure optional dataclass terminals preserve optionality in terminal_kind."""
        compiled = compile_query(
            Sample, {"row_scope": "order", "columns": ["order.point.chemistry"]}, allow_container_terminals=True
        )
        terminal_kind = compiled.compiled_columns[0].terminal_kind
        self.assertIsInstance(terminal_kind, DataclassField)
        assert isinstance(terminal_kind, DataclassField)
        self.assertIs(terminal_kind.dataclass_type, Chemistry)
        self.assertTrue(terminal_kind.optional)

    def test_compiled_column_terminal_kind_list_match_filter_mid_path(self):
        """Ensure list match-filter branches contribute to terminal kind computation."""
        compiled = compile_query(Sample, {"row_scope": "order", "columns": ["order.points[index=1].index"]})
        terminal_kind = compiled.compiled_columns[0].terminal_kind
        self.assertIsInstance(terminal_kind, LeafField)
        assert isinstance(terminal_kind, LeafField)
        self.assertIs(terminal_kind.declared_type, int)

    def test_compiled_column_terminal_kind_dict_match_filter_mid_path(self):
        """Ensure dict match-filter branches are reflected in terminal_kind."""
        compiled = compile_query(Sample, {"row_scope": "order", "columns": ["order.point_map[key=c].index"]})
        terminal_kind = compiled.compiled_columns[0].terminal_kind
        self.assertIsInstance(terminal_kind, LeafField)
        assert isinstance(terminal_kind, LeafField)
        self.assertIs(terminal_kind.declared_type, int)

    def test_compiled_column_terminal_kind_alias_only_column(self):
        """Ensure single-segment alias columns use the alias scope type_kind."""
        compiled = compile_query(Sample, {"row_scope": "order", "columns": ["order"]}, allow_container_terminals=True)
        terminal_kind = compiled.compiled_columns[0].terminal_kind
        self.assertIsInstance(terminal_kind, DataclassField)
        assert isinstance(terminal_kind, DataclassField)
        self.assertIs(terminal_kind.dataclass_type, Sample)

    def test_compiled_column_terminal_kind_excludes_meta_accessor(self):
        """Ensure terminal_kind reflects path segments only; @index/@key meta is intentionally excluded."""
        compiled = compile_query(Sample, {"row_scope": "points[*]", "columns": ["point.@index"]})
        terminal_kind = compiled.compiled_columns[0].terminal_kind
        self.assertIsInstance(terminal_kind, DataclassField)
        assert isinstance(terminal_kind, DataclassField)
        self.assertIs(terminal_kind.dataclass_type, Point)
