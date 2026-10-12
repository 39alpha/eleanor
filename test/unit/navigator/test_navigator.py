from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import cast, final, override
from unittest import TestCase, mock

import eleanor.variable_space as vs
import numpy as np
import pytest
from eleanor.exceptions import EleanorError
from eleanor.kernel import AbstractKernel
from eleanor.navigator import AbstractNavigator, SampleDensity, SimulationSize, SystemCount
from eleanor.navigator.lattice import (
    AbstractLatticeNavigator,
    LatticeNavigator,
    RandomLatticeNavigator,
)
from eleanor.navigator.random import RandomNavigator
from eleanor.order import Order
from eleanor.parameters import Parameter, RangeParameter, ValueParameter


class DummyNavigator(AbstractNavigator):
    @override
    def navigate(
        self,
        order: Order,
        kernel: AbstractKernel,
        simulation_size: SimulationSize,
        batch_size: int,
        *args: object,
        **kwargs: object,
    ) -> Iterator[list[vs.Point]]:
        _ = args
        _ = kwargs
        points = [cast(vs.Point, cast(object, f"p{i}")) for i in range(simulation_size.num_systems(order))]
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

    def test_abstract_navigator_default_helpers(self) -> None:
        """
        Ensure that :class:`AbstractNavigator` default helper methods behave as documented.
        """
        nav = DummyNavigator()
        self.assertEqual(nav.num_systems(mock.Mock(), SystemCount(3)), 3)

    def test_abstract_placeholder_methods(self) -> None:
        """
        Ensure that abstract placeholder method bodies are executable when called directly.
        """
        abstract_navigator = cast(AbstractNavigator, object())
        lattice_navigator = cast(AbstractLatticeNavigator, object())
        parameter = cast(Parameter, object())
        self.assertIsNone(AbstractNavigator.navigate(abstract_navigator, mock.Mock(), mock.Mock(), SystemCount(1), 1))
        self.assertIsNone(AbstractLatticeNavigator.generate(lattice_navigator, parameter, 1, rng=None))

    def test_random_navigate_and_num_systems(self) -> None:
        """
        Ensure that :class:`RandomNavigator` navigation delegates to generate per requested scale.
        """
        nav = RandomNavigator()
        with mock.patch.object(RandomNavigator, "generate", side_effect=["a", "b", "c"]) as gen_mock:
            batches = list(nav.navigate(mock.Mock(), mock.Mock(), SystemCount(3), 2))

        self.assertEqual(batches, [["a", "b"], ["c"]])
        self.assertEqual(gen_mock.call_count, 3)
        self.assertTrue(all(len(batch) <= 2 for batch in batches))
        self.assertEqual(nav.num_systems(mock.Mock(), SystemCount(7)), 7)

    def test_random_generate_success(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` applies constraints and returns generated points.
        """
        kernel = mock.Mock()

        class FakeParameter:
            def random(self, rng=None):
                return ["chosen"]

        @final
        class FakePointBuilder:
            def __init__(self, order) -> None:
                self.order = order
                self.param = FakeParameter()
                self.values = {}
                self.calls = 0

            def constrain(self):
                self.calls += 1
                return ["p"] if self.calls == 1 else []

            def __getitem__(self, key):
                return self.param

            def __setitem__(self, key, value) -> None:
                self.values[key] = value

            def generate_vs(self):
                return {"values": self.values}

        with mock.patch("eleanor.navigator.random.PointBuilder", FakePointBuilder):
            nav = RandomNavigator()
            point = cast(
                dict[str, object],
                cast(object, nav.generate(mock.Mock(), kernel)),
            )

        kernel.constrain.assert_called_once()
        self.assertEqual(point["values"], {"p": "chosen"})

    def test_random_generate_wraps_errors(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` wraps internal failures with a stable message.
        """
        nav = RandomNavigator()
        with mock.patch("eleanor.navigator.random.PointBuilder", side_effect=RuntimeError("boom")):
            with self.assertRaises(Exception) as cm:
                _ = nav.generate(mock.Mock(), mock.Mock())
        self.assertIn("failed to select VS point", str(cm.exception))

    def test_random_generate_default_max_attempts_does_not_retry(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` makes exactly one attempt when no
        ``max_attempts`` is supplied. The default of 1 preserves the prior
        single-attempt behavior so existing callers see no change.
        """
        nav = RandomNavigator()
        with mock.patch(
            "eleanor.navigator.random.PointBuilder",
            side_effect=RuntimeError("boom"),
        ) as boat_class_mock:
            with self.assertRaises(EleanorError):
                _ = nav.generate(mock.Mock(), mock.Mock())
        self.assertEqual(boat_class_mock.call_count, 1)

    def test_random_generate_retries_until_success(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` retries on failure and returns
        the first successful point. After two failed PointBuilder constructions
        the third attempt succeeds and its point is returned.
        """
        successful_boat = mock.Mock()
        successful_boat.constrain.return_value = []
        successful_boat.generate_vs.return_value = "the_point"

        nav = RandomNavigator()
        with mock.patch(
            "eleanor.navigator.random.PointBuilder",
            side_effect=[
                RuntimeError("attempt-1"),
                RuntimeError("attempt-2"),
                successful_boat,
            ],
        ) as boat_class_mock:
            point = nav.generate(mock.Mock(), mock.Mock(), max_attempts=3)

        self.assertEqual(point, "the_point")
        self.assertEqual(boat_class_mock.call_count, 3)
        successful_boat.generate_vs.assert_called_once()

    def test_random_generate_stops_retrying_once_attempt_succeeds(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` does not consume retries past the
        first success. With ``max_attempts=5`` and a successful first attempt,
        PointBuilder is constructed exactly once.
        """
        successful_boat = mock.Mock()
        successful_boat.constrain.return_value = []
        successful_boat.generate_vs.return_value = "the_point"

        nav = RandomNavigator()
        with mock.patch(
            "eleanor.navigator.random.PointBuilder",
            return_value=successful_boat,
        ) as boat_class_mock:
            point = nav.generate(mock.Mock(), mock.Mock(), max_attempts=5)

        self.assertEqual(point, "the_point")
        self.assertEqual(boat_class_mock.call_count, 1)

    def test_random_generate_retry_exhaustion_chains_last_cause(self) -> None:
        """
        Ensure that when every attempt fails, :meth:`RandomNavigator.generate` raises
        :class:`EleanorError` whose ``__cause__`` is the *last* underlying
        failure. The retry loop exhausts ``max_attempts`` and then propagates
        the most recent exception as the cause.
        """
        first = RuntimeError("first")
        second = RuntimeError("second")
        last = RuntimeError("last")
        nav = RandomNavigator()
        with mock.patch(
            "eleanor.navigator.random.PointBuilder",
            side_effect=[first, second, last],
        ) as boat_class_mock:
            with self.assertRaises(EleanorError) as cm:
                _ = nav.generate(mock.Mock(), mock.Mock(), max_attempts=3)

        self.assertIn("failed to select VS point", str(cm.exception))
        self.assertIs(cm.exception.__cause__, last)
        self.assertEqual(boat_class_mock.call_count, 3)

    def test_random_generate_rejects_non_int_max_attempts(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` rejects a non-integer
        ``max_attempts`` with :class:`EleanorError` before any work is
        done.
        """
        nav = RandomNavigator()
        with mock.patch("eleanor.navigator.random.PointBuilder") as boat_class_mock:
            with self.assertRaisesRegex(EleanorError, "max_attempts must be an integer"):
                _ = nav.generate(mock.Mock(), mock.Mock(), max_attempts="3")
        boat_class_mock.assert_not_called()

    def test_random_generate_rejects_bool_max_attempts(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` rejects a ``bool`` ``max_attempts``.
        ``bool`` is a subclass of ``int`` in Python, so ``True``/``False``
        would otherwise silently coerce to 1/0; the guard rejects them so
        misuse surfaces as an error rather than as a silent zero-attempt run.
        """
        nav = RandomNavigator()
        with self.assertRaisesRegex(EleanorError, "max_attempts must be an integer"):
            _ = nav.generate(mock.Mock(), mock.Mock(), max_attempts=True)

    def test_random_generate_rejects_zero_max_attempts(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` rejects ``max_attempts=0`` with
        :class:`EleanorError` rather than silently raising the generic
        "failed to select VS point" wrapper without ever attempting a point.
        """
        nav = RandomNavigator()
        with mock.patch("eleanor.navigator.random.PointBuilder") as boat_class_mock:
            with self.assertRaisesRegex(EleanorError, "max_attempts must be at least one"):
                _ = nav.generate(mock.Mock(), mock.Mock(), max_attempts=0)
        boat_class_mock.assert_not_called()

    def test_random_generate_rejects_negative_max_attempts(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.generate` rejects a negative ``max_attempts``.
        """
        nav = RandomNavigator()
        with self.assertRaisesRegex(EleanorError, "max_attempts must be at least one"):
            _ = nav.generate(mock.Mock(), mock.Mock(), max_attempts=-1)

    def test_random_navigate_threads_max_attempts_to_generate(self) -> None:
        """
        Ensure that :meth:`RandomNavigator.navigate` forwards ``max_attempts`` from its
        kwargs to every :meth:`RandomNavigator.generate` call. This is the wiring on
        which :meth:`Eleanor.process` relies when it passes
        ``max_attempts=max_nav_attempts`` to ``navigator.navigate``.
        """
        nav = RandomNavigator()
        with mock.patch.object(RandomNavigator, "generate", return_value="point") as gen_mock:
            _ = list(nav.navigate(mock.Mock(), mock.Mock(), SystemCount(3), 2, max_attempts=5))

        self.assertEqual(gen_mock.call_count, 3)
        for call in gen_mock.call_args_list:
            self.assertEqual(call.kwargs.get("max_attempts"), 5)

    def test_lattice_navigate_iterate_and_num_systems(self) -> None:
        """
        Ensure that :class:`LatticeNavigator` traverses generated values and computes system count.
        """
        kernel = mock.Mock()

        @final
        class FakePointBuilder:
            def __init__(self, order) -> None:
                self.values = {}
                self.hardset_calls = []

            def constrain(self):
                return ["p"] if "p" not in self.values else []

            def __getitem__(self, key):
                return "seed"

            def __setitem__(self, key, value) -> None:
                self.values[key] = value

            def hardset(self, key, value) -> None:
                self.hardset_calls.append((key, value))
                self.values.pop(key, None)

            def generate_vs(self):
                return {"value": self.values.get("p")}

        nav = DummyLatticeNavigator()
        with mock.patch("eleanor.navigator.lattice.PointBuilder", FakePointBuilder):
            batches = list(nav.navigate(mock.Mock(dimensions=mock.Mock(return_value=1)), kernel, SystemCount(2), 1))
        points = [point for batch in batches for point in batch]

        kernel.constrain.assert_called_once()
        self.assertEqual(points, [{"value": "v0"}, {"value": "v1"}])
        self.assertEqual([len(batch) for batch in batches], [1, 1])

        order = mock.Mock()
        order.parameters.return_value = [
            ValueParameter(np.float64(1)),
            RangeParameter(np.float64(0), np.float64(1)),
        ]
        order.dimensions.side_effect = lambda: Order.dimensions(order)
        nav2 = DummyLatticeNavigator()
        self.assertEqual(nav2.num_systems(order, SystemCount(3)), 3)

    def test_lattice_iterate_handles_generation_errors(self) -> None:
        """
        Ensure that :meth:`LatticeNavigator.iterate` surfaces generation errors.
        """
        nav = DummyLatticeNavigator()
        point_builder = mock.Mock()
        point_builder.constrain.return_value = ["p"]
        point_builder.__getitem__ = mock.Mock(return_value="seed")

        with mock.patch.object(DummyLatticeNavigator, "generate", side_effect=RuntimeError("bad")):
            with self.assertRaisesRegex(RuntimeError, "bad"):
                _ = list(nav.iterate(mock.Mock(), point_builder, [], 2))

    def test_random_navigate_respects_batch_size(self) -> None:
        """
        Ensure RandomNavigator.navigate partitions output into max-size batches.
        """
        nav = RandomNavigator()
        with mock.patch.object(RandomNavigator, "generate", side_effect=[f"p{i}" for i in range(10)]):
            batches = list(nav.navigate(mock.Mock(), mock.Mock(), SystemCount(10), 3))

        self.assertEqual([len(batch) for batch in batches], [3, 3, 3, 1])

    def test_lattice_navigate_respects_batch_size(self) -> None:
        """
        Ensure LatticeNavigator.navigate partitions iterator output by batch_size.
        """
        nav = DummyLatticeNavigator()
        with (
            mock.patch("eleanor.navigator.lattice.PointBuilder", return_value=mock.Mock()),
            mock.patch.object(
                DummyLatticeNavigator,
                "iterate",
                return_value=iter([f"p{i}" for i in range(9)]),
            ),
        ):
            batches = list(
                nav.navigate(mock.Mock(dimensions=mock.Mock(return_value=2)), mock.Mock(), SystemCount(9), 4)
            )

        self.assertEqual([len(batch) for batch in batches], [4, 4, 1])

    def test_random_lattice_and_lattice_generate(self) -> None:
        """
        Ensure RandomLatticeNavigator and LatticeNavigator generation delegate to parameter helpers with validation.
        """
        param = mock.Mock()
        param.random.return_value = ["r1", "r2"]
        param.lattice.return_value = ["l1", "l2"]

        random_lattice = RandomLatticeNavigator()
        self.assertEqual(random_lattice.generate(param, 2, rng=None), ["r1", "r2"])
        param.random.assert_called_once_with(size=2, rng=None)

        lattice = LatticeNavigator()
        self.assertEqual(lattice.generate(param, 2), ["l1", "l2"])
        param.lattice.assert_called_once_with(size=2)

        with self.assertRaises(EleanorError):
            _ = lattice.generate(param, 0)


class TestSimulationSize(TestCase):
    """
    Tests of the :class:`SimulationSize` implementations.
    """

    def test_system_count_rejects_non_positive_counts(self) -> None:
        """
        Ensure that :class:`SystemCount` rejects zero and negative counts.
        """
        for count in (0, -1):
            with self.subTest(count=count), self.assertRaisesRegex(EleanorError, "count must be positive, non-zero"):
                _ = SystemCount(count)

    def test_sample_density_rejects_non_positive_densities(self) -> None:
        """
        Ensure that :class:`SampleDensity` rejects zero and negative densities.
        """
        for density in (0.0, -0.5):
            with (
                self.subTest(density=density),
                self.assertRaisesRegex(EleanorError, "density must be positive, non-zero"),
            ):
                _ = SampleDensity(density)

    def test_sample_density_rejects_non_finite_densities(self) -> None:
        """
        Ensure that :class:`SampleDensity` rejects NaN and infinite densities.
        """
        for density in (float("nan"), float("inf")):
            with self.subTest(density=density), self.assertRaisesRegex(EleanorError, "density must be finite"):
                _ = SampleDensity(density)


def _order(*, dimensions: int = 1, volume: float = 1.0) -> Order:
    """Produce an order-like stand-in exposing only ``dimensions``, ``volume`` and ``rng``."""
    return cast(Order, SimpleNamespace(dimensions=lambda: dimensions, volume=lambda: np.float64(volume), rng=None))


@pytest.mark.parametrize("count", [1, 2, 17, 1_000_000])
def test_system_count_num_systems_is_the_count(count: int) -> None:
    assert SystemCount(count).num_systems(_order(volume=3.0)) == count


@pytest.mark.parametrize(
    ("density", "volume", "expected"),
    [
        (0.25, 200.0, 50),
        (2.0, 3.0, 6),
        (1, 7.0, 7),
        (0.37, 10.0, 4),
        (0.34, 10.0, 3),
        (0.01, 10.0, 1),
        (5.0, 0.0, 1),
        (1e-9, 1.0, 1),
    ],
)
def test_sample_density_num_systems(density: float, volume: float, expected: int) -> None:
    num_systems = SampleDensity(density).num_systems(_order(volume=volume))
    assert num_systems == expected
    assert isinstance(num_systems, int)


@pytest.mark.parametrize("count", [True, 1.0, "3", None])
def test_system_count_rejects_non_integers(count: object) -> None:
    with pytest.raises(EleanorError, match="count must be an integer"):
        _ = SystemCount(cast(int, count))


@pytest.mark.parametrize("density", [True, "0.5", None])
def test_sample_density_rejects_non_numbers(density: object) -> None:
    with pytest.raises(EleanorError, match="density must be a floating-point number"):
        _ = SampleDensity(cast(float, density))


@pytest.mark.parametrize(
    ("size", "field", "value"),
    [(SystemCount(3), "count", 4), (SampleDensity(0.5), "density", 1.0)],
)
def test_simulation_sizes_are_frozen(size: SimulationSize, field: str, value: object) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(size, field, value)


@pytest.mark.parametrize(
    ("simulation_size", "volume", "expected"),
    [(SystemCount(7), 100.0, 7), (SampleDensity(0.5), 100.0, 50)],
)
def test_abstract_navigator_num_systems_delegates_to_simulation_size(
    simulation_size: SimulationSize, volume: float, expected: int
) -> None:
    assert DummyNavigator().num_systems(_order(volume=volume), simulation_size) == expected


@pytest.mark.parametrize(
    ("simulation_size", "volume", "expected"),
    [(SystemCount(5), 1.0, 5), (SampleDensity(0.5), 8.0, 4)],
)
def test_random_navigate_generates_the_requested_number_of_points(
    simulation_size: SimulationSize, volume: float, expected: int
) -> None:
    nav = RandomNavigator()
    with mock.patch.object(RandomNavigator, "generate", return_value="point") as gen_mock:
        batches = list(nav.navigate(_order(volume=volume), mock.Mock(), simulation_size, 3))

    assert sum(len(batch) for batch in batches) == expected
    assert gen_mock.call_count == expected


LATTICE_SIZES = [
    # (count, dimensions, scale, num_systems)
    (1, 1, 1, 1),
    (10, 1, 10, 10),
    (3, 2, 2, 4),
    (9, 2, 3, 9),
    (10, 2, 3, 9),
    (12, 2, 3, 9),
    (13, 2, 4, 16),
    (2, 3, 1, 1),
    (64, 3, 4, 64),
    (100, 3, 5, 125),
    (1000, 3, 10, 1000),
    (1_000_000, 6, 10, 1_000_000),
    (1, 0, 1, 1),
    (5, 0, 1, 1),
]


@pytest.mark.parametrize(("count", "dimensions", "scale", "num_systems"), LATTICE_SIZES)
def test_lattice_scale_and_num_systems(count: int, dimensions: int, scale: int, num_systems: int) -> None:
    order = _order(dimensions=dimensions)
    nav = DummyLatticeNavigator()

    assert nav.scale(order, SystemCount(count)) == scale
    assert nav.num_systems(order, SystemCount(count)) == num_systems


@pytest.mark.parametrize("dimensions", [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize("scale", [2, 3, 7, 10, 13, 20])
def test_lattice_scale_inverts_perfect_powers(scale: int, dimensions: int) -> None:
    order = _order(dimensions=dimensions)
    nav = DummyLatticeNavigator()

    assert nav.scale(order, SystemCount(scale**dimensions)) == scale
    assert nav.num_systems(order, SystemCount(scale**dimensions)) == scale**dimensions


@pytest.mark.parametrize(
    ("density", "volume", "dimensions", "scale", "num_systems"),
    [
        (0.5, 50.0, 2, 5, 25),
        (1.0, 10.0, 2, 3, 9),
        (2.0, 500.0, 3, 10, 1000),
    ],
)
def test_lattice_scale_and_num_systems_from_density(
    density: float, volume: float, dimensions: int, scale: int, num_systems: int
) -> None:
    order = _order(dimensions=dimensions, volume=volume)
    nav = DummyLatticeNavigator()

    assert nav.scale(order, SampleDensity(density)) == scale
    assert nav.num_systems(order, SampleDensity(density)) == num_systems


MAX_NAVIGATED_SYSTEMS = 1000


@pytest.mark.parametrize(
    ("count", "dimensions", "scale", "num_systems"),
    [row for row in LATTICE_SIZES if row[3] <= MAX_NAVIGATED_SYSTEMS],
)
def test_lattice_navigate_produces_num_systems_points(
    count: int, dimensions: int, scale: int, num_systems: int
) -> None:
    names = [f"p{i}" for i in range(dimensions)]

    @final
    class FakePointBuilder:
        def __init__(self, order) -> None:
            self.values = {}

        def constrain(self):
            return [name for name in names if name not in self.values]

        def __getitem__(self, key):
            return key

        def __setitem__(self, key, value) -> None:
            self.values[key] = value

        def hardset(self, key, value) -> None:
            self.values.pop(key, None)

        def generate_vs(self):
            return dict(self.values)

    order = _order(dimensions=dimensions)
    nav = DummyLatticeNavigator()
    with mock.patch("eleanor.navigator.lattice.PointBuilder", FakePointBuilder):
        points = [point for batch in nav.navigate(order, mock.Mock(), SystemCount(count), 4) for point in batch]

    assert len(points) == num_systems
    assert len(points) == nav.num_systems(order, SystemCount(count))
    for name in names:
        assert {point[name] for point in points} == {f"v{i}" for i in range(scale)}
