from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast, override
from unittest import TestCase

import numpy as np
from eleanor.exceptions import EleanorError
from eleanor.kernel.eq36.constraints import (
    TemperatureRangeConstraint,
    TPCurveConstraint,
)
from eleanor.kernel.eq36.data1 import Data1
from eleanor.parameters import (
    ListParameter,
    NormalParameter,
    Parameter,
    ParameterRegistry,
    RangeParameter,
    ValueParameter,
)


@dataclass
class _DummyCurve:
    temperature: dict[str, np.float64]
    pressure: np.float64 | None = np.float64(10.0)
    in_domain: bool = True

    def temperature_in_domain(self, _temperature: np.float64):
        return self.in_domain

    def __call__(self, _temperature: np.float64):
        return self.pressure


class _WeirdParameter(Parameter):
    @override
    def in_domain(self, parameter: Parameter) -> bool:
        _ = parameter
        return True

    @override
    def range(self) -> tuple[np.float64, np.float64]:
        return np.float64(0.0), np.float64(0.0)

    @override
    def volume(self) -> np.float64:
        return np.float64(1.0)

    @override
    def random(self, size: int = 1):
        return []

    @override
    def lattice(self, size: int = 2):
        return []


def _data1_with_curve(curve: _DummyCurve | None) -> Data1:
    return cast(Data1, cast(object, SimpleNamespace(tp_curve=curve)))


