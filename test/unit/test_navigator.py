from collections.abc import Iterator
from typing import cast, override
from unittest import mock

import numpy as np

import eleanor.variable_space as vs
from eleanor.exceptions import EleanorException
from eleanor.navigator import AbstractNavigator, Lattice, LatticeNavigator, Random, RandomLattice
from eleanor.parameters import Parameter, RangeParameter, ValueParameter

from .common import TestCase


class DummyNavigator(AbstractNavigator):
    @override
    def navigate(
        self,
        scale: int,
        batch_size: int,
        *args: object,
        **kwargs: object,
    ) -> Iterator[list[vs.Point]]:
        _ = args
        _ = kwargs
        points = [cast(vs.Point, cast(object, f"p{i}")) for i in range(scale)]
        for start in range(0, len(points), batch_size):
            yield points[start : start + batch_size]


class DummyLatticeNavigator(LatticeNavigator):
    @override
    def generate(
        self,
        parameter: Parameter,
        scale: int,
        *args: object,
        **kwargs: object,
    ) -> list[ValueParameter]:
        _ = parameter
        _ = args
        _ = kwargs
        return cast(list[ValueParameter], [f"v{i}" for i in range(scale)])


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

    def test_abstract_placeholder_methods(self):
        """
        Ensure that abstract placeholder method bodies are executable when called directly.
        """
        abstract_navigator = cast(AbstractNavigator, object())
        lattice_navigator = cast(LatticeNavigator, object())
        parameter = cast(Parameter, object())
        self.assertIsNone(AbstractNavigator.navigate(abstract_navigator, 1, 1))
        self.assertIsNone(LatticeNavigator.generate(lattice_navigator, parameter, 1))

    def test_random_navigate_and_num_systems(self):
        """
        Ensure that :class:`Random` navigation delegates to generate per requested scale.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch.object(Random, "generate", side_effect=["a", "b", "c"]) as gen_mock:
            batches = list(nav.navigate(3, 2))

        self.assertEqual(batches, [["a", "b"], ["c"]])
        self.assertEqual(gen_mock.call_count, 3)
        self.assertTrue(all(len(batch) <= 2 for batch in batches))
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

        with mock.patch("eleanor.navigator.random.Boatswain", FakeBoatswain):
            nav = Random(order=mock.Mock(), kernel=kernel)
            point = cast(dict[str, object], cast(object, nav.generate(order_id=11)))

        kernel.constrain.assert_called_once()
        self.assertEqual(point["order_id"], 11)
        self.assertEqual(point["values"], {"p": "chosen"})

    def test_random_generate_wraps_errors(self):
        """
        Ensure that :meth:`Random.generate` wraps internal failures with a stable message.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch("eleanor.navigator.random.Boatswain", side_effect=RuntimeError("boom")):
            with self.assertRaises(Exception) as cm:
                nav.generate()
        self.assertIn("failed to select VS point", str(cm.exception))

    def test_random_generate_default_max_attempts_does_not_retry(self):
        """
        Ensure that :meth:`Random.generate` makes exactly one attempt when no
        ``max_attempts`` is supplied. The default of 1 preserves the prior
        single-attempt behavior so existing callers see no change.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch(
            "eleanor.navigator.random.Boatswain",
            side_effect=RuntimeError("boom"),
        ) as boat_class_mock:
            with self.assertRaises(EleanorException):
                nav.generate()
        self.assertEqual(boat_class_mock.call_count, 1)

    def test_random_generate_retries_until_success(self):
        """
        Ensure that :meth:`Random.generate` retries on failure and returns
        the first successful point. After two failed Boatswain constructions
        the third attempt succeeds and its point is returned.
        """
        successful_boat = mock.Mock()
        successful_boat.constrain.return_value = []
        successful_boat.generate_vs.return_value = "the_point"

        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch(
            "eleanor.navigator.random.Boatswain",
            side_effect=[
                RuntimeError("attempt-1"),
                RuntimeError("attempt-2"),
                successful_boat,
            ],
        ) as boat_class_mock:
            point = nav.generate(max_attempts=3)

        self.assertEqual(point, "the_point")
        self.assertEqual(boat_class_mock.call_count, 3)
        successful_boat.generate_vs.assert_called_once()

    def test_random_generate_stops_retrying_once_attempt_succeeds(self):
        """
        Ensure that :meth:`Random.generate` does not consume retries past the
        first success. With ``max_attempts=5`` and a successful first attempt,
        Boatswain is constructed exactly once.
        """
        successful_boat = mock.Mock()
        successful_boat.constrain.return_value = []
        successful_boat.generate_vs.return_value = "the_point"

        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch(
            "eleanor.navigator.random.Boatswain",
            return_value=successful_boat,
        ) as boat_class_mock:
            point = nav.generate(max_attempts=5)

        self.assertEqual(point, "the_point")
        self.assertEqual(boat_class_mock.call_count, 1)

    def test_random_generate_retry_exhaustion_chains_last_cause(self):
        """
        Ensure that when every attempt fails, :meth:`Random.generate` raises
        :class:`EleanorException` whose ``__cause__`` is the *last* underlying
        failure. The retry loop exhausts ``max_attempts`` and then propagates
        the most recent exception as the cause.
        """
        first = RuntimeError("first")
        second = RuntimeError("second")
        last = RuntimeError("last")
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch(
            "eleanor.navigator.random.Boatswain",
            side_effect=[first, second, last],
        ) as boat_class_mock:
            with self.assertRaises(EleanorException) as cm:
                nav.generate(max_attempts=3)

        self.assertIn("failed to select VS point", str(cm.exception))
        self.assertIs(cm.exception.__cause__, last)
        self.assertEqual(boat_class_mock.call_count, 3)

    def test_random_generate_rejects_non_int_max_attempts(self):
        """
        Ensure that :meth:`Random.generate` rejects a non-integer
        ``max_attempts`` with :class:`EleanorException` before any work is
        done.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch("eleanor.navigator.random.Boatswain") as boat_class_mock:
            with self.assertRaisesRegex(EleanorException, "max_attempts must be an integer"):
                nav.generate(max_attempts="3")
        boat_class_mock.assert_not_called()

    def test_random_generate_rejects_bool_max_attempts(self):
        """
        Ensure that :meth:`Random.generate` rejects a ``bool`` ``max_attempts``.
        ``bool`` is a subclass of ``int`` in Python, so ``True``/``False``
        would otherwise silently coerce to 1/0; the guard rejects them so
        misuse surfaces as an error rather than as a silent zero-attempt run.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with self.assertRaisesRegex(EleanorException, "max_attempts must be an integer"):
            nav.generate(max_attempts=True)

    def test_random_generate_rejects_zero_max_attempts(self):
        """
        Ensure that :meth:`Random.generate` rejects ``max_attempts=0`` with
        :class:`EleanorException` rather than silently raising the generic
        "failed to select VS point" wrapper without ever attempting a point.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch("eleanor.navigator.random.Boatswain") as boat_class_mock:
            with self.assertRaisesRegex(EleanorException, "max_attempts must be at least one"):
                nav.generate(max_attempts=0)
        boat_class_mock.assert_not_called()

    def test_random_generate_rejects_negative_max_attempts(self):
        """
        Ensure that :meth:`Random.generate` rejects a negative ``max_attempts``.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with self.assertRaisesRegex(EleanorException, "max_attempts must be at least one"):
            nav.generate(max_attempts=-1)

    def test_random_navigate_threads_max_attempts_to_generate(self):
        """
        Ensure that :meth:`Random.navigate` forwards ``max_attempts`` from its
        kwargs to every :meth:`Random.generate` call. This is the wiring on
        which :meth:`Eleanor.process` relies when it passes
        ``max_attempts=max_nav_attempts`` to ``navigator.navigate``.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch.object(Random, "generate", return_value="point") as gen_mock:
            _ = list(nav.navigate(3, 2, max_attempts=5))

        self.assertEqual(gen_mock.call_count, 3)
        for call in gen_mock.call_args_list:
            self.assertEqual(call.kwargs.get("max_attempts"), 5)

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
        with mock.patch("eleanor.navigator.lattice.Boatswain", FakeBoatswain):
            batches = list(nav.navigate(2, 1, order_id=5))
        points = [point for batch in batches for point in batch]

        kernel.constrain.assert_called_once()
        self.assertEqual(points, [{"value": "v0", "order_id": 5}, {"value": "v1", "order_id": 5}])
        self.assertEqual([len(batch) for batch in batches], [1, 1])

        order = mock.Mock()
        order.parameters.return_value = [
            ValueParameter("a", None, np.float64(1)),
            RangeParameter("b", None, np.float64(0), np.float64(1)),
        ]
        nav2 = DummyLatticeNavigator(order=order, kernel=mock.Mock())
        self.assertEqual(nav2.num_systems(3), 3)

    def test_lattice_iterate_handles_generation_errors(self):
        """
        Ensure that :meth:`LatticeNavigator.iterate` surfaces generation errors.
        """
        nav = DummyLatticeNavigator(order=mock.Mock(), kernel=mock.Mock())
        boatswain = mock.Mock()
        boatswain.constrain.return_value = ["p"]
        boatswain.__getitem__ = mock.Mock(return_value="seed")

        with mock.patch.object(DummyLatticeNavigator, "generate", side_effect=RuntimeError("bad")):
            with self.assertRaisesRegex(RuntimeError, "bad"):
                _ = list(nav.iterate(boatswain, [], 2))

    def test_random_navigate_respects_batch_size(self):
        """
        Ensure Random.navigate partitions output into max-size batches.
        """
        nav = Random(order=mock.Mock(), kernel=mock.Mock())
        with mock.patch.object(Random, "generate", side_effect=[f"p{i}" for i in range(10)]):
            batches = list(nav.navigate(10, 3))

        self.assertEqual([len(batch) for batch in batches], [3, 3, 3, 1])

    def test_lattice_navigate_respects_batch_size(self):
        """
        Ensure LatticeNavigator.navigate partitions iterator output by batch_size.
        """
        nav = DummyLatticeNavigator(order=mock.Mock(), kernel=mock.Mock())
        with (
            mock.patch("eleanor.navigator.lattice.Boatswain", return_value=mock.Mock()),
            mock.patch.object(
                DummyLatticeNavigator,
                "iterate",
                return_value=iter([f"p{i}" for i in range(9)]),
            ),
        ):
            batches = list(nav.navigate(3, 4))

        self.assertEqual([len(batch) for batch in batches], [4, 4, 1])

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

        with self.assertRaises(ValueError):
            lattice.generate(param, 0)
