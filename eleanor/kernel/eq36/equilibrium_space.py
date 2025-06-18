import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy.orm import declared_attr

import eleanor.equilibrium_space as es
from eleanor.equilibrium_space import AqueousSpecies, Element, Gas, PureSolid, Reactant, RedoxReaction, SolidSolution
from eleanor.typing import Any, Optional
from eleanor.yeoman import yeoman_registry


class Point(es.Point):
    __mapper_args__: dict[str, Any] = {
        'polymorphic_abstract': True,
    }


@yeoman_registry.mapped_as_dataclass(init=False)
class Eq3Point(Point):

    @declared_attr
    def __mapper_args__(cls):
        return {
            'polymorphic_identity': 'eq3',
        }

    def __init__(
        self,
        temperature: float,
        pressure: float,
        log_fO2: float,
        log_activity_water: float,
        mole_fraction_water: float,
        log_gamma_water: float,
        osmotic_coefficient: float,
        stoichiometric_osmotic_coefficient: float,
        log_sum_molalities: float,
        log_sum_stoichiometric_molalities: float,
        log_ionic_strength: float,
        log_stoichiometric_ionic_strength: float,
        log_ionic_asymmetry: float,
        log_stoichiometric_ionic_asymmetry: float,
        solvent_mass: float,
        solute_mass: float,
        solution_mass: float,
        solution_volume: float,
        solvent_fraction: float,
        solute_fraction: float,
        tds_mass: float,
        pH: float,
        Eh: float,
        pe: float,
        Ah: float,
        pcH: float,
        pHCl: float,
        cations: float,
        anions: float,
        total_charge: float,
        mean_charge: float,
        charge_imbalance: float,
        elements: list[Element],
        aqueous_species: list[AqueousSpecies],
        pure_solids: list[PureSolid],
        solid_solutions: list[SolidSolution],
        gases: list[Gas],
        redox_reactions: list[RedoxReaction],
        id: Optional[int] = None,
        variable_space_id: Optional[int] = None,
        extended_alkalinity: Optional[float] = None,
        start_date: Optional[datetime] = None,
        complete_date: Optional[datetime] = None,
    ):
        self.temperature = temperature
        self.pressure = pressure
        self.log_fO2 = log_fO2
        self.log_activity_water = log_activity_water
        self.mole_fraction_water = mole_fraction_water
        self.log_gamma_water = log_gamma_water
        self.osmotic_coefficient = osmotic_coefficient
        self.stoichiometric_osmotic_coefficient = stoichiometric_osmotic_coefficient
        self.log_sum_molalities = log_sum_molalities
        self.log_sum_stoichiometric_molalities = log_sum_stoichiometric_molalities
        self.log_ionic_strength = log_ionic_strength
        self.log_stoichiometric_ionic_strength = log_stoichiometric_ionic_strength
        self.log_ionic_asymmetry = log_ionic_asymmetry
        self.log_stoichiometric_ionic_asymmetry = log_stoichiometric_ionic_asymmetry
        self.solvent_mass = solvent_mass
        self.solute_mass = solute_mass
        self.solution_mass = solution_mass
        self.solution_volume = solution_volume
        self.solvent_fraction = solvent_fraction
        self.solute_fraction = solute_fraction
        self.tds_mass = tds_mass
        self.pH = pH
        self.Eh = Eh
        self.pe = pe
        self.Ah = Ah
        self.pHCl = pHCl
        self.pcH = pcH
        self.pHCl = pHCl
        self.cations = cations
        self.anions = anions
        self.total_charge = total_charge
        self.mean_charge = mean_charge
        self.charge_imbalance = charge_imbalance

        self.elements = elements
        self.aqueous_species = aqueous_species
        self.pure_solids = pure_solids
        self.solid_solutions = solid_solutions
        self.gases = gases
        self.reactants = []
        self.redox_reactions = redox_reactions
        self.extended_alkalinity = extended_alkalinity

        self.id = id
        self.variable_space_id = id
        self.start_date = start_date
        self.complete_date = complete_date


