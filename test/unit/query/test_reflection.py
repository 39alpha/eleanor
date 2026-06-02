from unittest import TestCase

from eleanor.query.errors import InvalidFilter, InvalidFilterValue, InvalidPath
from eleanor.query.path import parse_path
from eleanor.query.reflection import (
    DataclassField,
    DictField,
    LeafField,
    ListField,
    dataclass_fields,
    leaf_fields,
    walk_path,
)

from .models import Point, Sample


class TestReflection(TestCase):
    """
    Tests for dataclass reflection and typed path walking.
    """

    def test_dataclass_fields_classify_collection_kinds(self):
        """
        Ensure field introspection identifies dataclass, list, and dict field kinds.
        """
        kinds = {field.name: field for field in dataclass_fields(Sample)}
        self.assertIsInstance(kinds["point"], DataclassField)
        self.assertIsInstance(kinds["points"], ListField)
        self.assertIsInstance(kinds["point_map"], DictField)

    def test_leaf_fields_only_returns_non_container_fields(self):
        """
        Ensure leaf_fields only includes scalar leaves for a dataclass.
        """
        leaves = leaf_fields(Point)
        self.assertEqual({field.name for field in leaves}, {"index"})
        self.assertTrue(all(isinstance(field, LeafField) for field in leaves))

    def test_walk_path_allows_list_match_and_nested_segments(self):
        """
        Ensure list match filters validate and advance to nested leaf segments.
        """
        steps = walk_path(Sample, parse_path("points[index=1].chemistry.ph"))
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0].segment.name, "points")
        self.assertEqual(steps[-1].segment.name, "ph")

    def test_walk_path_rejects_unknown_segment(self):
        """
        Ensure unknown segments raise InvalidPath.
        """
        with self.assertRaises(InvalidPath):
            walk_path(Sample, parse_path("point.chemistry.unknown"))

    def test_walk_path_rejects_invalid_filter_target(self):
        """
        Ensure wildcard filters on non-container fields raise InvalidFilter.
        """
        with self.assertRaises(InvalidFilter):
            walk_path(Sample, parse_path("point.chemistry[*]"))

    def test_walk_path_rejects_invalid_filter_value_type(self):
        """
        Ensure predicate literals that cannot coerce to declared types raise InvalidFilterValue.
        """
        with self.assertRaises(InvalidFilterValue):
            walk_path(Sample, parse_path("points[index=abc]"))
