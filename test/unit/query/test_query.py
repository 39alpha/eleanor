from unittest import TestCase

from eleanor.query import compile_query, evaluate
from eleanor.query.errors import MultipleMatchError, ParseError
from eleanor.query.path import parse_path, path_to_string

from .models import Chemistry, Point, SimpleSample


class TestPathParsing(TestCase):
    """
    Tests for EQL path parsing and canonical rendering.
    """

    def test_parse_path_round_trips_quoted_predicates(self):
        """
        Ensure quoted predicate values with escapes survive parse and stringify.
        """
        path = parse_path('point.minerals[name="Ca\\"CO3"]')
        self.assertEqual(path_to_string(path), 'point.minerals[name="Ca\\"CO3"]')

    def test_parse_path_rejects_trailing_dot(self):
        """
        Ensure malformed paths with trailing separators raise ParseError.
        """
        with self.assertRaises(ParseError):
            parse_path("point.")


class TestCompileAndEvaluate(TestCase):
    """
    Integration tests for compile_query + evaluate over representative dataclasses.
    """

    def test_shortname_row_scope_and_missing_default(self):
        """
        Ensure shortname row_scope resolves and per-column null-default fills path misses.
        """
        sample = SimpleSample(
            points=[
                Point(index=1, chemistry=Chemistry(ph=7.1, pe=4.2), minerals=[]),
                Point(index=2, chemistry=None, minerals=[]),
            ]
        )
        query: dict[str, object] = {
            "row_scope": "point",
            "on_missing": "blank",
            "columns": [
                "point.index",
                {"path": "point.chemistry.ph", "name": "ph"},
                {"path": "point.chemistry.pe", "name": "pe_or_default", "on_missing": "null", "default": -99.0},
            ],
        }

        compiled = compile_query(SimpleSample, query)
        self.assertEqual(path_to_string(compiled.row_scope_path), "points[*]")

        rows = list(evaluate(compiled, sample))
        self.assertEqual(
            rows,
            [
                {"index": 1, "ph": 7.1, "pe_or_default": 4.2},
                {"index": 2, "ph": None, "pe_or_default": -99.0},
            ],
        )

    def test_evaluate_raises_on_multiple_match_filter_results(self):
        """
        Ensure list match filters that produce multiple matches raise MultipleMatchError.
        """
        sample = SimpleSample(
            points=[
                Point(index=1, chemistry=Chemistry(ph=7.0, pe=3.1), minerals=[]),
                Point(index=1, chemistry=Chemistry(ph=7.5, pe=3.2), minerals=[]),
            ]
        )
        query: dict[str, object] = {
            "row_scope": "order",
            "columns": ["order.points[index=1].index"],
        }

        compiled = compile_query(SimpleSample, query)
        with self.assertRaises(MultipleMatchError):
            list(evaluate(compiled, sample))
