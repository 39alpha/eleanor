from dataclasses import dataclass, field
from datetime import datetime
from typing import final


@final
@dataclass
class Element(object):
    name: str
    log_molality: float
    mass_fraction: float


@final
@dataclass
class AqueousSpecies(object):
    name: str
    log_molality: float
    log_activity: float
    log_gamma: float


@final
@dataclass
class PureSolid(object):
    name: str
    log_qk: float
    affinity: float
    log_moles: float | None = None
    log_mass: float | None = None
    log_volume: float | None = None


@final
@dataclass
class EndMember(object):
    name: str
    log_qk: float
    affinity: float
    log_moles: float | None = None
    log_mass: float | None = None
    log_volume: float | None = None


@final
@dataclass
class SolidSolution(object):
    name: str
    log_qk: float
    affinity: float
    end_members: list[EndMember]
    log_moles: float | None = None
    log_mass: float | None = None
    log_volume: float | None = None


@final
@dataclass
class Gas(object):
    name: str
    log_fugacity: float


@final
@dataclass
class Reactant(object):
    name: str
    affinity: float
    relative_rate: float
    log_moles_reacted: float
    log_moles_remaining: float
    log_mass_reacted: float
    log_mass_remaining: float


@final
@dataclass
class RedoxReaction(object):
    couple: str
    Eh: float
    pe: float
    log_fO2: float
    Ah: float


@final
@dataclass(kw_only=True)
class Point(object):
    stage: str
    temperature: float
    pressure: float
    pH: float
    log_fO2: float
    log_activity_water: float
    mole_fraction_water: float
    log_gamma_water: float
    Eh: float
    pe: float
    Ah: float
    log_ionic_strength: float
    log_stoichiometric_ionic_strength: float
    log_ionic_asymmetry: float
    log_stoichiometric_ionic_asymmetry: float
    osmotic_coefficient: float
    stoichiometric_osmotic_coefficient: float
    log_sum_molalities: float
    log_sum_stoichiometric_molalities: float
    charge_imbalance: float
    solute_mass: float
    solvent_mass: float
    solution_mass: float
    tds: float
    solute_fraction: float
    solvent_fraction: float
    elements: list[Element]
    aqueous_species: list[AqueousSpecies]
    pure_solids: list[PureSolid]
    solid_solutions: list[SolidSolution]
    gases: list[Gas]
    redox_reactions: list[RedoxReaction]
    log_xi: float | None = None
    pcH: float | None = None
    pHCl: float | None = None
    solution_volume: float | None = None
    expected_charge_imbalance: float | None = None
    sigma: float | None = None
    charge_discrepancy: float | None = None
    anions: float | None = None
    cations: float | None = None
    total_charge: float | None = None
    mean_charge: float | None = None
    extended_alkalinity: float | None = None
    overall_affinity: float | None = None
    reactant_mass_reacted: float | None = None
    reactant_mass_remaining: float | None = None
    solid_mass_change: float | None = None
    solid_mass_created: float | None = None
    solid_mass_destroyed: float | None = None
    solid_volume_change: float | None = None
    solid_volume_created: float | None = None
    solid_volume_destroyed: float | None = None
    reactants: list[Reactant] = field(default_factory=list)
    start_date: datetime | None = None
    complete_date: datetime | None = None
    custom_properties: dict[str, object] = field(default_factory=dict)
