from unittest import mock

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

from .common import TestCase


class TestParameters(TestCase):
    """
    Tests of the eleanor.parameters module.
    """

    def test_parameter_abstract_placeholders(self):
        """
        Ensure abstract placeholder bodies on :class:`Parameter` are executable directly.
        """
        self.assertFalse(Parameter.in_domain(object(), None))
        self.assertEqual(Parameter.range(object()), (0, 0))
        self.assertEqual(Parameter.volume(object()), 1.0)
        self.assertIsNone(Parameter.random(object()))
        self.assertIsNone(Parameter.lattice(object()))

    def test_parameter_from_dict_validation(self):
        """
        Ensure :meth:`Parameter.from_dict` validates required name/type metadata.
        """
        with self.assertRaises(EleanorException):
            Parameter.from_dict({"name": 1, "value": 1.0})
        with self.assertRaises(EleanorException):
            Parameter.from_dict({"name": "x", "type": 1, "value": 1.0})
        with self.assertRaises(EleanorException):
            Parameter.from_dict({"name": "x"})

    def test_parameter_from_dict_and_load_dispatch(self):
        """
        Ensure parameter parsing/load dispatch covers value/list/range/normal forms.
        """
        p0 = Parameter.from_dict({"name": "x", "value": 2})
        self.assertIsInstance(p0, ValueParameter)
        self.assertEqual(p0.value, 2)

        p1 = Parameter.from_dict({"name": "x", "values": [3, 1, 2]})
        self.assertIsInstance(p1, ListParameter)
        self.assertEqual(p1.values, [1, 2, 3])

        p2 = Parameter.from_dict({"name": "x", "min": 5, "max": 2})
        self.assertIsInstance(p2, RangeParameter)
        self.assertEqual((p2.min, p2.max), (2, 5))

        p3 = Parameter.from_dict({"name": "x", "mean": 0.0, "stddev": 2.0})
        self.assertIsInstance(p3, NormalParameter)
        self.assertEqual(p3.stddev, 2.0)

        self.assertIsInstance(Parameter.load({"value": 1.0}, "a"), ValueParameter)
        self.assertIsInstance(Parameter.load([1.0, 2.0], "a"), ListParameter)
        self.assertIsInstance(Parameter.load(1.0, "a"), ValueParameter)

    def test_parameter_refine_and_restrict(self):
        """
        Ensure refine/restrict/fix collapse degenerate list/range parameters to value parameters.
        """
        p = RangeParameter("x", None, 1.0, 1.0)
        self.assertIsInstance(Parameter.refine(p), ValueParameter)

        p = ListParameter("x", None, [2.0, 2.0])
        self.assertIsInstance(Parameter.refine(p), ValueParameter)

        p = RangeParameter("x", None, 0.0, 2.0)
        fixed = p.fix(1.0)
        self.assertIsInstance(fixed, ValueParameter)
        self.assertEqual(fixed.value, 1.0)

    def test_value_parameter_methods(self):
        """
        Ensure :class:`ValueParameter` domain/range/volume/random/lattice behave as expected.
        """
        p = ValueParameter("x", None, 2.0)
        self.assertTrue(p.in_domain(ValueParameter("x", None, 2.0)))
        self.assertFalse(p.in_domain(ValueParameter("x", None, 3.0)))
        self.assertFalse(p.in_domain(RangeParameter("x", None, 1.0, 2.0)))
        self.assertEqual(p.range(), (2.0, 2.0))
        self.assertEqual(p.volume(), 1.0)
        self.assertEqual([x.value for x in p.random(size=2)], [2.0, 2.0])
        self.assertEqual([x.value for x in p.lattice(size=3)], [2.0, 2.0, 2.0])

    def test_range_parameter_methods(self):
        """
        Ensure :class:`RangeParameter` ordering, domain checks, and generation helpers work.
        """
        p = RangeParameter("x", None, 3.0, 1.0)
        self.assertEqual((p.min, p.max), (1.0, 3.0))
        b0, b1 = p.bounds
        self.assertEqual((b0.value, b1.value), (1.0, 3.0))
        self.assertTrue(p.in_domain(ValueParameter("x", None, 2.0)))
        self.assertFalse(p.in_domain(ValueParameter("x", None, 4.0)))
        self.assertTrue(p.in_domain(RangeParameter("x", None, 1.5, 2.5)))
        self.assertTrue(p.in_domain(ListParameter("x", None, [1.0, 2.0, 3.0])))
        self.assertFalse(p.in_domain(ListParameter("x", None, [0.0, 2.0])))
        self.assertFalse(p.in_domain(object()))
        self.assertEqual(p.range(), (1.0, 3.0))
        self.assertEqual(p.volume(), 2.0)

        with mock.patch("eleanor.parameters.scipy.stats.uniform.rvs", return_value=np.array([1.0, 2.0])):
            out = p.random(size=2)
        self.assertEqual([x.value for x in out], [1.0, 2.0])

        out2 = p.lattice(size=3)
        self.assertEqual([x.value for x in out2], [1.0, 2.0, 3.0])

    def test_list_parameter_methods(self):
        """
        Ensure :class:`ListParameter` validation, domain checks, and generation helpers work.
        """
        with self.assertRaises(EleanorException):
            ListParameter("x", None, [])

        p = ListParameter("x", None, [3.0, 1.0, 2.0])
        self.assertEqual(p.values, [1.0, 2.0, 3.0])
        self.assertEqual([e.value for e in p.elements], [1.0, 2.0, 3.0])
        self.assertTrue(p.in_domain(ValueParameter("x", None, 2.0)))
        self.assertFalse(p.in_domain(ValueParameter("x", None, 5.0)))
        self.assertTrue(p.in_domain(RangeParameter("x", None, 2.0, 2.0)))
        self.assertFalse(p.in_domain(RangeParameter("x", None, 1.0, 2.0)))
        self.assertTrue(p.in_domain(ListParameter("x", None, [1.0, 2.0])))
        self.assertFalse(p.in_domain(ListParameter("x", None, [1.0, 4.0])))
        self.assertFalse(p.in_domain(object()))
        self.assertEqual(p.range(), (1.0, 3.0))
        self.assertEqual(p.volume(), 3)

        with mock.patch("eleanor.parameters.scipy.stats.randint.rvs", return_value=np.array([0, 2])):
            out = p.random(size=2)
        self.assertEqual([x.value for x in out], [1.0, 3.0])
        self.assertEqual([x.value for x in p.lattice(size=5)], [1.0, 2.0, 3.0, 1.0, 2.0])

    def test_normal_parameter_defaults_and_generation(self):
        """
        Ensure :class:`NormalParameter` default stddev, random, and lattice generation behave.
        """
        p0 = NormalParameter("x", None, mean=0.0)
        self.assertEqual(p0.stddev, 1.0)

        p1 = NormalParameter("x", None, mean=0.0, a=-3.0, b=3.0)
        self.assertEqual(p1.stddev, 1.0)
        self.assertEqual(p1.range(), (-float("inf"), float("inf")))
        self.assertEqual(p1.volume(), 1.0)
        self.assertTrue(p1.in_domain(object()))

        with mock.patch("eleanor.parameters.scipy.stats.norm.rvs", return_value=np.array([0.1, -0.2])):
            out0 = p0.random(size=2)
        self.assertEqual([round(x.value, 3) for x in out0], [0.1, -0.2])

        with mock.patch("eleanor.parameters.scipy.stats.truncnorm.rvs", return_value=np.array([0.2, 0.3])):
            out1 = p1.random(size=2)
        self.assertEqual([round(x.value, 3) for x in out1], [0.2, 0.3])

        out2 = p0.lattice(size=3)
        self.assertEqual(len(out2), 3)
        self.assertTrue(all(isinstance(v, ValueParameter) for v in out2))

        out3 = p1.lattice(size=3)
        self.assertEqual(len(out3), 3)
        self.assertTrue(all(isinstance(v, ValueParameter) for v in out3))

    def test_parameter_registry(self):
        """
        Ensure :class:`ParameterRegistry` supports add/lookup and validates duplicates/bounds.
        """
        reg = ParameterRegistry()
        p0 = ValueParameter("a", None, 1.0)
        p1 = ValueParameter("b", None, 2.0)
        reg.add_parameter(p0)
        reg.add_parameters([p1])
        self.assertEqual(reg.valuation(), {0: p0, 1: p1})
        self.assertEqual(reg.id(p0), 0)
        self.assertIs(reg.parameter(1), p1)

        with self.assertRaises(EleanorException):
            reg.add_parameter(p0)
        with self.assertRaises(IndexError):
            reg.id(ValueParameter("c", None, 3.0))
        with self.assertRaises(IndexError):
            reg.parameter(-1)
        with self.assertRaises(IndexError):
            reg.parameter(10)
