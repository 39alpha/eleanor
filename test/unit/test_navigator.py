from unittest import mock

from eleanor.navigator import AbstractNavigator, Lattice, LatticeNavigator, Random, RandomLattice
from eleanor.parameters import RangeParameter, ValueParameter

from .common import TestCase


class DummyNavigator(AbstractNavigator):
    def navigate(self, scale: int, *args, **kwargs):
        return [f"p{i}" for i in range(scale)]


class DummyLatticeNavigator(LatticeNavigator):
    def generate(self, parameter, scale: int, *args, **kwargs):
        return [f"v{i}" for i in range(scale)]


class TestNavigator(TestCase):
    """
    Tests of the eleanor.navigator module.
    """

    def test_abstract_navigator_default_helpers(self):
        """
        Ensure that :class:`AbstractNavigator` default helper methods behave as documented.
        """
        nav = DummyNavigator(order=mock.Mock(), kernel=mock.Mock())
        self.assertEqual(nav.num_systems(3), 3)
        self.assertEqual(nav.huffer_problem(), "p0")
        self.assertTrue(nav.supports_success_sampling())
        self.assertTrue(nav.is_complete([1, 2]))

    def test_abstract_placeholder_methods(self):
        """
        Ensure that abstract placeholder method bodies are executable when called directly.
        """
        self.assertIsNone(AbstractNavigator.navigate(object(), 1))
        self.assertIsNone(LatticeNavigator.generate(object(), object(), 1))

    def test_random_navigate_and_num_systems(self):
        """
        Ensure that :class:`Random` navigation delegates to generate per requested scale.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch.object(Random, "generate", side_effect=["a", "b", "c"]) as gen_mock:
            points = nav.navigate(3)

        self.assertEqual(points, ["a", "b", "c"])
        self.assertEqual(gen_mock.call_count, 3)
        self.assertEqual(nav.num_systems(7), 7)

    def test_random_generate_success(self):
        """
        Ensure that :meth:`Random.generate` applies constraints and returns generated points.
        """
        kernel = mock.Mock()

        class FakeParameter:
            def random(self):
                return ["chosen"]

        class FakeBoatswain:
            def __init__(self, order):
                self.order = order
                self.param = FakeParameter()
                self.values = {}
                self.calls = 0

            def constrain(self):
                self.calls += 1
                return ["p"] if self.calls == 1 else []

            def __getitem__(self, key):
                return self.param

            def __setitem__(self, key, value):
                self.values[key] = value

            def generate_vs(self, order_id):
                return {"order_id": order_id, "values": self.values}

        with mock.patch("eleanor.navigator.Boatswain", FakeBoatswain):
            nav = Random(order=mock.Mock(), kernel=kernel)
            point = nav.generate(order_id=11)

        kernel.constrain.assert_called_once()
        self.assertEqual(point["order_id"], 11)
        self.assertEqual(point["values"], {"p": "chosen"})

    def test_random_generate_wraps_errors(self):
        """
        Ensure that :meth:`Random.generate` wraps internal failures with a stable message.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch("eleanor.navigator.Boatswain", side_effect=RuntimeError("boom")):
            with self.assertRaises(Exception) as cm:
                nav.generate()
        self.assertIn("failed to select VS point", str(cm.exception))

    def test_lattice_navigate_iterate_and_num_systems(self):
        """
        Ensure that :class:`LatticeNavigator` traverses generated values and computes system count.
        """
        kernel = mock.Mock()

        class FakeBoatswain:
            def __init__(self, order):
                self.values = {}
                self.hardset_calls = []

            def constrain(self):
                return ["p"] if "p" not in self.values else []

            def __getitem__(self, key):
                return "seed"

            def __setitem__(self, key, value):
                self.values[key] = value

            def hardset(self, key, value):
                self.hardset_calls.append((key, value))
                self.values.pop(key, None)

            def generate_vs(self, order_id):
                return {"value": self.values.get("p"), "order_id": order_id}

        nav = DummyLatticeNavigator(order=mock.Mock(), kernel=kernel)
        with mock.patch("eleanor.navigator.Boatswain", FakeBoatswain):
            points = nav.navigate(2, order_id=5)

        kernel.constrain.assert_called_once()
        self.assertEqual(points, [{"value": "v0", "order_id": 5}, {"value": "v1", "order_id": 5}])

        order = mock.Mock()
        order.parameters.return_value = [
            ValueParameter("a", None, 1),
            RangeParameter("b", None, 0, 1),
        ]
        nav2 = DummyLatticeNavigator(order=order, kernel=mock.Mock())
        self.assertEqual(nav2.num_systems(3), 3)

    def test_lattice_iterate_handles_generation_errors(self):
        """
        Ensure that :meth:`LatticeNavigator.iterate` suppresses generation errors and yields no points.
        """
        nav = DummyLatticeNavigator(order=mock.Mock(), kernel=mock.Mock())
        boatswain = mock.Mock()
        boatswain.constrain.return_value = ["p"]
        boatswain.__getitem__ = mock.Mock(return_value="seed")

        with mock.patch.object(DummyLatticeNavigator, "generate", side_effect=RuntimeError("bad")):
            points = list(nav.iterate(boatswain, [], 2))

        self.assertEqual(points, [])

    def test_random_lattice_and_lattice_generate(self):
        """
        Ensure RandomLattice and Lattice generation delegate to parameter helpers with validation.
        """
        param = mock.Mock()
        param.random.return_value = ["r1", "r2"]
        param.lattice.return_value = ["l1", "l2"]

        random_lattice = RandomLattice(order=mock.Mock(), kernel=mock.Mock())
        self.assertEqual(random_lattice.generate(param, 2), ["r1", "r2"])
        param.random.assert_called_once_with(size=2)

        lattice = Lattice(order=mock.Mock(), kernel=mock.Mock())
        self.assertEqual(lattice.generate(param, 2), ["l1", "l2"])
        param.lattice.assert_called_once_with(size=2)
        self.assertFalse(lattice.supports_success_sampling())

        with self.assertRaises(ValueError):
            lattice.generate(param, 0)
