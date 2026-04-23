"""Tests for :meth:`eleanor.order.Order.iter_leaves` and :class:`LeafPlan`.

The helpers in this module build orders directly from raw dicts so the
tree-walk invariants are exercised end-to-end: once the test produces an
``Order``, the iterator walks via the real :meth:`Order.split_suborders`
and :meth:`Order.volume` implementations.
"""

from typing import Any
from unittest import mock

from eleanor.order import LeafPlan, Order

from .common import TestCase


def _order_dict(name: str, creator: str = "u", **extras: Any) -> dict[str, Any]:
    """Helper to produce a minimal-but-complete raw order dict."""
    base: dict[str, Any] = {"name": name, "creator": creator}
    base.update(extras)
    return base


class TestOrderIterLeaves(TestCase):
    """
    Tests of ``Order.iter_leaves`` across the tree shapes that
    :class:`Eleanor.run` relies on.
    """

    def test_leaf_order_yields_single_plan(self):
        """
        Ensure an order without suborders yields a single LeafPlan with
        ``sample_fraction == 1.0`` and ``umbrella is None``.
        """
        order = Order(_order_dict("leaf"))
        leaves = list(order.iter_leaves())

        self.assertEqual(len(leaves), 1)
        (plan,) = leaves
        self.assertIsInstance(plan, LeafPlan)
        self.assertIs(plan.order, order)
        self.assertEqual(plan.sample_fraction, 1.0)
        self.assertIsNone(plan.umbrella)

    def test_singly_nested_without_flags_yields_children_standalone(self):
        """
        Ensure a single level of suborders yields one plan per child, each
        with ``umbrella is None`` when the ``combined`` flag is not set.
        """
        raw = _order_dict(
            "root",
            suborders=[
                _order_dict("child-a"),
                _order_dict("child-b"),
            ],
        )
        order = Order(raw)
        leaves = list(order.iter_leaves())

        self.assertEqual(len(leaves), 2)
        self.assertEqual([leaf.order.name for leaf in leaves], ["child-a", "child-b"])
        for leaf in leaves:
            self.assertEqual(leaf.sample_fraction, 1.0)
            self.assertIsNone(leaf.umbrella)

    def test_combined_flag_records_root_umbrella(self):
        """
        Ensure combined=True on the caller sets ``umbrella`` to the root
        order on every yielded leaf.
        """
        raw = _order_dict(
            "root",
            suborders=[_order_dict("child-a"), _order_dict("child-b")],
        )
        order = Order(raw)
        leaves = list(order.iter_leaves(combined=True))

        self.assertEqual(len(leaves), 2)
        for leaf in leaves:
            self.assertIs(leaf.umbrella, order)

    def test_suborders_combined_field_flips_umbrella_at_that_level(self):
        """
        Ensure ``suborders.combined=True`` at an intermediate node makes
        the umbrella the intermediate node itself (not the root, since
        the root's own ``suborders.combined`` is unset).
        """
        raw = _order_dict(
            "root",
            suborders={
                "combined": False,
                "orders": [
                    _order_dict(
                        "middle",
                        suborders={
                            "combined": True,
                            "orders": [
                                _order_dict("grand-a"),
                                _order_dict("grand-b"),
                            ],
                        },
                    ),
                    _order_dict("solo"),
                ],
            },
        )
        order = Order(raw)
        leaves = list(order.iter_leaves())

        # Three leaves total: grand-a, grand-b, solo.
        names = [leaf.order.name for leaf in leaves]
        self.assertEqual(sorted(names), ["grand-a", "grand-b", "solo"])

        grand_leaves = [leaf for leaf in leaves if leaf.order.name.startswith("grand")]
        self.assertEqual(len(grand_leaves), 2)
        self.assertIs(grand_leaves[0].umbrella, grand_leaves[1].umbrella)
        self.assertEqual(grand_leaves[0].umbrella.name, "middle")

        (solo,) = [leaf for leaf in leaves if leaf.order.name == "solo"]
        self.assertIsNone(solo.umbrella)

    def test_combined_is_sticky_on_across_descendants(self):
        """
        Ensure once ``combined`` is True at some ancestor, every leaf in
        that ancestor's subtree reports the same ancestor as umbrella,
        even if a deeper suborders block does not set combined.
        """
        raw = _order_dict(
            "root",
            suborders={
                "combined": True,
                "orders": [
                    _order_dict(
                        "middle",
                        suborders=[_order_dict("grand-a"), _order_dict("grand-b")],
                    ),
                ],
            },
        )
        order = Order(raw)
        leaves = list(order.iter_leaves())

        self.assertEqual(len(leaves), 2)
        for leaf in leaves:
            self.assertIsNotNone(leaf.umbrella)
            self.assertEqual(leaf.umbrella.name, "root")

    def test_proportional_sampling_at_root_uses_root_volume(self):
        """
        Ensure proportional_sampling=True on the caller divides leaf
        volume by the root's volume.
        """
        # Use volume via temperature parameters so leaves differ.
        raw = _order_dict(
            "root",
            suborders={
                "proportional_sampling": True,
                "orders": [
                    _order_dict("a", temperature={"values": [1.0, 2.0]}),
                    _order_dict("b", temperature={"values": [3.0, 4.0, 5.0]}),
                ],
            },
        )
        order = Order(raw)
        leaves = list(order.iter_leaves())

        self.assertEqual(len(leaves), 2)
        total_volume = order.volume()
        for leaf in leaves:
            expected = leaf.order.volume() / total_volume
            self.assertAlmostEqual(leaf.sample_fraction, expected)
        # The fractions should sum to 1.0 (up to floating-point).
        self.assertAlmostEqual(sum(leaf.sample_fraction for leaf in leaves), 1.0)

    def test_proportional_flag_promoted_at_intermediate_node_uses_that_volume(self):
        """
        Ensure the denominator is the topmost ancestor at which the
        proportional flag first becomes True.
        """
        raw = _order_dict(
            "root",
            suborders={
                "orders": [
                    _order_dict(
                        "middle",
                        suborders={
                            "proportional_sampling": True,
                            "orders": [
                                _order_dict("a", temperature={"values": [1.0, 2.0]}),
                                _order_dict("b", temperature={"values": [3.0]}),
                            ],
                        },
                    ),
                    _order_dict("solo"),
                ],
            },
        )
        order = Order(raw)
        leaves = list(order.iter_leaves())

        # Find the 'middle' order as reconstructed by split_suborders so
        # we can compute the expected denominator.
        (mid_plan,) = [p for p in order.iter_leaves() if p.order.name == "a"]
        middle_order = None
        for top_child in order.split_suborders():
            if top_child.name == "middle":
                middle_order = top_child
                break
        self.assertIsNotNone(middle_order)
        middle_volume = middle_order.volume()

        a_plans = [p for p in leaves if p.order.name == "a"]
        b_plans = [p for p in leaves if p.order.name == "b"]
        solo_plans = [p for p in leaves if p.order.name == "solo"]

        self.assertEqual(len(a_plans), 1)
        self.assertEqual(len(b_plans), 1)
        self.assertEqual(len(solo_plans), 1)

        self.assertAlmostEqual(
            a_plans[0].sample_fraction,
            a_plans[0].order.volume() / middle_volume,
        )
        self.assertAlmostEqual(
            b_plans[0].sample_fraction,
            b_plans[0].order.volume() / middle_volume,
        )
        # The ``solo`` leaf is outside the proportional subtree.
        self.assertEqual(solo_plans[0].sample_fraction, 1.0)
        _ = mid_plan  # silence unused

    def test_empty_suborders_block_is_treated_as_leaf(self):
        """
        Ensure an order with a ``suborders`` block containing zero children
        is yielded as a single leaf.
        """
        raw = _order_dict("root", suborders=[])
        order = Order(raw)
        leaves = list(order.iter_leaves())

        self.assertEqual(len(leaves), 1)
        self.assertIs(leaves[0].order, order)

    def test_division_by_zero_denominator_yields_zero_fraction(self):
        """
        Ensure a leaf under a proportional root whose volume evaluates to
        zero produces a zero sample fraction rather than raising.
        """
        raw = _order_dict(
            "root",
            suborders={
                "proportional_sampling": True,
                "orders": [_order_dict("a"), _order_dict("b")],
            },
        )
        order = Order(raw)

        # Monkeypatch the root's volume to 0 for this test.
        with mock.patch.object(Order, "volume", return_value=0.0):
            leaves = list(order.iter_leaves())

        self.assertEqual(len(leaves), 2)
        for leaf in leaves:
            self.assertEqual(leaf.sample_fraction, 0.0)
