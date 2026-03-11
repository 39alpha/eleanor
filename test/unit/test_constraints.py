from dataclasses import dataclass
from unittest import mock

from eleanor.constraints import AbstractConstraint, Boatswain
from eleanor.kernel.config import Config as KernelConfig
from eleanor.kernel.config import Settings
from eleanor.parameters import ParameterRegistry, RangeParameter, ValueParameter
from eleanor.reactants import (
    AqueousReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
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

    def __init__(self, independent, dependent, value):
        self._independent = independent
        self._dependent = dependent
        self._value = value

    @property
    def independent_parameters(self):
        return [self._independent]

    @property
    def dependent_parameters(self):
        return [self._dependent]

    def apply(self, registry, _valuation):
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

    def __init__(self, *, parameters, temperature, pressure, elements, species, suppressions, reactants):
        self._parameters = parameters
        self.constraints = []
        self.temperature = temperature
        self.pressure = pressure
        self.elements = elements
        self.species = species
        self.suppressions = suppressions
        self.reactants = reactants
        self.kernel = KernelConfig(type="eq36", settings=Settings(timeout=1))

    def parameters(self):
        return self._parameters


class TestConstraints(TestCase):
    """
    Tests of the eleanor.constraints module.
    """

    def test_abstract_constraint_dependency_and_resolution(self):
        """
        Ensure dependency checks and resolution gatekeeping behave as expected.
        """
        p_ind = ValueParameter("ind", None, 1.0)
        p_dep = RangeParameter("dep", None, 0.0, 10.0)
        registry = ParameterRegistry()
        registry.add_parameters([p_ind, p_dep])
        valuation = registry.valuation()
        constraint = EchoConstraint(p_ind, p_dep, 2.5)

        self.assertTrue(constraint.depends_on(p_ind))
        self.assertTrue(constraint.constrains(p_dep))
        self.assertTrue(constraint.is_resolvable(registry, valuation))

        constraint.resolve(registry, valuation)
        self.assertEqual(valuation[registry.id(p_dep)].value, 2.5)

    def test_abstract_constraint_unresolvable_raises(self):
        """
        Ensure resolving with unresolved independent parameters raises.
        """
        p_ind = RangeParameter("ind", None, 0.0, 1.0)
        p_dep = RangeParameter("dep", None, 0.0, 1.0)
        registry = ParameterRegistry()
        registry.add_parameters([p_ind, p_dep])
        valuation = registry.valuation()
        constraint = EchoConstraint(p_ind, p_dep, 0.5)

        self.assertFalse(constraint.is_resolvable(registry, valuation))
        with self.assertRaises(Exception):
            constraint.resolve(registry, valuation)

    def test_abstract_constraint_from_order_placeholder(self):
        """
        Ensure placeholder :meth:`AbstractConstraint.from_order` is executable.
        """
        self.assertIsNone(AbstractConstraint.from_order(object(), object()))

    def test_abstract_constraint_placeholder_methods_are_executable(self):
        """
        Ensure abstract placeholder bodies can be executed directly.
        """
        self.assertIsNone(AbstractConstraint.independent_parameters.fget(object()))
        self.assertIsNone(AbstractConstraint.dependent_parameters.fget(object()))
        self.assertIsNone(AbstractConstraint.apply(object(), object(), object()))

    def test_boatswain_get_set_hardset_and_domain_errors(self):
        """
        Ensure Boatswain item access and refinement checks enforce registry/domain constraints.
        """
        temp = RangeParameter("temperature", None, 10.0, 20.0)
        pressure = ValueParameter("pressure", None, 1.0)
        order = DummyOrder(
            parameters=[temp, pressure],
            temperature=temp.fix(15.0),
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(order)

        self.assertEqual(boatswain[temp].min, 10.0)
        boatswain[temp] = temp.fix(12.0)
        self.assertEqual(boatswain[temp].value, 12.0)

        with self.assertRaises(Exception):
            boatswain[ValueParameter("missing", None, 1.0)] = ValueParameter("missing", None, 1.0)

        with self.assertRaises(Exception):
            boatswain[temp] = temp.fix(50.0)

        boatswain.hardset(temp, temp.fix(11.0))
        with self.assertRaises(Exception):
            boatswain[temp] = temp.fix(12.0)

    def test_boatswain_setitem_parameter_id_not_in_valuations(self):
        """
        Ensure setitem raises when registry returns an unknown parameter id.
        """
        temp = RangeParameter("temperature", None, 10.0, 20.0)
        pressure = ValueParameter("pressure", None, 1.0)
        order = DummyOrder(
            parameters=[temp, pressure],
            temperature=temp.fix(15.0),
            pressure=pressure,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(order)
        with mock.patch.object(boatswain.registry, "id", return_value=999):
            with self.assertRaises(Exception):
                boatswain[temp] = temp.fix(12.0)

    def test_boatswain_constrain_tracks_fully_and_under_constrained(self):
        """
        Ensure constrain resolves what it can and returns fully constrained non-value parameters.
        """
        p_fixed = ValueParameter("fixed", None, 1.0)
        p_target = RangeParameter("target", None, 0.0, 5.0)
        p_other = RangeParameter("other", None, 10.0, 20.0)

        order = DummyOrder(
            parameters=[p_fixed, p_target, p_other],
            temperature=p_fixed,
            pressure=p_fixed,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        c_resolvable = EchoConstraint(p_fixed, p_target, 3.0)
        c_unresolved = EchoConstraint(p_other, p_target, 2.0)

        boatswain = Boatswain(order, c_resolvable, c_unresolved)
        fully = boatswain.constrain()

        self.assertIn(p_other, fully)
        self.assertEqual(len(boatswain.constraints), 1)
        self.assertIs(boatswain.constraints[0], c_unresolved)
        self.assertEqual(boatswain[p_target].value, 3.0)
        self.assertEqual(boatswain.parameters, [])

    def test_boatswain_constrain_tracks_under_constrained_branch(self):
        """
        Ensure parameters constrained by unresolved constraints are tracked as under-constrained.
        """
        p_fixed = ValueParameter("fixed", None, 1.0)
        p_independent = RangeParameter("independent", None, 0.0, 5.0)
        p_dependent = RangeParameter("dependent", None, 10.0, 20.0)
        unresolved = EchoConstraint(p_independent, p_dependent, 15.0)

        order = DummyOrder(
            parameters=[p_fixed, p_independent, p_dependent],
            temperature=p_fixed,
            pressure=p_fixed,
            elements={},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain = Boatswain(order, unresolved)
        fully = boatswain.constrain()

        self.assertIn(p_independent, fully)
        self.assertIn(p_dependent, boatswain.parameters)

    def test_generate_vs_success_with_all_reactant_branches(self):
        """
        Ensure generate_vs materializes a variable-space Point for each supported reactant mapping branch.
        """
        temperature = ValueParameter("temperature", None, 25.0)
        pressure = ValueParameter("pressure", None, 1.0)
        na = ValueParameter("Na", None, -1.0)
        cl = ValueParameter("Cl", None, -1.0)
        species = ValueParameter("Quartz(aq)", None, 0.5)

        mineral = MineralReactant("calcite", ReactantType.MINERAL, ValueParameter("amount", None, -3.0), ValueParameter("titration_rate", None, 1.0))
        aqueous = AqueousReactant("na_cl", ReactantType.AQUEOUS, ValueParameter("amount", None, -2.0), ValueParameter("titration_rate", None, 1.0))
        gas = GasReactant("co2(g)", ReactantType.GAS, ValueParameter("amount", None, -4.0), ValueParameter("titration_rate", None, 1.0))
        element = ElementReactant("Na", ReactantType.ELEMENT, ValueParameter("amount", None, -6.0), ValueParameter("titration_rate", None, 1.0))
        special = SpecialReactant("seawater", ReactantType.SPECIAL, ValueParameter("amount", None, -5.0), ValueParameter("titration_rate", None, 1.0), {"Na": 1, "Cl": 1})
        fixed_gas = FixedGasReactant("co2", ReactantType.FIXED_GAS, ValueParameter("amount", None, -1.0), ValueParameter("fugacity", None, -2.0))
        solid = SolidSolutionReactant(
            "solidmix",
            ReactantType.SOLID_SOLUTION,
            ValueParameter("amount", None, -2.0),
            ValueParameter("titration_rate", None, 1.0),
            {"em1": ValueParameter("fraction", None, 0.25), "em2": ValueParameter("fraction", None, 0.75)},
        )

        reactants = [mineral, aqueous, gas, element, special, fixed_gas, solid]
        params = [temperature, pressure, na, cl, species]
        for reactant in reactants:
            params.extend(reactant.parameters())

        order = DummyOrder(
            parameters=params,
            temperature=temperature,
            pressure=pressure,
            elements={"Na": na, "Cl": cl},
            species={"Quartz(aq)": species},
            suppressions=[DummySuppression(name=None, type="mineral", exceptions=["Quartz"])],
            reactants=reactants,
        )
        boatswain = Boatswain(order)

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

    def test_generate_vs_wraps_unexpected_reactant_and_unrefined_errors(self):
        """
        Ensure generate_vs wraps internal errors for unknown reactants and unrefined parameters.
        """
        temperature = ValueParameter("temperature", None, 25.0)
        pressure = ValueParameter("pressure", None, 1.0)
        na = ValueParameter("Na", None, -1.0)

        order_bad_reactant = DummyOrder(
            parameters=[temperature, pressure, na],
            temperature=temperature,
            pressure=pressure,
            elements={"Na": na},
            species={},
            suppressions=[],
            reactants=[object()],
        )
        boatswain_bad_reactant = Boatswain(order_bad_reactant)
        with self.assertRaises(Exception):
            boatswain_bad_reactant.generate_vs()

        p_unrefined = RangeParameter("unrefined", None, 0.0, 1.0)
        order_unrefined = DummyOrder(
            parameters=[temperature, pressure, p_unrefined],
            temperature=temperature,
            pressure=pressure,
            elements={"u": p_unrefined},
            species={},
            suppressions=[],
            reactants=[],
        )
        boatswain_unrefined = Boatswain(order_unrefined)
        with self.assertRaises(Exception):
            boatswain_unrefined.generate_vs()
