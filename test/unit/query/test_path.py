from eleanor.query.errors import ParseError
from eleanor.query.path import (
    IterFilter,
    MatchFilter,
    MetaSegment,
    Path,
    parse_path,
    parse_row_scope,
    path_to_string,
    quote_predicate_value,
)

from ..common import TestCase


class TestPath(TestCase):
    """
    Tests for EQL path parsing and canonical string rendering.
    """

    def test_adjacent_match_filters_are_merged(self):
        """
        Ensure consecutive match filters on a segment merge into one predicate set.
        """
        parsed = parse_path("point.minerals[name=calcite][amount=0.3]")
        self.assertEqual(len(parsed.segments), 2)
        self.assertEqual(len(parsed.segments[1].filters), 1)
        self.assertIsInstance(parsed.segments[1].filters[0], MatchFilter)
        merged = parsed.segments[1].filters[0]
        assert isinstance(merged, MatchFilter)
        self.assertEqual(len(merged.predicates), 2)

    def test_path_to_string_escapes_quoted_predicates(self):
        """
        Ensure stringification preserves escapes for quoted predicate values.
        """
        parsed = parse_path('point.minerals[name="Ca\\"CO3"]')
        self.assertEqual(path_to_string(parsed), 'point.minerals[name="Ca\\"CO3"]')

    def test_parse_row_scope_returns_identifier_for_simple_name(self):
        """
        Ensure a single unfiltered segment row scope parses as an identifier-like string.
        """
        parsed = parse_row_scope("point")
        self.assertIsInstance(parsed, str)
        self.assertEqual(parsed, "point")

    def test_parse_row_scope_returns_path_when_filters_present(self):
        """
        Ensure filtered row_scope text returns a Path object.
        """
        parsed = parse_row_scope("points[*]")
        self.assertIsInstance(parsed, Path)
        assert isinstance(parsed, Path)
        self.assertEqual(len(parsed.segments), 1)
        self.assertIsInstance(parsed.segments[0].filters[0], IterFilter)

    def test_parse_path_rejects_invalid_structures(self):
        """
        Ensure malformed path grammar is rejected with ParseError.
        """
        with self.assertRaises(ParseError):
            parse_path("point.")
        with self.assertRaises(ParseError):
            parse_path("point[]")
        with self.assertRaises(ParseError):
            parse_path('point.minerals[name="bad\\q"]')

    def test_quote_predicate_value_keeps_safe_values_bare(self):
        """
        Ensure values whose characters are all legal under ``Unquoted`` round-trip verbatim.
        """
        self.assertEqual(quote_predicate_value("Ca+2"), "Ca+2")
        self.assertEqual(quote_predicate_value("HCO3-"), "HCO3-")
        parsed = parse_path(f"x[name={quote_predicate_value('Ca+2')}]")
        match = parsed.segments[0].filters[0]
        assert isinstance(match, MatchFilter)
        self.assertEqual(match.predicates[0].value, "Ca+2")
        self.assertFalse(match.predicates[0].value_quoted)

    def test_quote_predicate_value_quotes_and_escapes_unsafe_values(self):
        """
        Ensure whitespace, ``=``, ``,``, ``]``, ``"``, and the empty string
        force a quoted form whose escapes round-trip through ``parse_path``.
        Bare backslash is legal under ``Unquoted`` (spec §4) and stays bare,
        but is escaped correctly when other unsafe characters force quoting.
        """
        self.assertEqual(quote_predicate_value(""), '""')
        self.assertEqual(quote_predicate_value('a"b'), '"a\\"b"')
        # Bare backslash is a valid ``UnquotedChar`` per spec §4 so it stays
        # bare; it only needs escaping when another character forces quoting.
        self.assertEqual(quote_predicate_value("a\\b"), "a\\b")
        self.assertEqual(quote_predicate_value('a"\\b'), '"a\\"\\\\b"')
        for unsafe in ("a b", "a=b", "a,b", "a]b"):
            quoted = quote_predicate_value(unsafe)
            self.assertTrue(quoted.startswith('"') and quoted.endswith('"'))
            parsed = parse_path(f"x[name={quoted}]")
            match = parsed.segments[0].filters[0]
            assert isinstance(match, MatchFilter)
            self.assertEqual(match.predicates[0].value, unsafe)
            self.assertTrue(match.predicates[0].value_quoted)

    def test_parse_path_recognizes_terminal_meta_accessor(self):
        """
        Ensure ``<alias>.@<name>`` parses to a Path whose ``meta`` field
        carries the accessor name (spec §4). The non-meta segments retain
        their normal AST shape.
        """
        parsed = parse_path("vs.@index")
        self.assertEqual(len(parsed.segments), 1)
        self.assertEqual(parsed.segments[0].name, "vs")
        self.assertIsNotNone(parsed.meta)
        assert parsed.meta is not None
        self.assertIsInstance(parsed.meta, MetaSegment)
        self.assertEqual(parsed.meta.name, "index")

        deep = parse_path("a.b.c.@key")
        self.assertEqual([seg.name for seg in deep.segments], ["a", "b", "c"])
        assert deep.meta is not None
        self.assertEqual(deep.meta.name, "key")

    def test_path_to_string_round_trips_meta_segment(self):
        """
        Ensure ``path_to_string`` re-emits the trailing ``.@<name>`` and that
        the result parses back to an equal Path.
        """
        text = "solid_solution.@index"
        parsed = parse_path(text)
        self.assertEqual(path_to_string(parsed), text)
        self.assertEqual(parse_path(path_to_string(parsed)), parsed)

    def test_path_to_string_renders_orphan_meta(self):
        """
        Ensure ``path_to_string`` renders a Path constructed with no segments
        and a meta as ``@<name>``. Such a Path is unreachable through the
        parser (which requires a leading segment) but the renderer should
        still produce a sensible string for callers that build Paths
        programmatically.
        """
        orphan = Path(segments=tuple(), meta=MetaSegment(name="index"))
        self.assertEqual(path_to_string(orphan), "@index")

    def test_parse_row_scope_rejects_meta_accessor_terminal(self):
        """
        Ensure ``parse_row_scope`` raises ``ParseError`` for any input whose
        path has a meta-accessor terminal. Meta-accessors are only valid in
        column paths; accepting them silently in row_scope would discard the
        accessor (single-segment case) or produce a scope table built from the
        wrong path (filtered case).
        """
        with self.assertRaises(ParseError):
            parse_row_scope("vs.@index")
        with self.assertRaises(ParseError):
            parse_row_scope("points[*].@index")

    def test_parse_path_rejects_malformed_meta_segments(self):
        """
        Ensure malformed meta-accessor surfaces (no leading segment, missing
        identifier, anything after the meta) raise ``ParseError`` at parse
        time. Validity of the meta name itself is enforced at compile time,
        not here.
        """
        with self.assertRaises(ParseError):
            parse_path("@index")
        with self.assertRaises(ParseError):
            parse_path("vs.@")
        with self.assertRaises(ParseError):
            parse_path("vs.@123")
        with self.assertRaises(ParseError):
            parse_path("vs.@index.foo")
        with self.assertRaises(ParseError):
            parse_path("vs.@index@key")
