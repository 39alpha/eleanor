from typing import cast, final, override
from unittest import mock

import numpy as np

from eleanor.constraints.boatswain import Boatswain
from eleanor.constraints.config import Config as ConstraintConfig
from eleanor.constraints.interface import (
    AbstractConstraint,
    LinearConstraint,
    LinearConstraintTerm,
    Transform,
    resolve_parameter,
)
from eleanor.exceptions import EleanorException
from eleanor.kernel.config import Config as KernelConfig
from eleanor.kernel.config import Settings
from eleanor.order import Order, Suppression
from eleanor.parameters import Parameter, ParameterRegistry, RangeParameter, Valuation, ValueParameter
from eleanor.reactants import (
    AqueousReactant,
    CombinedReactant,
    CombinedReactantComponent,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    MineralReactant,
    Reactant,
    ReactantType,
    SolidSolutionReactant,
    SpecialReactant,
)

from .common import TestCase


@final
class EchoConstraint(AbstractConstraint):
    """
    Test helper that fixes one dependent parameter to a chosen value.
    """

    def __init__(self, independent: Parameter, dependent: Parameter, value: np.float64) -> None:
        self._independent = independent
        self._dependent = dependent
        self._value = value

    @property
    @override
    def independent_parameters(self) -> list[Parameter]:
        return [self._independent]

    @property
    @override
    def dependent_parameters(self) -> list[Parameter]:
        return [self._dependent]

    @override
    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        _ = valuation
        return {registry.id(self._dependent): self._dependent.fix(self._value)}


@final
class DummyOrder:
    """
    Minimal order-like object used to exercise Boatswain logic.
    """

    def __init__(
        self,
        *,
        parameters: list[Parameter],
        water_mass: Parameter | None = None,
        temperature: Parameter,
        pressure: Parameter,
        elements: dict[str, Parameter],
        species: dict[str, Parameter],
        suppressions: list[Suppression],
        reactants: list[Reactant],
    ):
        self._parameters = parameters
        self.constraints = []
        self.water_mass = water_mass
        self.temperature = temperature
        self.pressure = pressure
        self.elements = elements
        self.species = species
        self.suppressions = suppressions
        self.reactants = reactants
        self.kernel = KernelConfig(type="eq36", settings=Settings(timeout=1))

    def parameters(self):
        return self._parameters


def _as_order(order: DummyOrder) -> Order:
    return cast(Order, cast(object, order))