@yeoman_registry.mapped_as_dataclass(init=False)
class Eq6Point(Point):

    @declared_attr
    def __mapper_args__(cls):
        return {
            'polymorphic_identity': 'eq6',
        }

    def __init__(
        self,
        log_xi: float,
        temperature: float,
        pressure: float,
        pH: float,
        Eh: float,
        pe: float,
        Ah: float,
        pHCl: float,
        log_fO2: float,
        log_activity_water: float,
        mole_fraction_water: float,
        log_gamma_water: float,
        osmotic_coefficient: float,
        stoichiometric_osmotic_coefficient: float,
        log_sum_molalities: float,
        log_sum_stoichiometric_molalities: float,
        log_ionic_strength: float,
        log_stoichiometric_ionic_strength: float,
        log_ionic_asymmetry: float,
        log_stoichiometric_ionic_asymmetry: float,
        solvent_mass: float,
        solute_mass: float,
        solution_mass: float,
        solvent_fraction: float,
        solute_fraction: float,
        tds_mass: float,
        charge_imbalance: float,
        expected_charge_imbalance: float,
        charge_discrepancy: float,
        sigma: float,
        reactant_mass_reacted: float,
        reactant_mass_remaining: float,
        solid_mass_created: float,
        solid_mass_destroyed: float,
        solid_mass_change: float,
        solid_volume_created: float,
        solid_volume_destroyed: float,
        solid_volume_change: float,
        elements: list[Element],
        aqueous_species: list[AqueousSpecies],
        pure_solids: list[PureSolid],
        solid_solutions: list[SolidSolution],
        gases: list[Gas],
        reactants: list[Reactant],
        redox_reactions: list[RedoxReaction],
        id: Optional[int] = None,
        variable_space_id: Optional[int] = None,
        extended_alkalinity: Optional[float] = None,
        overall_affinity: Optional[float] = None,
        start_date: Optional[datetime] = None,
        complete_date: Optional[datetime] = None,
    ):
        self.log_xi = log_xi
        self.temperature = temperature
        self.pressure = pressure
        self.pH = pH
        self.Eh = Eh
        self.pe = pe
        self.Ah = Ah
        self.pHCl = pHCl
        self.log_fO2 = log_fO2
        self.log_activity_water = log_activity_water
        self.mole_fraction_water = mole_fraction_water
        self.log_gamma_water = log_gamma_water
        self.osmotic_coefficient = osmotic_coefficient
        self.stoichiometric_osmotic_coefficient = stoichiometric_osmotic_coefficient
        self.log_sum_molalities = log_sum_molalities
        self.log_sum_stoichiometric_molalities = log_sum_stoichiometric_molalities
        self.log_ionic_strength = log_ionic_strength
        self.log_stoichiometric_ionic_strength = log_stoichiometric_ionic_strength
        self.log_ionic_asymmetry = log_ionic_asymmetry
        self.log_stoichiometric_ionic_asymmetry = log_stoichiometric_ionic_asymmetry
        self.solvent_mass = solvent_mass
        self.solute_mass = solute_mass
        self.solution_mass = solution_mass
        self.solvent_fraction = solvent_fraction
        self.solute_fraction = solute_fraction
        self.tds_mass = tds_mass
        self.charge_imbalance = charge_imbalance
        self.expected_charge_imbalance = expected_charge_imbalance
        self.charge_discrepancy = charge_discrepancy
        self.sigma = sigma
        self.overall_affinity = overall_affinity
        self.reactant_mass_reacted = reactant_mass_reacted
        self.reactant_mass_remaining = reactant_mass_remaining
        self.solid_mass_created = solid_mass_created
        self.solid_mass_destroyed = solid_mass_destroyed
        self.solid_mass_change = solid_mass_change
        self.solid_volume_created = solid_volume_created
        self.solid_volume_destroyed = solid_volume_destroyed
        self.solid_volume_change = solid_volume_change

        self.elements = elements
        self.aqueous_species = aqueous_species
        self.pure_solids = pure_solids
        self.solid_solutions = solid_solutions
        self.gases = gases
        self.reactants = reactants
        self.redox_reactions = redox_reactions
        self.extended_alkalinity = extended_alkalinity

        self.id = id
        self.variable_space_id = id
        self.start_date = start_date
        self.complete_date = complete_date
