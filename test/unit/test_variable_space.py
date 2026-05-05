import numpy as np

from eleanor.kernel.config import Config as KernelConfig
from eleanor.kernel.config import Settings
from eleanor.variable_space import (
    AqueousReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    MineralReactant,
    Point,
    SolidSolutionReactant,
    SolidSolutionReactantEndMembers,
    SpecialReactant,
    SpecialReactantComposition,
    Species,
)

from .common import TestCase


class TestVariableSpace(TestCase):
    """
    Tests of the eleanor.variable_space module.
    """

    def _make_point(self, species=None, reactant_sizes=None):
        if species is None:
            species = []
        if reactant_sizes is None:
            reactant_sizes = [0, 0, 0, 0, 0, 0, 0]
        mineral = [
            MineralReactant(name=f"m{i}", log_moles=np.float64(0.0), titration_rate=np.float64(1.0))
            for i in range(reactant_sizes[0])
        ]
        aqueous = [
            AqueousReactant(name=f"a{i}", log_moles=np.float64(0.0), titration_rate=np.float64(1.0))
            for i in range(reactant_sizes[1])
        ]
        gas = [
            GasReactant(name=f"g{i}", log_moles=np.float64(0.0), titration_rate=np.float64(1.0))
            for i in range(reactant_sizes[2])
        ]
        element = [
            ElementReactant(name=f"e{i}", log_moles=np.float64(0.0), titration_rate=np.float64(1.0))
            for i in range(reactant_sizes[3])
        ]
        special = [
            SpecialReactant(
                name=f"s{i}",
                log_moles=np.float64(0.0),
                titration_rate=np.float64(1.0),
                composition=[SpecialReactantComposition(element="Na", count=1)],
            )
            for i in range(reactant_sizes[4])
        ]
        fixed_gas = [
            FixedGasReactant(name=f"fg{i}", log_moles=np.float64(0.0), log_fugacity=np.float64(0.0))
            for i in range(reactant_sizes[5])
        ]
        solid_solution = [
            SolidSolutionReactant(
                name=f"ss{i}",
                log_moles=np.float64(0.0),
                titration_rate=np.float64(1.0),
                end_members=[SolidSolutionReactantEndMembers(name="em", fraction=np.float64(1.0))],
            )
            for i in range(reactant_sizes[6])
        ]
        return Point(
            kernel=KernelConfig(type="eq36", settings=Settings(timeout=1)),
            water_mass=np.float64(1.0),
            temperature=np.float64(25.0),
            pressure=np.float64(1.0),
            elements=[],
            species=species,
            suppressions=[],
            mineral_reactants=mineral,
            aqueous_reactants=aqueous,
            gas_reactants=gas,
            element_reactants=element,
            special_reactants=special,
            fixed_gas_reactants=fixed_gas,
            solid_solution_reactants=solid_solution,
            glass_reactants=[],
        )

    def test_species_helpers(self):
        """
        Ensure species helper methods detect constraints and resolve species by name.
        """
        s1 = Species(name="H+", value=np.float64(1.0))
        s2 = Species(name="OH-", value=np.float64(2.0))
        p = self._make_point(species=[s1, s2])

        self.assertTrue(p.has_species_constraint("H+"))
        self.assertFalse(p.has_species_constraint("Na+"))
        self.assertIs(p.get_species("OH-"), s2)
        self.assertIsNone(p.get_species("Na+"))

    def test_reactant_count_and_has_reactants(self):
        """
        Ensure reactant counting and presence checks aggregate across all reactant lists.
        """
        p0 = self._make_point(reactant_sizes=[0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(p0.reactant_count(), 0)
        self.assertFalse(p0.has_reactants())

        p1 = self._make_point(reactant_sizes=[1, 2, 0, 3, 0, 0, 4])
        self.assertEqual(p1.reactant_count(), 10)
        self.assertTrue(p1.has_reactants())
