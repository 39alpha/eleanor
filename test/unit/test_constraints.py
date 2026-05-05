from dataclasses import dataclass
from typing import cast, override
from unittest import mock

import numpy as np

from eleanor.constraints import AbstractConstraint, Boatswain
from eleanor.kernel.config import Config as KernelConfig
from eleanor.kernel.config import Settings
from eleanor.order import ConstraintConfig, Order
from eleanor.parameters import Parameter, ParameterRegistry, RangeParameter, Valuation, ValueParameter
from eleanor.reactants import (
    AqueousReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    GlassReactant,
    GlassReactantOxide,
    MineralReactant,
    ReactantType,
    SolidSolutionReactant,
    SpecialReactant,
)

from .common import TestCase


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


@dataclass
class DummySuppression:
    name: str | None
    type: str | None
    exceptions: list[str]


class DummyOrder:
    """
    Minimal order-like object used to exercise Boatswain logic.
    """

    def __init__(
        self, *, parameters, water_mass=None, temperature, pressure, elements, species, suppressions, reactants
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
        p_ind = ValueParameter("ind", None, np.float64(1.0))
        p_dep = RangeParameter("dep", None, np.float64(0.0), np.float64(10.0))
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
        p_ind = RangeParameter("ind", None, np.float64(0.0), np.float64(1.0))
        p_dep = RangeParameter("dep", None, np.float64(0.0), np.float64(1.0))
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
        dummy_constraint_config = cast(ConstraintConfig, object())
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

    def test_boatswain_get_set_hardset_and_domain_errors(self):
        """
        Ensure Boatswain item access and refinement checks enforce registry/domain constraints.
        """
        temp = RangeParameter("temperature", None, np.float64(10.0), np.float64(20.0))
        pressure = ValueParameter("pressure", None, np.float64(1.0))
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
            boatswain[ValueParameter("missing", None, np.float64(1.0))] = ValueParameter(
                "missing", None, np.float64(1.0)
            )

        with self.assertRaises(Exception):
            boatswain[temp] = temp.fix(np.float64(50.0))

        boatswain.hardset(temp, temp.fix(np.float64(11.0)))
        with self.assertRaises(Exception):
            boatswain[temp] = temp.fix(np.float64(12.0))

    def test_boatswain_setitem_parameter_id_not_in_valuations(self):
        """
        Ensure setitem raises when registry returns an unknown parameter id.
        """
        temp = RangeParameter("temperature", None, np.float64(10.0), np.float64(20.0))
        pressure = ValueParameter("pressure", None, np.float64(1.0))
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
        p_fixed = ValueParameter("fixed", None, np.float64(1.0))
        p_target = RangeParameter("target", None, np.float64(0.0), np.float64(5.0))
        p_other = RangeParameter("other", None, np.float64(10.0), np.float64(20.0))

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
        p_fixed = ValueParameter("fixed", None, np.float64(1.0))
        p_independent = RangeParameter("independent", None, np.float64(0.0), np.float64(5.0))
        p_dependent = RangeParameter("dependent", None, np.float64(10.0), np.float64(20.0))
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
        water_mass = ValueParameter("water_mass", None, np.float64(1.0))
        temperature = ValueParameter("temperature", None, np.float64(25.0))
        pressure = ValueParameter("pressure", None, np.float64(1.0))
        na = ValueParameter("Na", None, -np.float64(1.0))
        cl = ValueParameter("Cl", None, -np.float64(1.0))
        species = ValueParameter("Quartz(aq)", None, np.float64(0.5))

        mineral = MineralReactant(
            "calcite",
            ReactantType.MINERAL,
            ValueParameter("amount", None, -np.float64(3.0)),
            ValueParameter("titration_rate", None, np.float64(1.0)),
        )
        aqueous = AqueousReactant(
            "na_cl",
            ReactantType.AQUEOUS,
            ValueParameter("amount", None, -np.float64(2.0)),
            ValueParameter("titration_rate", None, np.float64(1.0)),
        )
        gas = GasReactant(
            "co2(g)",
            ReactantType.GAS,
            ValueParameter("amount", None, -np.float64(4.0)),
            ValueParameter("titration_rate", None, np.float64(1.0)),
        )
        element = ElementReactant(
            "Na",
            ReactantType.ELEMENT,
            ValueParameter("amount", None, -np.float64(6.0)),
            ValueParameter("titration_rate", None, np.float64(1.0)),
        )
        special = SpecialReactant(
            "seawater",
            ReactantType.SPECIAL,
            ValueParameter("amount", None, -np.float64(5.0)),
            ValueParameter("titration_rate", None, np.float64(1.0)),
            {"Na": 1, "Cl": 1},
        )
        fixed_gas = FixedGasReactant(
            "co2",
            ReactantType.FIXED_GAS,
            ValueParameter("amount", None, -np.float64(1.0)),
            ValueParameter("fugacity", None, -np.float64(2.0)),
        )
        solid = SolidSolutionReactant(
            "solidmix",
            ReactantType.SOLID_SOLUTION,
            ValueParameter("amount", None, -np.float64(2.0)),
            ValueParameter("titration_rate", None, np.float64(1.0)),
            {
                "em1": ValueParameter("fraction", None, np.float64(0.25)),
                "em2": ValueParameter("fraction", None, np.float64(0.75)),
            },
        )
        glass = GlassReactant(
            "glassmix",
            ReactantType.GLASS,
            ValueParameter("amount", None, -np.float64(1.0)),
            ValueParameter("titration_rate", None, np.float64(1.0)),
            {
                "SiO2": GlassReactantOxide(
                    "SiO2", {"Si": 1, "O": 2}, np.float64(0.5), ValueParameter("relative_rate", None, np.float64(1.0))
                ),
                "Na2O": GlassReactantOxide(
                    "Na2O", {"Na": 2, "O": 1}, np.float64(0.5), ValueParameter("relative_rate", None, np.float64(1.0))
                ),
            },
        )

        reactants = [mineral, aqueous, gas, element, special, fixed_gas, solid, glass]
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
            suppressions=[DummySuppression(name=None, type="mineral", exceptions=["Quartz"])],
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
        self.assertEqual(len(point.special_reactants), 1)
        self.assertEqual(len(point.fixed_gas_reactants), 1)
        self.assertEqual(len(point.solid_solution_reactants), 1)
        self.assertEqual(len(point.glass_reactants), 1)

    def test_generate_vs_propagates_non_default_water_mass(self):
        """
        Ensure generate_vs passes a non-default water_mass value through to the resulting Point.
        """
        water_mass = ValueParameter("water_mass", None, np.float64(0.5))
        temperature = ValueParameter("temperature", None, np.float64(25.0))
        pressure = ValueParameter("pressure", None, np.float64(1.0))

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

    def test_generate_vs_glass_per_oxide_relative_rates(self):
        """
        Ensure generate_vs computes per-oxide absolute titration rates as base_rate * relative_rate.
        """
        water_mass = ValueParameter("water_mass", None, np.float64(1.0))
        temperature = ValueParameter("temperature", None, np.float64(25.0))
        pressure = ValueParameter("pressure", None, np.float64(1.0))

        sio2_rate = ValueParameter("relative_rate", None, np.float64(2.0))
        na2o_rate = ValueParameter("relative_rate", None, np.float64(0.5))
        glass = GlassReactant(
            "glassmix",
            ReactantType.GLASS,
            ValueParameter("amount", None, -np.float64(1.0)),
            ValueParameter("titration_rate", None, np.float64(3.0)),
            {
                "SiO2": GlassReactantOxide("SiO2", {"Si": 1, "O": 2}, np.float64(0.5), sio2_rate),
                "Na2O": GlassReactantOxide("Na2O", {"Na": 2, "O": 1}, np.float64(0.5), na2o_rate),
            },
        )

        params: list[Parameter] = [water_mass, temperature, pressure]
        params.extend(glass.parameters())

        order = DummyOrder(
            parameters=params,
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[glass],
        )
        boatswain = Boatswain(_as_order(order))
        point = boatswain.generate_vs()

        self.assertEqual(len(point.glass_reactants), 1)
        gl = point.glass_reactants[0]
        self.assertEqual(gl.titration_rate, 3.0)

        oxide_rates = {o.name: o.titration_rate for o in gl.oxides}
        self.assertAlmostEqual(oxide_rates["SiO2"], 3.0 * 2.0)
        self.assertAlmostEqual(oxide_rates["Na2O"], 3.0 * 0.5)

    def test_generate_vs_wraps_unexpected_reactant_and_unrefined_errors(self):
        """
        Ensure generate_vs wraps internal errors for unknown reactants and unrefined parameters.
        """
        water_mass = ValueParameter("water_mass", None, np.float64(1.0))
        temperature = ValueParameter("temperature", None, np.float64(25.0))
        pressure = ValueParameter("pressure", None, np.float64(1.0))
        na = ValueParameter("Na", None, -np.float64(1.0))

        order_bad_reactant = DummyOrder(
            parameters=[water_mass, temperature, pressure, na],
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements={"Na": na},
            species={},
            suppressions=[],
            reactants=[object()],
        )
        boatswain_bad_reactant = Boatswain(_as_order(order_bad_reactant))
        with self.assertRaises(Exception):
            boatswain_bad_reactant.generate_vs()

        p_unrefined = RangeParameter("unrefined", None, np.float64(0.0), np.float64(1.0))
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
            boatswain_unrefined.generate_vs()
