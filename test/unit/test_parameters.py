from typing import cast
from unittest import TestCase, mock

import numpy as np

from eleanor.exceptions import EleanorException
from eleanor.parameters import (
    ListParameter,
    NormalParameter,
    Parameter,
    ParameterRegistry,
    RangeParameter,
    ValueParameter,
)


class TestParameters(TestCase):
    """
    Tests of the eleanor.parameters module.
    """

    def test_parameter_abstract_placeholders(self):
        """
        Ensure abstract placeholder bodies on :class:`Parameter` are executable directly.
        """
        placeholder = cast(Parameter, object())
        self.assertFalse(Parameter.in_domain(placeholder, cast(Parameter, cast(object, None))))
        self.assertEqual(Parameter.range(placeholder), (np.float64(0), np.float64(0)))
        self.assertEqual(Parameter.volume(placeholder), np.float64(1.0))
        self.assertIsNone(Parameter.random(placeholder))
        self.assertIsNone(Parameter.lattice(placeholder))

    def test_parameter_from_dict_and_load_dispatch(self):
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

    def test_parameter_refine_and_restrict(self):
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

    def test_value_parameter_methods(self):
        """
        Ensure :class:`ValueParameter` domain/range/volume/random/lattice behave as expected.
        """
        p = ValueParameter(np.float64(2.0))
        self.assertTrue(p.in_domain(ValueParameter(np.float64(2.0))))
        self.assertFalse(p.in_domain(ValueParameter(np.float64(3.0))))
        self.assertFalse(p.in_domain(RangeParameter(np.float64(1.0), np.float64(2.0))))
        self.assertEqual(p.range(), (np.float64(2.0), np.float64(2.0)))
        self.assertEqual(p.volume(), np.float64(1.0))
        self.assertEqual([x.value for x in p.random(size=2)], [np.float64(2.0), np.float64(2.0)])
        self.assertEqual([x.value for x in p.lattice(size=3)], [np.float64(2.0), np.float64(2.0), np.float64(2.0)])

    def test_range_parameter_methods(self):
        """
        Ensure :class:`RangeParameter` ordering, domain checks, and generation helpers work.
        """
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

    def test_list_parameter_methods(self):
        """
        Ensure :class:`ListParameter` validation, domain checks, and generation helpers work.
        """
        with self.assertRaises(EleanorException):
            _ = ListParameter([])

        p = ListParameter([np.float64(3.0), np.float64(1.0), np.float64(2.0)])
        self.assertEqual(p.values, [np.float64(1.0), np.float64(2.0), np.float64(3.0)])
        self.assertEqual([e.value for e in p.elements], [np.float64(1.0), np.float64(2.0), np.float64(3.0)])
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
            [np.float64(1.0), np.float64(2.0), np.float64(3.0), np.float64(1.0), np.float64(2.0)],
        )

    def test_normal_parameter_defaults_and_generation(self):
        """
        Ensure :class:`NormalParameter` default stddev, random, and lattice generation behave.
        """
        p0 = NormalParameter(mean=np.float64(0.0))
        self.assertEqual(p0.stddev, np.float64(1.0))

        p1 = NormalParameter(mean=np.float64(0.0), a=np.float64(-3.0), b=np.float64(3.0))
        self.assertEqual(p1.stddev, np.float64(1.0))
        self.assertEqual(p1.range(), (-np.inf, np.inf))
        self.assertEqual(p1.volume(), np.float64(1.0))
        self.assertTrue(p1.in_domain(cast(Parameter, object())))

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

    def test_parameter_registry(self):
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

        with self.assertRaises(EleanorException):
            reg.add_parameter(p0)
        with self.assertRaises(IndexError):
            _ = reg.id(ValueParameter(np.float64(3.0)))
        with self.assertRaises(IndexError):
            _ = reg.parameter(-1)
        with self.assertRaises(IndexError):
            _ = reg.parameter(10)