class TestEq36Constraints(TestCase):
    """
    Tests of the eleanor.kernel.eq36.constraints module.
    """

    def _registry_with(self, *params):
        registry = ParameterRegistry()
        registry.add_parameters(list(params))
        return registry, registry.valuation()

    def test_temperature_range_init_requires_data1(self) -> None:
        """
        Ensure at least one data1 object is required.
        """
        with self.assertRaises(EleanorError):
            _ = TemperatureRangeConstraint(ValueParameter(np.float64(25.0)), [])

    def test_temperature_range_init_uses_tp_curves_only(self) -> None:
        """
        Ensure constructor aggregates min/max temperatures only from data1 entries with curves.
        """
        temp = ValueParameter(np.float64(25.0))
        c = TemperatureRangeConstraint(
            temp,
            [
                _data1_with_curve(None),
                _data1_with_curve(
                    _DummyCurve({"min": np.float64(10.0), "max": np.float64(40.0)})
                ),
                _data1_with_curve(
                    _DummyCurve({"min": np.float64(5.0), "max": np.float64(50.0)})
                ),
            ],
        )
        self.assertEqual(c.min_temp, np.float64(5.0))
        self.assertEqual(c.max_temp, np.float64(50.0))
        self.assertEqual(c.independent_parameters, [])
        self.assertEqual(c.dependent_parameters, [temp])

    def test_temperature_range_apply_value_range_list_normal(self) -> None:
        """
        Ensure apply refines each supported parameter type to the curve temperature bounds.
        """
        data1s = [
            _data1_with_curve(
                _DummyCurve({"min": np.float64(10.0), "max": np.float64(40.0)})
            )
        ]

        t_value = ValueParameter(np.float64(25.0))
        c_value = TemperatureRangeConstraint(t_value, data1s)
        registry, valuation = self._registry_with(t_value)
        refined_value = c_value.apply(registry, valuation)[0]
        self.assertIsInstance(refined_value, ValueParameter)
        if not isinstance(refined_value, ValueParameter):
            raise AssertionError("expected ValueParameter")
        self.assertEqual(refined_value.value, np.float64(25.0))

        t_range = RangeParameter(np.float64(0.0), np.float64(100.0))
        c_range = TemperatureRangeConstraint(t_range, data1s)
        registry, valuation = self._registry_with(t_range)
        refined_range = c_range.apply(registry, valuation)[0]
        self.assertIsInstance(refined_range, RangeParameter)
        if not isinstance(refined_range, RangeParameter):
            raise AssertionError("expected RangeParameter")
        self.assertEqual(
            (refined_range.min, refined_range.max), (np.float64(10.0), np.float64(40.0))
        )

        t_list = ListParameter(
            [np.float64(1.0), np.float64(12.0), np.float64(30.0), np.float64(99.0)],
        )
        c_list = TemperatureRangeConstraint(t_list, data1s)
        registry, valuation = self._registry_with(t_list)
        refined_list = c_list.apply(registry, valuation)[0]
        self.assertIsInstance(refined_list, ListParameter)
        if not isinstance(refined_list, ListParameter):
            raise AssertionError("expected ListParameter")
        self.assertEqual(refined_list.values, [np.float64(12.0), np.float64(30.0)])

        t_normal = NormalParameter(
            mean=np.float64(20.0),
            stddev=np.float64(5.0),
            a=np.float64(-50.0),
            b=np.float64(80.0),
        )
        c_normal = TemperatureRangeConstraint(t_normal, data1s)
        registry, valuation = self._registry_with(t_normal)
        refined_normal = c_normal.apply(registry, valuation)[0]
        self.assertIsInstance(refined_normal, NormalParameter)
        if not isinstance(refined_normal, NormalParameter):
            raise AssertionError("expected NormalParameter")
        self.assertEqual(
            (refined_normal.min, refined_normal.max),
            (np.float64(10.0), np.float64(40.0)),
        )

    def test_temperature_range_apply_incompatible_and_unexpected_parameter(
        self,
    ) -> None:
        """
        Ensure apply raises wrapped compatibility errors and rejects unexpected parameter types.
        """
        data1s = [
            _data1_with_curve(
                _DummyCurve({"min": np.float64(10.0), "max": np.float64(40.0)})
            )
        ]

        out_of_range = ValueParameter(np.float64(90.0))
        c = TemperatureRangeConstraint(out_of_range, data1s)
        registry, valuation = self._registry_with(out_of_range)
        with self.assertRaises(EleanorError):
            _ = c.apply(registry, valuation)
        empty_after_filter = ListParameter([np.float64(1.0), np.float64(2.0)])
        c2 = TemperatureRangeConstraint(empty_after_filter, data1s)
        registry, valuation = self._registry_with(empty_after_filter)
        with self.assertRaises(EleanorError):
            _ = c2.apply(registry, valuation)

        weird = _WeirdParameter()
        c3 = TemperatureRangeConstraint(weird, data1s)
        registry, valuation = self._registry_with(weird)
        with self.assertRaises(EleanorError):
            _ = c3.apply(registry, valuation)

    def test_tp_curve_constraint_properties_and_non_value_temperature(self) -> None:
        """
        Ensure TP-curve constraint dependency properties and temperature precondition checks.
        """
        temp = RangeParameter(np.float64(1.0), np.float64(2.0))
        pressure = RangeParameter(np.float64(1.0), np.float64(100.0))
        c = TPCurveConstraint(temp, pressure, [])
        self.assertEqual(c.independent_parameters, [temp])
        self.assertEqual(c.dependent_parameters, [pressure])

        registry, valuation = self._registry_with(temp, pressure)
        with self.assertRaises(EleanorError):
            _ = c.apply(registry, valuation)

    def test_tp_curve_constraint_apply_success_and_empty_candidates_error(self) -> None:
        """
        Ensure apply filters candidate pressures and wraps errors when no valid pressure remains.
        """
        temp = ValueParameter(np.float64(25.0))
        pressure = RangeParameter(np.float64(5.0), np.float64(20.0))
        data1s = [
            _data1_with_curve(None),
            _data1_with_curve(
                _DummyCurve(
                    {"min": np.float64(0.0), "max": np.float64(100.0)},
                    pressure=None,
                    in_domain=True,
                )
            ),
            _data1_with_curve(
                _DummyCurve(
                    {"min": np.float64(0.0), "max": np.float64(100.0)},
                    pressure=np.float64(30.0),
                    in_domain=True,
                )
            ),
            _data1_with_curve(
                _DummyCurve(
                    {"min": np.float64(0.0), "max": np.float64(100.0)},
                    pressure=np.float64(10.0),
                    in_domain=False,
                )
            ),
            _data1_with_curve(
                _DummyCurve(
                    {"min": np.float64(0.0), "max": np.float64(100.0)},
                    pressure=np.float64(12.0),
                    in_domain=True,
                )
            ),
        ]
        c = TPCurveConstraint(temp, pressure, data1s)
        registry, valuation = self._registry_with(temp, pressure)
        result = c.apply(registry, valuation)
        refined = result[registry.id(pressure)]
        self.assertIsInstance(refined, ValueParameter)
        if not isinstance(refined, ValueParameter):
            raise AssertionError("expected ValueParameter")
        self.assertEqual(refined.value, np.float64(12.0))

        pressure_strict = RangeParameter(np.float64(50.0), np.float64(60.0))
        c_strict = TPCurveConstraint(temp, pressure_strict, data1s)
        registry, valuation = self._registry_with(temp, pressure_strict)
        with self.assertRaises(EleanorError):
            _ = c_strict.apply(registry, valuation)
