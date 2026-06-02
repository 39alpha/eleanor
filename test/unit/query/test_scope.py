from dataclasses import dataclass
from unittest import TestCase

from eleanor.query.errors import AliasCollision, AmbiguousRowScope, InvalidRowScope, UnknownRowScope
from eleanor.query.path import Path, parse_path, path_to_string
from eleanor.query.reflection import DataclassField
from eleanor.query.scope import AmbientScopeTable, resolve_row_scope

from .models import Point, Sample


@dataclass
class UniqueRoot:
    points: list[Point]


class TestScope(TestCase):
    """
    Tests for row_scope resolution and ambient alias table construction.
    """

    def test_resolve_row_scope_order_includes_root_aliases(self):
        """
        Ensure row_scope=order binds both order and self aliases at root.
        """
        path, table = resolve_row_scope(Sample, "order")
        self.assertEqual(path_to_string(path), "")
        self.assertIn("order", table)
        self.assertIn("self", table)

    def test_resolve_row_scope_shortname_unique_path(self):
        """
        Ensure a unique shortname resolves to its canonical iterative path.
        """
        path, table = resolve_row_scope(UniqueRoot, "point")
        self.assertEqual(path_to_string(path), "points[*]")
        self.assertIn("point", table)
        self.assertIn("self", table)

    def test_resolve_row_scope_ambiguous_shortname_raises(self):
        """
        Ensure overlapping shortname candidates raise AmbiguousRowScope.
        """
        with self.assertRaises(AmbiguousRowScope):
            resolve_row_scope(Sample, "point")

    def test_resolve_row_scope_unknown_shortname_raises(self):
        """
        Ensure unknown shortname inputs raise UnknownRowScope.
        """
        with self.assertRaises(UnknownRowScope):
            resolve_row_scope(Sample, "missing")

    def test_resolve_row_scope_rejects_leaf_terminal_path(self):
        """
        Ensure explicit row_scope paths ending in leaf fields are rejected.
        """
        with self.assertRaises(InvalidRowScope):
            resolve_row_scope(Sample, "points[index=1].index")

    def test_ambient_scope_table_alias_collision_raises(self):
        """
        Ensure adding a reused alias for a different path raises AliasCollision.
        """
        table = AmbientScopeTable()
        root_kind = DataclassField(name="order", dataclass_type=Sample, optional=False)
        table.add("order", Path(segments=tuple()), root_kind, terminal=False)
        with self.assertRaises(AliasCollision):
            table.add(
                "order",
                parse_path("point"),
                DataclassField(name="point", dataclass_type=Point, optional=False),
                terminal=True,
            )
