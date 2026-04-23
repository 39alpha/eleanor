from eleanor.equilibrium_space import (
    AqueousSpecies,
    Element as ESElement,
    Gas,
    Point as ESPoint,
    PureSolid,
    RedoxReaction,
    SolidSolution,
)
from eleanor.kernel.config import Config as KernelConfig
from eleanor.kernel.eq36.settings import Eq3Config, Eq6Config, Settings as Eq36Settings
from eleanor.output.postgres.persistence import mappers
from eleanor.variable_space import (
    AqueousReactant,
    Element,
    GasReactant,
    MineralReactant,
    Point,
    Species,
    Suppression,
    SuppressionException,
)

from ..common import TestCase


class TestPostgresPersistenceMappers(TestCase):
    """
    Tests for core<->persistence mapper parity.
    """

    def _kernel_settings(self) -> Eq36Settings:
        return Eq36Settings(
            timeout=None,
            model='b-dot',
            charge_balance='Cl-',
            eq3_config=Eq3Config(),
            eq6_config=Eq6Config(),
        )

    def test_kernel_config_round_trip_rehydrates_concrete_settings(self):
        """
        Ensure mapper read paths turn persisted settings payloads back into concrete Settings objects.
        """
        config = KernelConfig(type='eq36', settings=self._kernel_settings())
        persisted = mappers.to_kernel_config_model(config)
        restored = mappers.from_kernel_config_model(persisted)

        self.assertEqual(restored.type, 'eq36')
        self.assertIsInstance(restored.settings, Eq36Settings)
        self.assertEqual(restored.settings.charge_balance, 'Cl-')

    def test_vs_point_round_trip_preserves_representative_nested_data(self):
        """
        Ensure representative nested variable/equilibrium-space payloads survive mapper round-trip conversion.
        """
        es_point = ESPoint(
            stage='eq3',
            temperature=25.0,
            pressure=1.0,
            pH=7.0,
            log_fO2=-60.0,
            log_activity_water=-0.01,
            mole_fraction_water=0.98,
            log_gamma_water=0.02,
            Eh=0.1,
            pe=4.0,
            Ah=1.2,
            log_ionic_strength=-2.0,
            log_stoichiometric_ionic_strength=-1.8,
            log_ionic_asymmetry=-2.2,
            log_stoichiometric_ionic_asymmetry=-2.1,
            osmotic_coefficient=0.8,
            stoichiometric_osmotic_coefficient=0.81,
            log_sum_molalities=-1.0,
            log_sum_stoichiometric_molalities=-0.9,
            charge_imbalance=0.0,
            solute_mass=0.1,
            solvent_mass=1.0,
            solution_mass=1.1,
            tds=100.0,
            solute_fraction=0.1,
            solvent_fraction=0.9,
            elements=[ESElement(name='Na', log_molality=-3.0, mass_fraction=0.2)],
            aqueous_species=[AqueousSpecies(name='Na+', log_molality=-1.0, log_activity=-1.1, log_gamma=0.2)],
            pure_solids=[PureSolid(name='Calcite', log_qk=0.2, affinity=1.0)],
            solid_solutions=[SolidSolution(name='SS', log_qk=0.1, affinity=0.2, end_members=[])],
            gases=[Gas(name='CO2(g)', log_fugacity=-3.0)],
            redox_reactions=[RedoxReaction(couple='O2/H2O', Eh=0.1, pe=4.0, log_fO2=-60.0, Ah=1.2)],
        )

        point = Point(
            kernel=KernelConfig(type='eq36', settings=self._kernel_settings()),
            water_mass=1.0,
            temperature=25.0,
            pressure=1.0,
            elements=[Element(name='Na', log_molality=-3.0)],
            species=[Species(name='H+', value=-7.0)],
            suppressions=[Suppression(name='Quartz', type=None, exceptions=[SuppressionException(name='Calcite')])],
            mineral_reactants=[MineralReactant(name='Calcite', log_moles=0.0, titration_rate=1.0)],
            aqueous_reactants=[AqueousReactant(name='Na+', log_moles=0.0, titration_rate=1.0)],
            gas_reactants=[GasReactant(name='CO2(g)', log_moles=0.0, titration_rate=1.0)],
            element_reactants=[],
            special_reactants=[],
            fixed_gas_reactants=[],
            solid_solution_reactants=[],
            glass_reactants=[],
            es_points=[es_point],
        )

        persisted = mappers.to_vs_point_model(point, order_id=7)
        restored = mappers.from_vs_point_model(persisted)

        self.assertEqual(restored.order_id, 7)
        self.assertEqual(len(restored.elements), 1)
        self.assertEqual(restored.elements[0].name, 'Na')
        self.assertEqual(len(restored.suppressions), 1)
        self.assertEqual(restored.suppressions[0].exceptions[0].name, 'Calcite')
        self.assertEqual(len(restored.es_points), 1)
        self.assertEqual(restored.es_points[0].stage, 'eq3')
