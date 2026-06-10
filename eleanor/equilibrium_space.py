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
    eh: np.float64
    pe: np.float64
    log_fo2: np.float64
    ah: np.float64


@final
@dataclass(kw_only=True)
class Point:
    stage: str
    temperature: np.float64
    pressure: np.float64
    ph: np.float64
    log_fo2: np.float64
    eh: np.float64
    log_activity_water: np.float64
    log_ionic_strength: np.float64
    solute_mass: np.float64
    solvent_mass: np.float64
    solution_mass: np.float64
    tds: np.float64
    elements: list[Element]
    aqueous_species: list[AqueousSpecies]
    pure_solids: list[PureSolid]
    solid_solutions: list[SolidSolution]
    gases: list[Gas]
    redox_reactions: list[RedoxReaction]
    log_xi: np.float64 | None = None
    reactant_mass_reacted: np.float64 | None = None
    reactant_mass_remaining: np.float64 | None = None
    reactants: list[Reactant] = field(default_factory=list)
    start_date: datetime | None = None
    complete_date: datetime | None = None
    custom_properties: dict[str, object] = field(default_factory=dict)
