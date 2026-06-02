from dataclasses import dataclass, field
from datetime import datetime
from typing import final

import numpy as np


@final
@dataclass
class Element:
    name: str
    log_molality: np.float64
    mass_fraction: np.float64


@final
@dataclass
class AqueousSpecies:
    name: str
    log_molality: np.float64
    log_activity: np.float64
    log_gamma: np.float64


@final
@dataclass
class PureSolid:
    name: str
    log_qk: np.float64
    affinity: np.float64
    log_moles: np.float64 | None = None
    log_mass: np.float64 | None = None
    log_volume: np.float64 | None = None


@final
@dataclass
class EndMember:
    name: str
    log_qk: np.float64
    affinity: np.float64
    log_moles: np.float64 | None = None
    log_mass: np.float64 | None = None
    log_volume: np.float64 | None = None


@final
@dataclass
class SolidSolution:
    name: str
    log_qk: np.float64
    affinity: np.float64
    end_members: list[EndMember]
    log_moles: np.float64 | None = None
    log_mass: np.float64 | None = None
    log_volume: np.float64 | None = None


@final
@dataclass
class Gas:
    name: str
    log_fugacity: np.float64


@final
@dataclass
class Reactant:
    name: str
    affinity: np.float64
    relative_rate: np.float64
    log_moles_reacted: np.float64
    log_moles_remaining: np.float64
    log_mass_reacted: np.float64
    log_mass_remaining: np.float64


@final
@dataclass
class RedoxReaction:
    couple: str
    Eh: np.float64
    pe: np.float64
    log_fO2: np.float64
    Ah: np.float64


@final
@dataclass(kw_only=True)
class Point:
    stage: str
    temperature: np.float64
    pressure: np.float64
    pH: np.float64
    log_fO2: np.float64
    log_activity_water: np.float64
    mole_fraction_water: np.float64
    log_gamma_water: np.float64
    Eh: np.float64
    pe: np.float64
    Ah: np.float64
    log_ionic_strength: np.float64
    log_stoichiometric_ionic_strength: np.float64
    ionic_asymmetry: np.float64
    stoichiometric_ionic_asymmetry: np.float64
    osmotic_coefficient: np.float64
    stoichiometric_osmotic_coefficient: np.float64
    log_sum_molalities: np.float64
    log_sum_stoichiometric_molalities: np.float64
    charge_imbalance: np.float64
    solute_mass: np.float64
    solvent_mass: np.float64
    solution_mass: np.float64
    tds: np.float64
    solute_fraction: np.float64
    solvent_fraction: np.float64
    elements: list[Element]
    aqueous_species: list[AqueousSpecies]
    pure_solids: list[PureSolid]
    solid_solutions: list[SolidSolution]
    gases: list[Gas]
    redox_reactions: list[RedoxReaction]
    log_xi: np.float64 | None = None
    pcH: np.float64 | None = None
    pHCl: np.float64 | None = None
    solution_volume: np.float64 | None = None
    expected_charge_imbalance: np.float64 | None = None
    sigma: np.float64 | None = None
    charge_discrepancy: np.float64 | None = None
    anions: np.float64 | None = None
    cations: np.float64 | None = None
    total_charge: np.float64 | None = None
    mean_charge: np.float64 | None = None
    extended_alkalinity: np.float64 | None = None
    overall_affinity: np.float64 | None = None
    reactant_mass_reacted: np.float64 | None = None
    reactant_mass_remaining: np.float64 | None = None
    solid_mass_change: np.float64 | None = None
    solid_mass_created: np.float64 | None = None
    solid_mass_destroyed: np.float64 | None = None
    solid_volume_change: np.float64 | None = None
    solid_volume_created: np.float64 | None = None
    solid_volume_destroyed: np.float64 | None = None
    reactants: list[Reactant] = field(default_factory=list)
    start_date: datetime | None = None
    complete_date: datetime | None = None
    custom_properties: dict[str, object] = field(default_factory=dict)
