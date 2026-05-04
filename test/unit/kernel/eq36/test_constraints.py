from dataclasses import dataclass
from types import SimpleNamespace

from eleanor.exceptions import EleanorException
from eleanor.kernel.eq36.constraints import TemperatureRangeConstraint, TPCurveConstraint
from eleanor.parameters import (
    ListParameter,
    NormalParameter,
    Parameter,
    ParameterRegistry,
    RangeParameter,
    ValueParameter,
)

from ...common import TestCase


@dataclass
class _DummyCurve:
    T: dict[str, float]
    p: float = 10.0
    in_domain: bool = True

    def temperature_in_domain(self, _t):
        return self.in_domain

    def __call__(self, _t):
        return self.p


class _WeirdParameter(Parameter):
    def in_domain(self, _parameter) -> bool:
        return True

    def range(self):
        return 0, 0

    def volume(self) -> float:
        return 1.0

    def random(self, size: int = 1):
        return []

    def lattice(self, size: int = 2):
        return []


class TestEq36Constraints(TestCase):
    """
    Tests of the eleanor.kernel.eq36.constraints module.
    """

    def _registry_with(self, *params):
        registry = ParameterRegistry()
        registry.add_parameters(list(params))
        return registry, registry.valuation()

    def test_temperature_range_init_requires_data1(self):
        """
        Ensure at least one data1 object is required.
        """
        with self.assertRaises(EleanorException):
            TemperatureRangeConstraint(ValueParameter("temperature", None, 25.0), [])

    def test_temperature_range_init_uses_tp_curves_only(self):
        """
        Ensure constructor aggregates min/max temperatures only from data1 entries with curves.
        """
        temp = ValueParameter("temperature", None, 25.0)
        c = TemperatureRangeConstraint(
            temp,
            [
                SimpleNamespace(tp_curve=None),
                SimpleNamespace(tp_curve=_DummyCurve({"min": 10.0, "max": 40.0})),
                SimpleNamespace(tp_curve=_DummyCurve({"min": 5.0, "max": 50.0})),
            ],
        )
        self.assertEqual(c.min_t, 5.0)
        self.assertEqual(c.max_t, 50.0)
        self.assertEqual(c.independent_parameters, [])
        self.assertEqual(c.dependent_parameters, [temp])

    def test_temperature_range_apply_value_range_list_normal(self):
        """
        Ensure apply refines each supported parameter type to the curve temperature bounds.
        """
        data1s = [SimpleNamespace(tp_curve=_DummyCurve({"min": 10.0, "max": 40.0}))]

        t_value = ValueParameter("temperature", None, 25.0)
        c_value = TemperatureRangeConstraint(t_value, data1s)
        registry, valuation = self._registry_with(t_value)
        self.assertEqual(c_value.apply(registry, valuation)[0].value, 25.0)

        t_range = RangeParameter("temperature", None, 0.0, 100.0)
        c_range = TemperatureRangeConstraint(t_range, data1s)
        registry, valuation = self._registry_with(t_range)
        refined_range = c_range.apply(registry, valuation)[0]
        self.assertEqual((refined_range.min, refined_range.max), (10.0, 40.0))

        t_list = ListParameter("temperature", None, [1.0, 12.0, 30.0, 99.0])
        c_list = TemperatureRangeConstraint(t_list, data1s)
        registry, valuation = self._registry_with(t_list)
        refined_list = c_list.apply(registry, valuation)[0]
        self.assertEqual(refined_list.values, [12.0, 30.0])

        t_normal = NormalParameter("temperature", None, mean=20.0, stddev=5.0, a=-50.0, b=80.0)
        c_normal = TemperatureRangeConstraint(t_normal, data1s)
        registry, valuation = self._registry_with(t_normal)
        refined_normal = c_normal.apply(registry, valuation)[0]
        self.assertEqual((refined_normal.min, refined_normal.max), (10.0, 40.0))

    def test_temperature_range_apply_incompatible_and_unexpected_parameter(self):
        """
        Ensure apply raises wrapped compatibility errors and rejects unexpected parameter types.
        """
        data1s = [SimpleNamespace(tp_curve=_DummyCurve({"min": 10.0, "max": 40.0}))]

        out_of_range = ValueParameter("temperature", None, 90.0)
        c = TemperatureRangeConstraint(out_of_range, data1s)
        registry, valuation = self._registry_with(out_of_range)
        with self.assertRaises(EleanorException):
            c.apply(registry, valuation)

        empty_after_filter = ListParameter("temperature", None, [1.0, 2.0])
        c2 = TemperatureRangeConstraint(empty_after_filter, data1s)
        registry, valuation = self._registry_with(empty_after_filter)
        with self.assertRaises(EleanorException):
            c2.apply(registry, valuation)

        weird = _WeirdParameter("temperature", None)
        c3 = TemperatureRangeConstraint(weird, data1s)
        registry, valuation = self._registry_with(weird)
        with self.assertRaises(EleanorException):
            c3.apply(registry, valuation)

    def test_tp_curve_constraint_properties_and_non_value_temperature(self):
        """
        Ensure TP-curve constraint dependency properties and temperature precondition checks.
        """
        temp = RangeParameter("temperature", None, 1.0, 2.0)
        pressure = RangeParameter("pressure", None, 1.0, 100.0)
        c = TPCurveConstraint(temp, pressure, [])
        self.assertEqual(c.independent_parameters, [temp])
        self.assertEqual(c.dependent_parameters, [pressure])

        registry, valuation = self._registry_with(temp, pressure)
        with self.assertRaises(EleanorException):
            c.apply(registry, valuation)

    def test_tp_curve_constraint_apply_success_and_empty_candidates_error(self):
        """
        Ensure apply filters candidate pressures and wraps errors when no valid pressure remains.
        """
        temp = ValueParameter("temperature", None, 25.0)
        pressure = RangeParameter("pressure", None, 5.0, 20.0)
        data1s = [
            SimpleNamespace(tp_curve=None),
            SimpleNamespace(tp_curve=_DummyCurve({"min": 0.0, "max": 100.0}, p=None, in_domain=True)),
            SimpleNamespace(tp_curve=_DummyCurve({"min": 0.0, "max": 100.0}, p=30.0, in_domain=True)),
            SimpleNamespace(tp_curve=_DummyCurve({"min": 0.0, "max": 100.0}, p=10.0, in_domain=False)),
            SimpleNamespace(tp_curve=_DummyCurve({"min": 0.0, "max": 100.0}, p=12.0, in_domain=True)),
        ]
        c = TPCurveConstraint(temp, pressure, data1s)
        registry, valuation = self._registry_with(temp, pressure)
        result = c.apply(registry, valuation)
        refined = result[registry.id(pressure)]
        self.assertEqual(refined.value, 12.0)

        pressure_strict = RangeParameter("pressure", None, 50.0, 60.0)
        c_strict = TPCurveConstraint(temp, pressure_strict, data1s)
        registry, valuation = self._registry_with(temp, pressure_strict)
        with self.assertRaises(EleanorException):
            c_strict.apply(registry, valuation)