class TestConstraints(TestCase):
    """
    Tests of the eleanor.constraints module.
    """

    def test_abstract_constraint_dependency_and_resolution(self):
        """
        Ensure dependency checks and resolution gatekeeping behave as expected.
        """
        p_ind = ValueParameter(np.float64(1.0))
        p_dep = RangeParameter(np.float64(0.0), np.float64(10.0))
        registry = ParameterRegistry()
        registry.add_parameters([p_ind, p_dep])
        valuation = registry.valuation()
        constraint = EchoConstraint(p_ind, p_dep, np.float64(2.5))

        self.assertTrue(constraint.depends_on(p_ind))
        self.assertTrue(constraint.constrains(p_dep))
        self.assertTrue(constraint.is_resolvable(registry, valuation))

        constraint.resolve(registry, valuation)
        resolved = valuation[registry.id(p_dep)]
        self.assertIsInstance(resolved, ValueParameter)
        if not isinstance(resolved, ValueParameter):
            raise AssertionError("expected ValueParameter")
        self.assertEqual(resolved.value, 2.5)

    def test_abstract_constraint_unresolvable_raises(self):
        """
        Ensure resolving with unresolved independent parameters raises.
        """
        p_ind = RangeParameter(np.float64(0.0), np.float64(1.0))
        p_dep = RangeParameter(np.float64(0.0), np.float64(1.0))
        registry = ParameterRegistry()
        registry.add_parameters([p_ind, p_dep])
        valuation = registry.valuation()
        constraint = EchoConstraint(p_ind, p_dep, np.float64(0.5))

        self.assertFalse(constraint.is_resolvable(registry, valuation))
        with self.assertRaises(Exception):
            constraint.resolve(registry, valuation)

    def test_abstract_constraint_from_order_placeholder(self):
        """
        Ensure placeholder :meth:`AbstractConstraint.from_order` is executable.
        """
        dummy_order = cast(Order, object())
        dummy_constraint_config = ConstraintConfig(type="unknown", args={})
        self.assertIsNone(AbstractConstraint.from_order(dummy_order, dummy_constraint_config))

    def test_abstract_constraint_placeholder_methods_are_executable(self):
        """
        Ensure abstract placeholder bodies can be executed directly.
        """
        abstract_constraint = cast(AbstractConstraint, object())
        registry = cast(ParameterRegistry, object())
        valuation = cast(Valuation, object())
        independent_getter = AbstractConstraint.independent_parameters.fget
        dependent_getter = AbstractConstraint.dependent_parameters.fget
        self.assertIsNotNone(independent_getter)
        self.assertIsNotNone(dependent_getter)
        if independent_getter is None or dependent_getter is None:
            raise AssertionError("property getter unexpectedly missing")
        self.assertIsNone(independent_getter(abstract_constraint))
        self.assertIsNone(dependent_getter(abstract_constraint))
        self.assertIsNone(AbstractConstraint.apply(abstract_constraint, registry, valuation))

    def test_transform_forward_and_inverse(self):
        """
        Verify each Transform variant's forward and inverse are mutual inverses.
        """
        x = np.float64(2.0)
        for transform in Transform:
            y = transform.forward(x)
            x_round = transform.inverse(y)
            self.assertAlmostEqual(float(x_round), float(x), places=10)

        self.assertAlmostEqual(float(Transform.IDENTITY.forward(np.float64(3.0))), 3.0)
        self.assertAlmostEqual(float(Transform.LOG10.forward(np.float64(100.0))), 2.0)
        self.assertAlmostEqual(float(Transform.POW10.forward(np.float64(2.0))), 100.0)
        self.assertAlmostEqual(float(Transform.LOG10.inverse(np.float64(2.0))), 100.0)
        self.assertAlmostEqual(float(Transform.POW10.inverse(np.float64(100.0))), 2.0)

    def test_linear_constraint_construction_sorts_by_volume(self):
        """
        Verify terms are stable-sorted by parameter volume descending (largest first).
        """
        p_small = RangeParameter(np.float64(0.0), np.float64(1.0))
        p_big = RangeParameter(np.float64(0.0), np.float64(10.0))
        p_fixed = ValueParameter(np.float64(5.0))
        terms = [
            LinearConstraintTerm(p_big, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_fixed, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_small, np.float64(1.0), Transform.IDENTITY),
        ]

        linear_constraint = LinearConstraint(terms)
        self.assertIsNotNone(linear_constraint._dependent_term)
        if linear_constraint._dependent_term is None:
            raise AssertionError("expected dependent term")
        self.assertIs(linear_constraint._dependent_term.parameter, p_big)
        self.assertEqual(len(linear_constraint._independent_terms), 2)

    def test_linear_constraint_dependent_independent_split(self):
        """
        Verify dependent/independent split with mixed parameter types.
        """
        p_range = RangeParameter(np.float64(0.0), np.float64(5.0))
        p_value = ValueParameter(np.float64(3.0))
        terms = [
            LinearConstraintTerm(p_range, np.float64(2.0), Transform.IDENTITY),
            LinearConstraintTerm(p_value, np.float64(1.0), Transform.LOG10),
        ]

        linear_constraint = LinearConstraint(terms)
        self.assertEqual(len(linear_constraint.dependent_parameters), 1)
        self.assertIs(linear_constraint.dependent_parameters[0], p_range)
        independent_parameters = linear_constraint.independent_parameters
        self.assertIn(p_value, independent_parameters)
        self.assertIn(linear_constraint.constant, independent_parameters)

    def test_linear_constraint_all_value_parameters_no_dependent(self):
        """
        When all terms are ValueParameter, dependent_parameters is empty.
        """
        p1 = ValueParameter(np.float64(1.0))
        p2 = ValueParameter(np.float64(2.0))
        terms = [
            LinearConstraintTerm(p1, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p2, np.float64(1.0), Transform.IDENTITY),
        ]

        linear_constraint = LinearConstraint(terms, constant=ValueParameter(np.float64(3.0)))
        self.assertEqual(linear_constraint.dependent_parameters, [])

    def test_linear_constraint_apply_solves_for_dependent(self):
        """
        Verify apply computes the correct dependent value for a simple linear equation.
        """
        p_dep = RangeParameter(np.float64(0.0), np.float64(10.0))
        p_ind = ValueParameter(np.float64(3.0))
        terms = [
            LinearConstraintTerm(p_dep, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_ind, np.float64(1.0), Transform.IDENTITY),
        ]
        constant = ValueParameter(np.float64(7.0))
        linear_constraint = LinearConstraint(terms, constant=constant)
        registry = ParameterRegistry()
        registry.add_parameters([p_dep, p_ind, constant])
        valuation = registry.valuation()

        result = linear_constraint.apply(registry, valuation)
        self.assertIn(registry.id(p_dep), result)
        resolved = result[registry.id(p_dep)]
        self.assertIsInstance(resolved, ValueParameter)
        if isinstance(resolved, ValueParameter):
            self.assertAlmostEqual(float(resolved.value), 4.0)

    def test_linear_constraint_apply_with_log10_transform(self):
        """
        Verify apply with log10 transform resolves expected dependent value.
        """
        p_dep = RangeParameter(np.float64(1.0), np.float64(1000.0))
        terms = [LinearConstraintTerm(p_dep, np.float64(1.0), Transform.LOG10)]
        constant = ValueParameter(np.float64(2.0))
        linear_constraint = LinearConstraint(terms, constant=constant)
        registry = ParameterRegistry()
        registry.add_parameters([p_dep, constant])
        valuation = registry.valuation()

        result = linear_constraint.apply(registry, valuation)
        resolved = result[registry.id(p_dep)]
        self.assertIsInstance(resolved, ValueParameter)
        if isinstance(resolved, ValueParameter):
            self.assertAlmostEqual(float(resolved.value), 100.0)

    def test_linear_constraint_apply_all_fixed_validates_tolerance(self):
        """
        When all terms are fixed, apply checks the equation holds within tolerance.
        """
        p1 = ValueParameter(np.float64(1.0))
        p2 = ValueParameter(np.float64(2.0))
        terms = [
            LinearConstraintTerm(p1, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p2, np.float64(1.0), Transform.IDENTITY),
        ]

        constant = ValueParameter(np.float64(3.0))
        linear_constraint = LinearConstraint(terms, constant=constant)
        registry = ParameterRegistry()
        registry.add_parameters([p1, p2, constant])
        valuation = registry.valuation()
        result = linear_constraint.apply(registry, valuation)
        self.assertEqual(result, {})

        constant_bad = ValueParameter(np.float64(10.0))
        linear_constraint_bad = LinearConstraint(terms, constant=constant_bad)
        registry_bad = ParameterRegistry()
        registry_bad.add_parameters([p1, p2, constant_bad])
        valuation_bad = registry_bad.valuation()
        with self.assertRaises(EleanorException):
            _ = linear_constraint_bad.apply(registry_bad, valuation_bad)

    def test_linear_constraint_is_resolvable(self):
        """
        is_resolvable is true when all independent params are ValueParameter.
        """
        p_dep = RangeParameter(np.float64(0.0), np.float64(10.0))
        p_ind = ValueParameter(np.float64(3.0))
        terms = [
            LinearConstraintTerm(p_dep, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_ind, np.float64(1.0), Transform.IDENTITY),
        ]
        linear_constraint = LinearConstraint(terms)
        constant = linear_constraint.constant
        registry = ParameterRegistry()
        registry.add_parameters([p_dep, p_ind, constant])
        valuation = registry.valuation()
        self.assertTrue(linear_constraint.is_resolvable(registry, valuation))

        p_dep2 = RangeParameter(np.float64(0.0), np.float64(5.0))
        p_ind2 = RangeParameter(np.float64(0.0), np.float64(10.0))
        terms2 = [
            LinearConstraintTerm(p_dep2, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_ind2, np.float64(1.0), Transform.IDENTITY),
        ]
        linear_constraint2 = LinearConstraint(terms2)
        registry2 = ParameterRegistry()
        registry2.add_parameters([p_dep2, p_ind2, linear_constraint2.constant])
        valuation2 = registry2.valuation()
        self.assertFalse(linear_constraint2.is_resolvable(registry2, valuation2))

    def test_resolve_parameter_simple_and_filtered_paths(self):
        """
        Verify resolve_parameter handles plain attributes, dict filters, and list filters.
        """
        temp = RangeParameter(np.float64(10.0), np.float64(100.0))
        na = ValueParameter(np.float64(-1.0))
        amount = RangeParameter(np.float64(0.0), np.float64(5.0))

        @final
        class FakeReactant:
            def __init__(self, name: str, amount: Parameter):
                self.name = name
                self.amount = amount

        @final
        class FakeOrder:
            def __init__(self):
                self.temperature = temp
                self.elements = {"Na": na}
                self.reactants = [FakeReactant("calcite", amount)]

        order = cast(Order, cast(object, FakeOrder()))
        self.assertIs(resolve_parameter(order, "temperature"), temp)
        self.assertIs(resolve_parameter(order, "elements[key=Na]"), na)
        self.assertIs(resolve_parameter(order, "reactants[name=calcite].amount"), amount)
        with self.assertRaises(EleanorException):
            _ = resolve_parameter(order, "nonexistent")
        with self.assertRaises(EleanorException):
            _ = resolve_parameter(order, "elements[key=missing]")

    def test_linear_constraint_from_order_round_trip(self):
        """
        Round-trip raw constraint dict through from_order into a LinearConstraint.
        """
        temp = RangeParameter(np.float64(10.0), np.float64(100.0))
        na = ValueParameter(np.float64(-1.0))
        order = DummyOrder(
            parameters=[temp, na],
            temperature=temp,
            pressure=ValueParameter(np.float64(1.0)),
            elements={"Na": na},
            species={},
            suppressions=[],
            reactants=[],
        )
        raw: dict[str, object] = {
            "type": "linear",
            "terms": [
                {"variable": "temperature", "coefficient": 1.0, "transform": "identity"},
                {"variable": "elements[key=Na]", "coefficient": -2.0, "transform": "log10"},
            ],
            "constant": 5.0,
            "tolerance": 1e-8,
        }
        config = ConstraintConfig(type="linear", args=raw)
        result = AbstractConstraint.from_order(_as_order(order), config)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, LinearConstraint)
        if isinstance(result, LinearConstraint):
            self.assertEqual(len(result.terms), 2)
            self.assertAlmostEqual(float(result.tolerance), 1e-8)

    def test_from_order_missing_terms_raises(self):
        """
        Verify from_order raises when the raw dict has no 'terms' key.
        """
        order = self._make_simple_order()
        config = ConstraintConfig(type="linear", args={"type": "linear"})
        with self.assertRaises(EleanorException):
            _ = LinearConstraint.from_order(_as_order(order), config)

    def test_from_order_non_dict_term_raises(self):
        """
        Verify from_order raises when a term entry is not a dict.
        """
        order = self._make_simple_order()
        raw: dict[str, object] = {"type": "linear", "terms": ["not_a_dict"]}
        config = ConstraintConfig(type="linear", args=raw)
        with self.assertRaises(EleanorException):
            _ = LinearConstraint.from_order(_as_order(order), config)

    def test_from_order_missing_variable_raises(self):
        """
        Verify from_order raises when a term has no 'variable' key.
        """
        order = self._make_simple_order()
        raw: dict[str, object] = {"type": "linear", "terms": [{"coefficient": 1.0}]}
        config = ConstraintConfig(type="linear", args=raw)
        with self.assertRaises(EleanorException):
            _ = LinearConstraint.from_order(_as_order(order), config)

    def test_from_order_non_numeric_coefficient_raises(self):
        """
        Verify from_order raises when a coefficient is a bool or non-numeric type.
        """
        order = self._make_simple_order()
        raw_bool: dict[str, object] = {
            "type": "linear",
            "terms": [{"variable": "temperature", "coefficient": True}],
        }
        with self.assertRaises(EleanorException):
            _ = LinearConstraint.from_order(_as_order(order), ConstraintConfig(type="linear", args=raw_bool))

        raw_list: dict[str, object] = {
            "type": "linear",
            "terms": [{"variable": "temperature", "coefficient": [1, 2]}],
        }
        with self.assertRaises(EleanorException):
            _ = LinearConstraint.from_order(_as_order(order), ConstraintConfig(type="linear", args=raw_list))

    def test_from_order_invalid_transform_raises(self):
        """
        Verify from_order raises for an unrecognised transform string.
        """
        order = self._make_simple_order()
        raw: dict[str, object] = {
            "type": "linear",
            "terms": [{"variable": "temperature", "transform": "ln"}],
        }
        config = ConstraintConfig(type="linear", args=raw)
        with self.assertRaises(EleanorException):
            _ = LinearConstraint.from_order(_as_order(order), config)

    def test_from_order_non_numeric_tolerance_raises(self):
        """
        Verify from_order raises when tolerance is a bool or non-numeric type.
        """
        order = self._make_simple_order()
        raw: dict[str, object] = {
            "type": "linear",
            "terms": [{"variable": "temperature"}],
            "tolerance": True,
        }
        config = ConstraintConfig(type="linear", args=raw)
        with self.assertRaises(EleanorException):
            _ = LinearConstraint.from_order(_as_order(order), config)

    def _make_simple_order(self) -> DummyOrder:
        """Return a minimal DummyOrder with a single resolvable temperature parameter."""
        temp = RangeParameter(np.float64(10.0), np.float64(100.0))
        return DummyOrder(
            parameters=[temp],
            temperature=temp,
            pressure=ValueParameter(np.float64(1.0)),
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )

    def test_transform_forward_raises_on_non_positive_log10(self):
        """
        Verify log10 forward raises EleanorException for zero and negative inputs.
        """
        with self.assertRaises(EleanorException):
            _ = Transform.LOG10.forward(np.float64(0.0))
        with self.assertRaises(EleanorException):
            _ = Transform.LOG10.forward(np.float64(-1.0))

    def test_transform_inverse_raises_on_non_positive_pow10(self):
        """
        Verify pow10 inverse (log10) raises EleanorException for zero and negative inputs.
        """
        with self.assertRaises(EleanorException):
            _ = Transform.POW10.inverse(np.float64(0.0))
        with self.assertRaises(EleanorException):
            _ = Transform.POW10.inverse(np.float64(-1.0))

    def test_transform_forward_raises_on_overflow(self):
        """
        Verify pow10 forward raises EleanorException on overflow.
        """
        with self.assertRaises(EleanorException):
            _ = Transform.POW10.forward(np.float64(1e308))

    def test_linear_constraint_apply_zero_coefficient_raises(self):
        """
        Verify apply raises when the dependent term has a zero coefficient.
        """
        p_dep = RangeParameter(np.float64(0.0), np.float64(10.0))
        p_ind = ValueParameter(np.float64(3.0))
        terms = [
            LinearConstraintTerm(p_dep, np.float64(0.0), Transform.IDENTITY),
            LinearConstraintTerm(p_ind, np.float64(1.0), Transform.IDENTITY),
        ]
        constant = ValueParameter(np.float64(7.0))
        linear_constraint = LinearConstraint(terms, constant=constant)
        registry = ParameterRegistry()
        registry.add_parameters([p_dep, p_ind, constant])
        valuation = registry.valuation()
        with self.assertRaises(EleanorException):
            _ = linear_constraint.apply(registry, valuation)

    def test_linear_constraint_apply_out_of_domain_raises(self):
        """
        Verify apply raises when the solved value falls outside the dependent parameter's domain.
        """
        p_dep = RangeParameter(np.float64(0.0), np.float64(5.0))
        p_ind = ValueParameter(np.float64(1.0))
        terms = [
            LinearConstraintTerm(p_dep, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_ind, np.float64(1.0), Transform.IDENTITY),
        ]
        # x + y = 100 => x = 99, which is outside [0, 5]
        constant = ValueParameter(np.float64(100.0))
        linear_constraint = LinearConstraint(terms, constant=constant)
        registry = ParameterRegistry()
        registry.add_parameters([p_dep, p_ind, constant])
        valuation = registry.valuation()
        with self.assertRaises(EleanorException):
            _ = linear_constraint.apply(registry, valuation)

    def test_linear_constraint_empty_terms_raises(self):
        """
        Verify constructing a LinearConstraint with no terms raises.
        """
        with self.assertRaises(EleanorException):
            _ = LinearConstraint([])

    def test_linear_constraint_volume_delegates_to_constant(self):
        """
        Verify volume() returns the constant parameter's volume.
        """
        p = ValueParameter(np.float64(1.0))
        terms = [LinearConstraintTerm(p, np.float64(1.0), Transform.IDENTITY)]

        fixed_constant = ValueParameter(np.float64(5.0))
        lc_fixed = LinearConstraint(terms, constant=fixed_constant)
        self.assertEqual(float(lc_fixed.volume()), 1.0)

        range_constant = RangeParameter(np.float64(0.0), np.float64(10.0))
        lc_range = LinearConstraint(terms, constant=range_constant)
        self.assertEqual(float(lc_range.volume()), 10.0)

    def test_abstract_constraint_volume_default(self):
        """
        Verify the base AbstractConstraint.volume() returns 1.0.
        """
        p_ind = ValueParameter(np.float64(1.0))
        p_dep = RangeParameter(np.float64(0.0), np.float64(10.0))
        constraint = EchoConstraint(p_ind, p_dep, np.float64(2.5))
        self.assertEqual(float(constraint.volume()), 1.0)

    def test_linear_constraint_multiple_range_terms(self):
        """
        When multiple terms are RangeParameters, only the largest-volume one becomes dependent.
        The constraint stays unresolvable until the independent ranges are fixed.
        """
        p_small = RangeParameter(np.float64(0.0), np.float64(2.0))
        p_large = RangeParameter(np.float64(0.0), np.float64(100.0))
        terms = [
            LinearConstraintTerm(p_small, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_large, np.float64(1.0), Transform.IDENTITY),
        ]
        lc = LinearConstraint(terms)
        self.assertEqual(lc.dependent_parameters, [p_large])
        self.assertIn(p_small, [t.parameter for t in lc._independent_terms])

        registry = ParameterRegistry()
        registry.add_parameters([p_small, p_large, lc.constant])
        valuation = registry.valuation()
        self.assertFalse(lc.is_resolvable(registry, valuation))

    def test_boatswain_with_linear_constraint_end_to_end(self):
        """
        End-to-end Boatswain flow resolves a linear constraint during constrain.
        """
        p_x = RangeParameter(np.float64(0.0), np.float64(20.0))
        p_y = ValueParameter(np.float64(3.0))
        constant = ValueParameter(np.float64(10.0))
        terms = [
            LinearConstraintTerm(p_x, np.float64(1.0), Transform.IDENTITY),
            LinearConstraintTerm(p_y, np.float64(1.0), Transform.IDENTITY),
        ]
        linear_constraint = LinearConstraint(terms, constant=constant)
        order = DummyOrder(
            parameters=[p_x, p_y],
            temperature=p_y,
            pressure=p_y,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(_as_order(order), linear_constraint)
        _ = boatswain.constrain()
        resolved = boatswain[p_x]
        self.assertIsInstance(resolved, ValueParameter)
        if isinstance(resolved, ValueParameter):
            self.assertAlmostEqual(float(resolved.value), 7.0)

    def test_boatswain_get_set_hardset_and_domain_errors(self):
        """
        Ensure Boatswain item access and refinement checks enforce registry/domain constraints.
        """
        temp = RangeParameter(np.float64(10.0), np.float64(20.0))
        pressure = ValueParameter(np.float64(1.0))
        order = DummyOrder(
            parameters=[temp, pressure],
            temperature=temp.fix(np.float64(15.0)),
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(_as_order(order))

        start = boatswain[temp]
        self.assertIsInstance(start, RangeParameter)
        if not isinstance(start, RangeParameter):
            raise AssertionError("expected RangeParameter")
        self.assertEqual(start.min, 10.0)
        boatswain[temp] = temp.fix(np.float64(12.0))
        updated = boatswain[temp]
        self.assertIsInstance(updated, ValueParameter)
        if not isinstance(updated, ValueParameter):
            raise AssertionError("expected ValueParameter")
        self.assertEqual(updated.value, 12.0)

        with self.assertRaises(Exception):
            boatswain[ValueParameter(np.float64(1.0))] = ValueParameter(np.float64(1.0))

        with self.assertRaises(Exception):
            boatswain[temp] = temp.fix(np.float64(50.0))

        boatswain.hardset(temp, temp.fix(np.float64(11.0)))
        with self.assertRaises(Exception):
            boatswain[temp] = temp.fix(np.float64(12.0))

    def test_boatswain_setitem_parameter_id_not_in_valuations(self):
        """
        Ensure setitem raises when registry returns an unknown parameter id.
        """
        temp = RangeParameter(np.float64(10.0), np.float64(20.0))
        pressure = ValueParameter(np.float64(1.0))
        order = DummyOrder(
            parameters=[temp, pressure],
            temperature=temp.fix(np.float64(15.0)),
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(_as_order(order))
        with mock.patch.object(boatswain.registry, "id", return_value=999):
            with self.assertRaises(Exception):
                boatswain[temp] = temp.fix(np.float64(12.0))

    def test_boatswain_constrain_tracks_fully_and_under_constrained(self):
        """
        Ensure constrain resolves what it can and returns fully constrained non-value parameters.
        """
        p_fixed = ValueParameter(np.float64(1.0))
        p_target = RangeParameter(np.float64(0.0), np.float64(5.0))
        p_other = RangeParameter(np.float64(10.0), np.float64(20.0))

        order = DummyOrder(
            parameters=[p_fixed, p_target, p_other],
            temperature=p_fixed,
            pressure=p_fixed,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        c_resolvable = EchoConstraint(p_fixed, p_target, np.float64(3.0))
        c_unresolved = EchoConstraint(p_other, p_target, np.float64(2.0))

        boatswain = Boatswain(_as_order(order), c_resolvable, c_unresolved)
        fully = boatswain.constrain()

        self.assertIn(p_other, fully)
        self.assertEqual(len(boatswain.constraints), 1)
        self.assertIs(boatswain.constraints[0], c_unresolved)
        constrained = boatswain[p_target]
        self.assertIsInstance(constrained, ValueParameter)
        if not isinstance(constrained, ValueParameter):
            raise AssertionError("expected ValueParameter")
        self.assertEqual(constrained.value, 3.0)
        self.assertEqual(boatswain.parameters, [])

    def test_boatswain_constrain_tracks_under_constrained_branch(self):
        """
        Ensure parameters constrained by unresolved constraints are tracked as under-constrained.
        """
        p_fixed = ValueParameter(np.float64(1.0))
        p_independent = RangeParameter(np.float64(0.0), np.float64(5.0))
        p_dependent = RangeParameter(np.float64(10.0), np.float64(20.0))
        unresolved = EchoConstraint(p_independent, p_dependent, np.float64(15.0))

        order = DummyOrder(
            parameters=[p_fixed, p_independent, p_dependent],
            temperature=p_fixed,
            pressure=p_fixed,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(_as_order(order), unresolved)
        fully = boatswain.constrain()

        self.assertIn(p_independent, fully)
        self.assertIn(p_dependent, boatswain.parameters)

    def test_generate_vs_success_with_all_reactant_branches(self):
        """
        Ensure generate_vs materializes a variable-space Point for each supported reactant mapping branch.
        """
        water_mass = ValueParameter(np.float64(1.0))
        temperature = ValueParameter(np.float64(25.0))
        pressure = ValueParameter(np.float64(1.0))
        na = ValueParameter(-np.float64(1.0))
        cl = ValueParameter(-np.float64(1.0))
        species = ValueParameter(np.float64(0.5))

        mineral = MineralReactant(
            name="calcite",
            amount=ValueParameter(-np.float64(3.0)),
            titration_rate=ValueParameter(np.float64(1.0)),
        )
        aqueous = AqueousReactant(
            name="na_cl",
            amount=ValueParameter(-np.float64(2.0)),
            titration_rate=ValueParameter(np.float64(1.0)),
        )
        gas = GasReactant(
            name="co2(g)",
            amount=ValueParameter(-np.float64(4.0)),
            titration_rate=ValueParameter(np.float64(1.0)),
        )
        element = ElementReactant(
            name="Na",
            amount=ValueParameter(-np.float64(6.0)),
            titration_rate=ValueParameter(np.float64(1.0)),
        )
        special = SpecialReactant(
            name="seawater",
            amount=ValueParameter(-np.float64(5.0)),
            titration_rate=ValueParameter(np.float64(1.0)),
            composition={"Na": 1, "Cl": 1},
        )
        fixed_gas = FixedGasReactant(
            name="co2",
            amount=ValueParameter(-np.float64(1.0)),
            fugacity=ValueParameter(-np.float64(2.0)),
        )
        solid = SolidSolutionReactant(
            name="solidmix",
            amount=ValueParameter(-np.float64(2.0)),
            titration_rate=ValueParameter(np.float64(1.0)),
            end_members={
                "em1": ValueParameter(np.float64(0.25)),
                "em2": ValueParameter(np.float64(0.75)),
            },
        )
        combined = CombinedReactant(
            name="combinedmix",
            amount=ValueParameter(-np.float64(1.0)),
            titration_rate=ValueParameter(np.float64(1.0)),
            components={
                "SiO2": CombinedReactantComponent(
                    name="SiO2",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.5),
                    relative_rate=ValueParameter(np.float64(1.0)),
                    composition={"Si": 1, "O": 2},
                ),
                "Na2O": CombinedReactantComponent(
                    name="Na2O",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.5),
                    relative_rate=ValueParameter(np.float64(1.0)),
                    composition={"Na": 2, "O": 1},
                ),
            },
        )

        reactants = [mineral, aqueous, gas, element, special, fixed_gas, solid, combined]
        params: list[Parameter] = [water_mass, temperature, pressure, na, cl, species]
        for reactant in reactants:
            params.extend(reactant.parameters())

        order = DummyOrder(
            parameters=params,
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={"Na": na, "Cl": cl},
            species={"Quartz(aq)": species},
            suppressions=[Suppression(name=None, type="mineral", exceptions=["Quartz"])],
            reactants=reactants,
        )
        boatswain = Boatswain(_as_order(order))

        point = boatswain.generate_vs(order_id=42)

        self.assertEqual(point.order_id, 42)
        self.assertEqual(len(point.elements), 2)
        self.assertEqual(len(point.species), 1)
        self.assertEqual(len(point.suppressions), 1)
        self.assertEqual(len(point.mineral_reactants), 1)
        self.assertEqual(len(point.aqueous_reactants), 1)
        self.assertEqual(len(point.gas_reactants), 1)
        self.assertEqual(len(point.element_reactants), 1)
        self.assertEqual(len(point.special_reactants), 3)
        self.assertEqual(len(point.fixed_gas_reactants), 1)
        self.assertEqual(len(point.solid_solution_reactants), 1)

    def test_generate_vs_propagates_non_default_water_mass(self):
        """
        Ensure generate_vs passes a non-default water_mass value through to the resulting Point.
        """
        water_mass = ValueParameter(np.float64(0.5))
        temperature = ValueParameter(np.float64(25.0))
        pressure = ValueParameter(np.float64(1.0))

        order = DummyOrder(
            parameters=[water_mass, temperature, pressure],
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(_as_order(order))
        point = boatswain.generate_vs()

        self.assertEqual(point.water_mass, 0.5)

    def test_generate_vs_combined_per_component_relative_rates(self):
        """
        Ensure generate_vs computes per-component absolute titration rates as base_rate * relative_rate.
        """
        water_mass = ValueParameter(np.float64(1.0))
        temperature = ValueParameter(np.float64(25.0))
        pressure = ValueParameter(np.float64(1.0))
        combined = CombinedReactant(
            name="combinedmix",
            amount=ValueParameter(-np.float64(1.0)),
            titration_rate=ValueParameter(np.float64(3.0)),
            components={
                "SiO2": CombinedReactantComponent(
                    name="SiO2",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.5),
                    relative_rate=ValueParameter(np.float64(2.0)),
                    composition={"Si": 1, "O": 2},
                ),
                "Na2O": CombinedReactantComponent(
                    name="Na2O",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.5),
                    relative_rate=ValueParameter(np.float64(0.5)),
                    composition={"Na": 2, "O": 1},
                ),
            },
        )

        params: list[Parameter] = [water_mass, temperature, pressure]
        params.extend(combined.parameters())

        order = DummyOrder(
            parameters=params,
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[combined],
        )
        boatswain = Boatswain(_as_order(order))
        point = boatswain.generate_vs()
        self.assertEqual(len(point.special_reactants), 2)
        by_name = {r.name: r for r in point.special_reactants}
        self.assertAlmostEqual(by_name["SiO2"].titration_rate, 6.0)
        self.assertAlmostEqual(by_name["Na2O"].titration_rate, 1.5)
        expected_log_moles = cast(np.float64, np.log10(np.float64(0.5))) + (-np.float64(1.0))
        self.assertAlmostEqual(by_name["SiO2"].log_moles, expected_log_moles)
        self.assertAlmostEqual(by_name["Na2O"].log_moles, expected_log_moles)

    def test_generate_vs_combined_proportional_component_rates(self):
        """
        Ensure generate_vs falls back to fraction-proportional rates when component relative_rate is omitted.
        """
        water_mass = ValueParameter(np.float64(1.0))
        temperature = ValueParameter(np.float64(25.0))
        pressure = ValueParameter(np.float64(1.0))
        combined = CombinedReactant(
            name="combinedmix",
            amount=ValueParameter(-np.float64(1.0)),
            titration_rate=ValueParameter(np.float64(3.0)),
            components={
                "SiO2": CombinedReactantComponent(
                    name="SiO2",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.5),
                    relative_rate=None,
                    composition={"Si": 1, "O": 2},
                ),
                "Na2O": CombinedReactantComponent(
                    name="Na2O",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.25),
                    relative_rate=None,
                    composition={"Na": 2, "O": 1},
                ),
                "FeO": CombinedReactantComponent(
                    name="FeO",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.25),
                    relative_rate=None,
                    composition={"Fe": 1, "O": 1},
                ),
            },
        )
        self.assertEqual(len(combined.parameters()), 2)

        params: list[Parameter] = [water_mass, temperature, pressure]
        params.extend(combined.parameters())

        order = DummyOrder(
            parameters=params,
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[combined],
        )
        point = Boatswain(_as_order(order)).generate_vs()
        self.assertEqual(len(point.special_reactants), 3)
        by_name = {r.name: r for r in point.special_reactants}
        self.assertAlmostEqual(by_name["SiO2"].titration_rate, 1.5)
        self.assertAlmostEqual(by_name["Na2O"].titration_rate, 0.75)
        self.assertAlmostEqual(by_name["FeO"].titration_rate, 0.75)

    def test_generate_vs_combined_special_parity_with_old_glass(self):
        """
        Ensure combined special-component expansion preserves the old glass decomposition math.
        """
        water_mass = ValueParameter(np.float64(1.0))
        temperature = ValueParameter(np.float64(25.0))
        pressure = ValueParameter(np.float64(1.0))
        combined = CombinedReactant(
            name="parity",
            amount=ValueParameter(-np.float64(1.0)),
            titration_rate=ValueParameter(np.float64(3.0)),
            components={
                "SiO2": CombinedReactantComponent(
                    name="SiO2",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.5),
                    relative_rate=ValueParameter(np.float64(2.0)),
                    composition={"Si": 1, "O": 2},
                ),
                "Na2O": CombinedReactantComponent(
                    name="Na2O",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.5),
                    relative_rate=ValueParameter(np.float64(0.5)),
                    composition={"Na": 2, "O": 1},
                ),
            },
        )
        order = DummyOrder(
            parameters=[water_mass, temperature, pressure, *combined.parameters()],
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[combined],
        )
        point = Boatswain(_as_order(order)).generate_vs()
        by_name = {r.name: r for r in point.special_reactants}
        expected_log_moles = cast(np.float64, np.log10(np.float64(0.5))) + (-np.float64(1.0))
        self.assertAlmostEqual(by_name["SiO2"].log_moles, expected_log_moles)
        self.assertAlmostEqual(by_name["Na2O"].log_moles, expected_log_moles)
        self.assertAlmostEqual(by_name["SiO2"].titration_rate, 6.0)
        self.assertAlmostEqual(by_name["Na2O"].titration_rate, 1.5)

    def test_generate_vs_combined_mixed_component_types(self):
        """
        Ensure combined components fan out into the correct concrete VS reactant lists.
        """
        water_mass = ValueParameter(np.float64(1.0))
        temperature = ValueParameter(np.float64(25.0))
        pressure = ValueParameter(np.float64(1.0))
        combined = CombinedReactant(
            name="mixed",
            amount=ValueParameter(-np.float64(2.0)),
            titration_rate=ValueParameter(np.float64(4.0)),
            components={
                "forsterite": CombinedReactantComponent(
                    name="forsterite",
                    type=ReactantType.MINERAL,
                    fraction=np.float64(0.4),
                    relative_rate=ValueParameter(np.float64(2.0)),
                ),
                "SiO2": CombinedReactantComponent(
                    name="SiO2",
                    type=ReactantType.SPECIAL,
                    fraction=np.float64(0.3),
                    relative_rate=ValueParameter(np.float64(1.0)),
                    composition={"Si": 1, "O": 2},
                ),
                "olivine-ss": CombinedReactantComponent(
                    name="olivine-ss",
                    type=ReactantType.SOLID_SOLUTION,
                    fraction=np.float64(0.3),
                    relative_rate=ValueParameter(np.float64(0.5)),
                    end_members={
                        "fayalite": ValueParameter(np.float64(0.7)),
                        "forsterite": ValueParameter(np.float64(0.3)),
                    },
                ),
            },
        )
        order = DummyOrder(
            parameters=[water_mass, temperature, pressure, *combined.parameters()],
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[combined],
        )
        point = Boatswain(_as_order(order)).generate_vs()

        self.assertEqual(len(point.mineral_reactants), 1)
        self.assertEqual(len(point.special_reactants), 1)
        self.assertEqual(len(point.solid_solution_reactants), 1)
        self.assertAlmostEqual(point.mineral_reactants[0].titration_rate, 8.0)
        self.assertAlmostEqual(point.special_reactants[0].titration_rate, 4.0)
        self.assertAlmostEqual(point.solid_solution_reactants[0].titration_rate, 2.0)

    def test_generate_vs_wraps_unexpected_reactant_and_unrefined_errors(self):
        """
        Ensure generate_vs wraps internal errors for unknown reactants and unrefined parameters.
        """
        water_mass = ValueParameter(np.float64(1.0))
        temperature = ValueParameter(np.float64(25.0))
        pressure = ValueParameter(np.float64(1.0))
        na = ValueParameter(-np.float64(1.0))

        order_bad_reactant = DummyOrder(
            parameters=[water_mass, temperature, pressure, na],
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={"Na": na},
            species={},
            suppressions=[],
            reactants=[object()],  # pyright: ignore[reportArgumentType]
        )
        boatswain_bad_reactant = Boatswain(_as_order(order_bad_reactant))
        with self.assertRaises(Exception):
            _ = boatswain_bad_reactant.generate_vs()

        p_unrefined = RangeParameter(np.float64(0.0), np.float64(1.0))
        order_unrefined = DummyOrder(
            parameters=[water_mass, temperature, pressure, p_unrefined],
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={"u": p_unrefined},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain_unrefined = Boatswain(_as_order(order_unrefined))
        with self.assertRaises(Exception):
            _ = boatswain_unrefined.generate_vs()

    def test_linear_constraint_term_label(self):
        """
        Verify :meth:`LinearConstraintTerm.label` returns the stored name when set
        and falls back to the hex-id sentinel when the name is empty.
        """
        p = ValueParameter(np.float64(1.0))
        named_term = LinearConstraintTerm(p, np.float64(1.0), Transform.IDENTITY, name="elements[key=Na]")
        self.assertEqual(named_term.label(), "elements[key=Na]")

        unnamed_term = LinearConstraintTerm(p, np.float64(1.0), Transform.IDENTITY)
        fallback = unnamed_term.label()
        self.assertRegex(fallback, r"^<unnamed term @[0-9a-f]+>$")

    def test_linear_constraint_apply_constant_not_resolved(self):
        """
        Verify apply raises when the constant parameter is not yet a ValueParameter.
        """
        p = ValueParameter(np.float64(5.0))
        range_constant = RangeParameter(np.float64(0.0), np.float64(10.0))
        lc = LinearConstraint(
            [LinearConstraintTerm(p, np.float64(1.0), Transform.IDENTITY)],
            constant=range_constant,
        )
        registry = ParameterRegistry()
        registry.add_parameters([p, range_constant])
        valuation = registry.valuation()
        with self.assertRaisesRegex(EleanorException, "constant parameter is not resolved"):
            _ = lc.apply(registry, valuation)

    def test_linear_constraint_apply_all_fixed_not_resolved_message(self):
        """
        Verify apply raises with the correct label when all terms are fixed (no dependent)
        but the valuation contains an unresolved entry for one of the independent terms.
        """
        p = ValueParameter(np.float64(1.0))
        constant = ValueParameter(np.float64(1.0))
        term = LinearConstraintTerm(p, np.float64(1.0), Transform.IDENTITY, name="pressure")
        lc = LinearConstraint([term], constant=constant)
        registry = ParameterRegistry()
        registry.add_parameters([p, constant])
        valuation = registry.valuation()
        valuation[registry.id(p)] = RangeParameter(np.float64(0.0), np.float64(2.0))
        with self.assertRaisesRegex(EleanorException, "parameter 'pressure' is not resolved"):
            _ = lc.apply(registry, valuation)

    def test_linear_constraint_apply_independent_not_resolved_message(self):
        """
        Verify apply raises with the unnamed-term fallback label when an independent
        RangeParameter is not yet resolved and no name was supplied to the term.
        """
        p_dep = RangeParameter(np.float64(0.0), np.float64(100.0))
        p_ind = RangeParameter(np.float64(0.0), np.float64(1.0))
        constant = ValueParameter(np.float64(0.0))
        lc = LinearConstraint(
            [
                LinearConstraintTerm(p_dep, np.float64(1.0), Transform.IDENTITY),
                LinearConstraintTerm(p_ind, np.float64(1.0), Transform.IDENTITY),
            ],
            constant=constant,
        )
        registry = ParameterRegistry()
        registry.add_parameters([p_dep, p_ind, constant])
        valuation = registry.valuation()
        with self.assertRaisesRegex(
            EleanorException,
            r"independent parameter '<unnamed term @[0-9a-f]+>' is not resolved",
        ):
            _ = lc.apply(registry, valuation)

    def test_linear_constraint_from_order_full_variable_path_in_error(self):
        """
        Verify that a LinearConstraint built via from_order embeds the full variable
        path (e.g. 'elements[key=Na]') in the diagnostic message when the independent
        term is not yet resolved, not merely the leaf name.
        """
        temp = RangeParameter(np.float64(10.0), np.float64(100.0))
        na = RangeParameter(np.float64(-2.0), np.float64(0.0))
        order = DummyOrder(
            parameters=[temp, na],
            temperature=temp,
            pressure=ValueParameter(np.float64(1.0)),
            elements={"Na": na},
            species={},
            suppressions=[],
            reactants=[],
        )
        raw: dict[str, object] = {
            "type": "linear",
            "terms": [
                {"variable": "temperature", "coefficient": 1.0},
                {"variable": "elements[key=Na]", "coefficient": -1.0},
            ],
        }
        lc = LinearConstraint.from_order(_as_order(order), ConstraintConfig(type="linear", args=raw))
        self.assertIsInstance(lc, LinearConstraint)

        registry = ParameterRegistry()
        registry.add_parameters([temp, na, lc.constant])
        valuation = registry.valuation()
        with self.assertRaisesRegex(EleanorException, r"elements\[key=Na\]"):
            _ = lc.apply(registry, valuation)
