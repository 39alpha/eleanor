from typing import cast
from unittest import TestCase, mock

import numpy as np
from eleanor.exceptions import EleanorError
from eleanor.parameters import (
    POS_INF,
    ListParameter,
    NormalParameter,
    Parameter,
    ParameterRegistry,
    RangeParameter,
    ValueParameter,
    parameter_space_volume,
)


class TestParameters(TestCase):
    """
    Tests of the eleanor.parameters module.
    """

    def test_parameter_abstract_placeholders(self) -> None:
        """Abstract placeholder bodies are executable directly."""
        placeholder = cast(Parameter, object())
        self.assertFalse(Parameter.in_domain(placeholder, cast(Parameter, cast(object, None))))
        self.assertEqual(Parameter.range(placeholder), (np.float64(0), np.float64(0)))
        self.assertEqual(Parameter.volume(placeholder), np.float64(0.0))
        self.assertIsNone(Parameter.random(placeholder))
        self.assertIsNone(Parameter.lattice(placeholder))

    def test_parameter_space_volume(self) -> None:
        """Fixed parameters drop out, the rest multiply, and a space with nothing free has no volume."""
        fixed = ValueParameter(np.float64(1.0))
        wide = RangeParameter(np.float64(0.0), np.float64(10.0))
        pair = ListParameter([np.float64(1.0), np.float64(2.0)])

        self.assertEqual(parameter_space_volume([]), np.float64(0.0))
        self.assertEqual(parameter_space_volume([fixed, ValueParameter(np.float64(2.0))]), np.float64(0.0))
        self.assertEqual(parameter_space_volume([wide]), np.float64(10.0))
        self.assertEqual(parameter_space_volume([fixed, wide]), np.float64(10.0))
        self.assertEqual(parameter_space_volume([wide, pair]), np.float64(20.0))

    def test_parameter_space_volume_accepts_an_iterator(self) -> None:
        """The parameters argument is only consumed once, so an iterator works."""
        params = iter([RangeParameter(np.float64(0.0), np.float64(3.0)), ValueParameter(np.float64(1.0))])
        self.assertEqual(parameter_space_volume(params), np.float64(3.0))

    def test_parameter_from_dict_and_load_dispatch(self) -> None:
        """
        Ensure parameter parsing/load dispatch covers value/list/range/normal forms.
        """
        p0 = Parameter.from_dict({"value": 2})
        self.assertIsInstance(p0, ValueParameter)
        self.assertEqual(cast(ValueParameter, p0).value, 2)

        p1 = Parameter.from_dict({"values": [3, 1, 2]})
        self.assertIsInstance(p1, ListParameter)
        self.assertEqual(cast(ListParameter, p1).values, [1, 2, 3])

        p2 = Parameter.from_dict({"min": 5, "max": 2})
        self.assertIsInstance(p2, RangeParameter)
        p2_range = cast(RangeParameter, p2)
        self.assertEqual((p2_range.min, p2_range.max), (2, 5))

        p3 = Parameter.from_dict({"mean": 0.0, "stddev": 2.0})
        self.assertIsInstance(p3, NormalParameter)
        self.assertEqual(cast(NormalParameter, p3).stddev, 2.0)

        self.assertIsInstance(Parameter.load({"value": 1.0}), ValueParameter)
        self.assertIsInstance(Parameter.load([1.0, 2.0]), ListParameter)
        self.assertIsInstance(Parameter.load(1.0), ValueParameter)

    def test_parameter_refine_and_restrict(self) -> None:
        """
        Ensure refine/restrict/fix collapse degenerate list/range parameters to value parameters.
        """
        p = RangeParameter(np.float64(1.0), np.float64(1.0))
        self.assertIsInstance(Parameter.refine(p), ValueParameter)
        p = ListParameter([np.float64(2.0), np.float64(2.0)])
        self.assertIsInstance(Parameter.refine(p), ValueParameter)
        p = RangeParameter(np.float64(0.0), np.float64(2.0))
        fixed = p.fix(np.float64(1.0))
        self.assertIsInstance(fixed, ValueParameter)
        self.assertEqual(cast(ValueParameter, fixed).value, np.float64(1.0))

    def test_parameter_refine_collapses_degenerate_normal(self) -> None:
        """A normal with no spread, or with equal bounds, refines to a fixed parameter."""
        cases = [
            # Equal bounds pin the value, whatever the mean, and win over the stddev branch.
            ({"mean": 5.0, "min": 5.0, "max": 5.0}, np.float64(5.0)),
            # A zero stddev collapses to the mean, clamped into the bounds when it falls outside.
            ({"mean": 5.0, "stddev": 0.0}, np.float64(5.0)),
            ({"mean": 2.0, "min": 0.0, "max": 10.0, "stddev": 0.0}, np.float64(2.0)),
            ({"mean": 100.0, "min": 0.0, "max": 10.0, "stddev": 0.0}, np.float64(10.0)),
            ({"mean": -100.0, "min": 0.0, "max": 10.0, "stddev": 0.0}, np.float64(0.0)),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                parameter = Parameter.from_dict(raw)
                self.assertIsInstance(parameter, ValueParameter)
                self.assertEqual(cast(ValueParameter, parameter).value, expected)

        pinned = Parameter.refine(
            NormalParameter(mean=np.float64(50.0), stddev=np.float64(10.0), a=np.float64(100.0), b=np.float64(100.0))
        )
        self.assertIsInstance(pinned, ValueParameter)
        self.assertEqual(cast(ValueParameter, pinned).value, np.float64(100.0))

        for raw in ({"mean": 25.0, "stddev": 1.0}, {"mean": 25.0, "min": 20.0, "max": 30.0}):
            with self.subTest(raw=raw):
                self.assertIsInstance(Parameter.from_dict(raw), NormalParameter)

    def test_value_parameter_methods(self) -> None:
        """Domain, range, volume, random and lattice of a fixed parameter."""
        p = ValueParameter(np.float64(2.0))
        self.assertTrue(p.in_domain(ValueParameter(np.float64(2.0))))
        self.assertFalse(p.in_domain(ValueParameter(np.float64(3.0))))
        self.assertFalse(p.in_domain(RangeParameter(np.float64(1.0), np.float64(2.0))))
        self.assertEqual(p.range(), (np.float64(2.0), np.float64(2.0)))
        self.assertEqual(p.volume(), np.float64(0.0))
        self.assertEqual([x.value for x in p.random(size=2)], [np.float64(2.0), np.float64(2.0)])
        self.assertEqual(
            [x.value for x in p.lattice(size=3)],
            [np.float64(2.0), np.float64(2.0), np.float64(2.0)],
        )

    def test_range_parameter_methods(self) -> None:
        """Ordering, domain checks, volume and generation helpers of a range."""
        p = RangeParameter(np.float64(3.0), np.float64(1.0))
        self.assertEqual((p.min, p.max), (np.float64(1.0), np.float64(3.0)))
        b0, b1 = p.bounds
        self.assertEqual((b0.value, b1.value), (np.float64(1.0), np.float64(3.0)))
        self.assertTrue(p.in_domain(ValueParameter(np.float64(2.0))))
        self.assertFalse(p.in_domain(ValueParameter(np.float64(4.0))))
        self.assertTrue(p.in_domain(RangeParameter(np.float64(1.5), np.float64(2.5))))
        self.assertTrue(p.in_domain(ListParameter([np.float64(1.0), np.float64(2.0), np.float64(3.0)])))
        self.assertFalse(p.in_domain(ListParameter([np.float64(0.0), np.float64(2.0)])))
        self.assertFalse(p.in_domain(cast(Parameter, object())))
        self.assertEqual(p.range(), (np.float64(1.0), np.float64(3.0)))
        self.assertEqual(p.volume(), np.float64(2.0))

        with mock.patch("scipy.stats.uniform.rvs", return_value=np.array([1.0, 2.0])):
            out = p.random(size=2)
        self.assertEqual([x.value for x in out], [np.float64(1.0), np.float64(2.0)])

        out2 = p.lattice(size=3)
        self.assertEqual([x.value for x in out2], [np.float64(1.0), np.float64(2.0), np.float64(3.0)])

    def test_list_parameter_methods(self) -> None:
        """Validation, domain checks, volume and generation helpers of a list."""
        with self.assertRaises(EleanorError):
            _ = ListParameter([])

        p = ListParameter([np.float64(3.0), np.float64(1.0), np.float64(2.0)])
        self.assertEqual(p.values, [np.float64(1.0), np.float64(2.0), np.float64(3.0)])
        self.assertEqual(
            [e.value for e in p.elements],
            [np.float64(1.0), np.float64(2.0), np.float64(3.0)],
        )
        self.assertTrue(p.in_domain(ValueParameter(np.float64(2.0))))
        self.assertFalse(p.in_domain(ValueParameter(np.float64(5.0))))
        self.assertTrue(p.in_domain(RangeParameter(np.float64(2.0), np.float64(2.0))))
        self.assertFalse(p.in_domain(RangeParameter(np.float64(1.0), np.float64(2.0))))
        self.assertTrue(p.in_domain(ListParameter([np.float64(1.0), np.float64(2.0)])))
        self.assertFalse(p.in_domain(ListParameter([np.float64(1.0), np.float64(4.0)])))
        self.assertFalse(p.in_domain(cast(Parameter, object())))
        self.assertEqual(p.range(), (np.float64(1.0), np.float64(3.0)))
        self.assertEqual(p.volume(), np.float64(3))

        with mock.patch("scipy.stats.randint.rvs", return_value=np.array([0, 2])):
            out = p.random(size=2)
        self.assertEqual([x.value for x in out], [np.float64(1.0), np.float64(3.0)])
        self.assertEqual(
            [x.value for x in p.lattice(size=5)],
            [
                np.float64(1.0),
                np.float64(2.0),
                np.float64(3.0),
                np.float64(1.0),
                np.float64(2.0),
            ],
        )

    def test_normal_parameter_defaults_and_generation(self) -> None:
        """Default stddev, random and lattice generation of a normal."""
        p0 = NormalParameter(mean=np.float64(0.0))
        self.assertEqual(p0.stddev, np.float64(1.0))
        self.assertEqual(p0.range(), (-np.inf, np.inf))

        p1 = NormalParameter(mean=np.float64(0.0), a=np.float64(-3.0), b=np.float64(3.0))
        self.assertEqual(p1.stddev, np.float64(1.0))
        self.assertEqual(p1.range(), (np.float64(-3.0), np.float64(3.0)))
        self.assertFalse(p1.in_domain(cast(Parameter, object())))

        with mock.patch("scipy.stats.norm.rvs", return_value=np.array([0.1, -0.2])):
            out0 = p0.random(size=2)
        self.assertEqual([round(x.value, 3) for x in out0], [0.1, -0.2])

        with mock.patch("scipy.stats.truncnorm.rvs", return_value=np.array([0.2, 0.3])):
            out1 = p1.random(size=2)
        self.assertEqual([round(x.value, 3) for x in out1], [0.2, 0.3])

        out2 = cast(list[object], p0.lattice(size=3))
        self.assertEqual(len(out2), 3)
        self.assertTrue(all(isinstance(v, ValueParameter) for v in out2))

        out3 = cast(list[object], p1.lattice(size=3))
        self.assertEqual(len(out3), 3)
        self.assertTrue(all(isinstance(v, ValueParameter) for v in out3))

    def test_normal_parameter_volume_reflects_bounds(self) -> None:
        """A normal parameter's volume is the six-sigma quantile interval of the distribution it samples."""
        unbounded = NormalParameter(mean=np.float64(0.0))
        self.assertEqual(unbounded.volume(), np.float64(6.0))

        bounded = NormalParameter(mean=np.float64(0.0), a=np.float64(-3.0), b=np.float64(3.0))
        self.assertAlmostEqual(float(bounded.volume()), 5.565227, places=6)

        half_bounded = NormalParameter(
            mean=np.float64(5.0),
            stddev=np.float64(2.0),
            a=np.float64(0.0),
            b=np.float64(np.inf),
        )
        self.assertAlmostEqual(float(half_bounded.volume()), 10.863624, places=6)

        # Truncation is negligible here, so a normal concentrated well inside wide bounds keeps its
        # six-sigma span rather than reporting the 50 units the bounds allow.
        concentrated = NormalParameter(
            mean=np.float64(25.0),
            stddev=np.float64(1.0),
            a=np.float64(0.0),
            b=np.float64(50.0),
        )
        self.assertAlmostEqual(float(concentrated.volume()), 6.0, places=6)

        # A mean outside the bounds is supported: the dimension is still sampleable, so its volume
        # is small but non-zero.
        outside_bounds = NormalParameter(
            mean=np.float64(100.0),
            stddev=np.float64(1.0),
            a=np.float64(0.0),
            b=np.float64(10.0),
        )
        self.assertAlmostEqual(float(outside_bounds.volume()), 0.073365, places=6)

    def test_normal_parameter_rejects_degenerate_stddev(self) -> None:
        """A non-finite or negative stddev is refused at construction."""
        for stddev in (np.inf, -np.inf, np.nan, -1.0):
            with self.assertRaises(EleanorError):
                _ = NormalParameter(mean=np.float64(0.0), stddev=np.float64(stddev))

    def test_normal_parameter_zero_stddev_is_a_point_mass(self) -> None:
        """A zero stddev has no volume and samples the mean, clamped into the bounds."""
        cases = [
            (NormalParameter(mean=np.float64(5.0), stddev=np.float64(0.0)), np.float64(5.0)),
            (
                NormalParameter(mean=np.float64(5.0), stddev=np.float64(0.0), a=np.float64(0.0), b=np.float64(10.0)),
                np.float64(5.0),
            ),
            (
                NormalParameter(mean=np.float64(10.0), stddev=np.float64(0.0), a=np.float64(0.0), b=np.float64(10.0)),
                np.float64(10.0),
            ),
            # A mean outside the bounds is supported, so it clamps to the nearer bound.
            (
                NormalParameter(mean=np.float64(100.0), stddev=np.float64(0.0), a=np.float64(0.0), b=np.float64(10.0)),
                np.float64(10.0),
            ),
        ]
        for parameter, expected in cases:
            self.assertEqual(parameter.volume(), np.float64(0.0))
            self.assertEqual([x.value for x in parameter.random(size=2)], [expected, expected])
            self.assertEqual([x.value for x in parameter.lattice(size=2)], [expected, expected])

    def test_normal_parameter_equal_bounds_is_a_point_mass(self) -> None:
        """Equal bounds pin the parameter whatever its stddev, and are not read as unbounded."""
        derived = NormalParameter(mean=np.float64(5.0), a=np.float64(5.0), b=np.float64(5.0))
        self.assertEqual(derived.stddev, np.float64(0.0))

        pinned = NormalParameter(
            mean=np.float64(50.0),
            stddev=np.float64(10.0),
            a=np.float64(100.0),
            b=np.float64(100.0),
        )
        for parameter, expected in ((derived, np.float64(5.0)), (pinned, np.float64(100.0))):
            self.assertEqual(parameter.volume(), np.float64(0.0))
            self.assertEqual([x.value for x in parameter.random(size=2)], [expected, expected])
            self.assertEqual([x.value for x in parameter.lattice(size=2)], [expected, expected])

        # Infinite equal bounds are degenerate, not an unbounded normal of volume SIGMA_SPAN * stddev.
        for bound in (np.inf, -np.inf):
            infinite = NormalParameter(mean=np.float64(0.0), a=np.float64(bound), b=np.float64(bound))
            self.assertEqual(infinite.volume(), np.float64(0.0))

    def test_normal_parameter_lattice_survives_heavy_truncation(self) -> None:
        """Lattice points stay inside the bounds however far outside them the mean sits."""
        cases = [
            NormalParameter(mean=np.float64(0.0), stddev=np.float64(1.0), a=np.float64(-11.0), b=np.float64(-10.0)),
            NormalParameter(mean=np.float64(1.0), stddev=np.float64(0.001), a=np.float64(0.0), b=np.float64(0.5)),
            NormalParameter(mean=np.float64(100.0), stddev=np.float64(1.0), a=np.float64(0.0), b=np.float64(10.0)),
        ]
        for parameter in cases:
            with self.subTest(parameter=parameter):
                points = parameter.lattice(size=3)
                values = [x.value for x in points]

                self.assertTrue(all(np.isfinite(v) for v in values), values)
                self.assertTrue(all(parameter.min <= v <= parameter.max for v in values), values)
                self.assertEqual(values, sorted(values), values)
                self.assertEqual(len(set(values)), len(values), values)
                # The refinement check the navigator applies to every generated value.
                self.assertTrue(all(parameter.in_domain(point) for point in points), values)

    def test_normal_parameter_range_and_bounds(self) -> None:
        """Range and bounds report the truncation bounds, infinite only where untruncated."""
        cases = [
            ("unbounded", NormalParameter(mean=np.float64(0.0)), (-np.inf, np.inf)),
            (
                "bounded",
                NormalParameter(mean=np.float64(0.0), a=np.float64(-3.0), b=np.float64(3.0)),
                (np.float64(-3.0), np.float64(3.0)),
            ),
            (
                "half-bounded",
                NormalParameter(mean=np.float64(250.0), stddev=np.float64(10.0), a=np.float64(200.0), b=POS_INF),
                (np.float64(200.0), np.inf),
            ),
        ]
        for label, parameter, expected in cases:
            with self.subTest(bounds=label):
                self.assertEqual(parameter.range(), expected)
                low, high = parameter.bounds
                self.assertEqual((low.value, high.value), expected)

    def test_normal_parameter_in_domain(self) -> None:
        """A bounded normal admits only parameters whose own support falls inside its bounds."""
        bounded = NormalParameter(mean=np.float64(25.0), stddev=np.float64(1.0), a=np.float64(20.0), b=np.float64(30.0))
        unbounded = NormalParameter(mean=np.float64(25.0), stddev=np.float64(1.0))

        inside: list[Parameter] = [
            ValueParameter(np.float64(25.0)),
            RangeParameter(np.float64(22.0), np.float64(28.0)),
            ListParameter([np.float64(21.0), np.float64(29.0)]),
            NormalParameter(mean=np.float64(25.0), stddev=np.float64(1.0), a=np.float64(22.0), b=np.float64(28.0)),
        ]
        outside: list[Parameter] = [
            ValueParameter(np.float64(500.0)),
            RangeParameter(np.float64(10.0), np.float64(40.0)),
            ListParameter([np.float64(21.0), np.float64(99.0)]),
            unbounded,
        ]

        for parameter in inside:
            with self.subTest(parameter=parameter):
                self.assertTrue(bounded.in_domain(parameter))
        for parameter in outside:
            with self.subTest(parameter=parameter):
                self.assertFalse(bounded.in_domain(parameter))

        # An untruncated normal has infinite bounds, so everything falls inside it.
        for parameter in [*inside, *outside]:
            with self.subTest(parameter=parameter):
                self.assertTrue(unbounded.in_domain(parameter))

    def test_range_and_list_in_domain_accept_a_normal(self) -> None:
        """A normal refines a range or list when its bounds fall inside."""
        bounded = NormalParameter(mean=np.float64(25.0), stddev=np.float64(1.0), a=np.float64(20.0), b=np.float64(30.0))
        unbounded = NormalParameter(mean=np.float64(25.0), stddev=np.float64(1.0))
        pinned = NormalParameter(mean=np.float64(25.0), stddev=np.float64(1.0), a=np.float64(25.0), b=np.float64(25.0))

        self.assertTrue(RangeParameter(np.float64(0.0), np.float64(50.0)).in_domain(bounded))
        self.assertFalse(RangeParameter(np.float64(0.0), np.float64(25.0)).in_domain(bounded))
        self.assertFalse(RangeParameter(np.float64(0.0), np.float64(50.0)).in_domain(unbounded))

        # A list only admits an interval that has collapsed to one of its values.
        self.assertTrue(ListParameter([np.float64(25.0)]).in_domain(pinned))
        self.assertFalse(ListParameter([np.float64(25.0)]).in_domain(bounded))
        self.assertFalse(ListParameter([np.float64(25.0)]).in_domain(unbounded))

    def test_parameter_registry(self) -> None:
        """
        Ensure :class:`ParameterRegistry` supports add/lookup and validates duplicates/bounds.
        """
        reg = ParameterRegistry()
        p0 = ValueParameter(np.float64(1.0))
        p1 = ValueParameter(np.float64(2.0))
        reg.add_parameter(p0)
        reg.add_parameters([p1])
        self.assertEqual(reg.valuation(), {0: p0, 1: p1})
        self.assertEqual(reg.id(p0), 0)
        self.assertIs(reg.parameter(1), p1)

        with self.assertRaises(EleanorError):
            reg.add_parameter(p0)
        with self.assertRaises(IndexError):
            _ = reg.id(ValueParameter(np.float64(3.0)))
        with self.assertRaises(IndexError):
            _ = reg.parameter(-1)
        with self.assertRaises(IndexError):
            _ = reg.parameter(10)
