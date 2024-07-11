from dataclasses import dataclass, field

from .typing import Float


@dataclass(kw_only=True)
class Element(object):
    name: str
    log_molality: Float
    vs_id: int | None = None
    id: int | None = None


@dataclass(kw_only=True)
class AqueousSpecies(object):
    name: str
    log_molality: Float
    log_activity: Float
    vs_id: int | None = None
    id: int | None = None


@dataclass(kw_only=True)
class SolidPhase(object):
    type: str
    name: str
    log_qk: Float
    log_moles: Float | None = None
    end_member: str | None = None
    vs_id: int | None = None
    id: int | None = None


@dataclass(kw_only=True)
class Gas(object):
    name: str
    log_fugacity: Float
    vs_id: int | None = None
    id: int | None = None


@dataclass(kw_only=True)
class Result(object):
    stage: str
    temperature: Float
    pressure: Float
    pH: Float
    log_fO2: Float
    log_activity_water: Float
    ionic_strength: Float
    tds_mass: Float
    solution_mass: Float
    charge_imbalance: Float
    elements: list[Element]
    aqueous_species: list[AqueousSpecies]
    solid_phases: list[SolidPhase]
    gases: list[Gas]
    extended_alkalinity: Float | None = None
    initial_affinity: Float | None = None
    log_xi: Float | None = None
    vs_id: int | None = None
    id: int | None = None
