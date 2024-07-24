import datetime
import json
from dataclasses import asdict, dataclass, field

from sqlalchemy import BLOB, CheckConstraint, Column, DateTime, Double, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import declared_attr, relationship

import eleanor.config.reactant as reactant
import eleanor.config.suppression as suppression
from eleanor.models import ESPoint as BaseESPoint
from eleanor.typing import Any, Optional
from eleanor.yeoman import yeoman_registry


@yeoman_registry.mapped
@dataclass
class Element(object):
    __table__ = Table(
        'eq36_elements',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('es_id', Integer, ForeignKey('es.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
    )

    name: str
    log_molality: float
    es_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped
@dataclass
class AqueousSpecies(object):
    __table__ = Table(
        'eq36_aqueous_species',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('es_id', Integer, ForeignKey('es.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
        Column('log_activity', Double, nullable=False),
    )

    name: str
    log_molality: float
    log_activity: float
    es_id: int | None = None
    id: int | None = None


@yeoman_registry.mapped
@dataclass
class SolidPhase(object):
    __table__ = Table(
        'eq36_solid_phase',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('es_id', Integer, ForeignKey('es.id'), nullable=False),
        Column('type', String, nullable=False),
        Column('name', String, nullable=False),
        Column('end_member', String, nullable=True),
        Column('log_qk', Double, nullable=False),
        Column('log_moles', Double),
    )

    type: str
    name: str
    log_qk: float
    log_moles: float | None = None
    end_member: str | None = None
    es_id: int | None = None
    id: int | None = None


@yeoman_registry.mapped
@dataclass
class Gas(object):
    __table__ = Table(
        'eq36_gas',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('es_id', Integer, ForeignKey('es.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_fugacity: float
    es_id: int | None = None
    id: int | None = None


@yeoman_registry.mapped_as_dataclass
class ESPoint(BaseESPoint):
    __abstract__ = True

    @declared_attr
    def __mapper_args__(cls):
        return {
            'polymorphic_identity': __loader__.name + '.' + cls.__qualname__,  # type: ignore
            'properties': {
                'elements': relationship(Element),
                'aqueous_species': relationship(AqueousSpecies),
                'solid_phases': relationship(SolidPhase),
                'gases': relationship(Gas),
            }
        }

    temperature: float
    pressure: float
    pH: float
    log_fO2: float
    log_activity_water: float
    ionic_strength: float
    tds_mass: float
    solution_mass: float
    charge_imbalance: float
    elements: list[Element]
    aqueous_species: list[AqueousSpecies]
    solid_phases: list[SolidPhase]
    gases: list[Gas]
    extended_alkalinity: Optional[float] = None
    initial_affinity: Optional[float] = None
    log_xi: Optional[float] = None


@yeoman_registry.mapped_as_dataclass(init=False)
class Eq3Point(ESPoint):
    __table__ = Table(
        'eq3',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('es.id'), primary_key=True),
        Column('temperature', Double, nullable=False),
        Column('pressure', Double, nullable=False),
        Column('pH', Double, nullable=False),
        Column('log_fO2', Double, nullable=False),
        Column('log_activity_water', Double, nullable=False),
        Column('ionic_strength', Double, nullable=False),
        Column('tds_mass', Double, nullable=False),
        Column('solution_mass', Double, nullable=False),
        Column('charge_imbalance', Double, nullable=False),
        Column('extended_alkalinity', Double),
        Column('initial_affinity', Double),
        Column('log_xi', Double),
    )

    def __init__(
        self,
        temperature: float,
        pressure: float,
        pH: float,
        log_fO2: float,
        log_activity_water: float,
        ionic_strength: float,
        tds_mass: float,
        solution_mass: float,
        charge_imbalance: float,
        elements: list[Element],
        aqueous_species: list[AqueousSpecies],
        solid_phases: list[SolidPhase],
        gases: list[Gas],
        id: Optional[int] = None,
        vs_id: Optional[int] = None,
        extended_alkalinity: Optional[float] = None,
        initial_affinity: Optional[float] = None,
        log_xi: Optional[float] = None,
    ):
        self.temperature = temperature
        self.pressure = pressure
        self.pH = pH
        self.log_fO2 = log_fO2
        self.log_activity_water = log_activity_water
        self.ionic_strength = ionic_strength
        self.tds_mass = tds_mass
        self.solution_mass = solution_mass
        self.charge_imbalance = charge_imbalance
        self.elements = elements
        self.aqueous_species = aqueous_species
        self.solid_phases = solid_phases
        self.gases = gases
        self.extended_alkalinity = extended_alkalinity
        self.initial_affinity = initial_affinity
        self.log_xi = log_xi


@yeoman_registry.mapped_as_dataclass(init=False)
class Eq6Point(ESPoint):
    __table__ = Table(
        'eq6',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('es.id'), primary_key=True),
        Column('temperature', Double, nullable=False),
        Column('pressure', Double, nullable=False),
        Column('pH', Double, nullable=False),
        Column('log_fO2', Double, nullable=False),
        Column('log_activity_water', Double, nullable=False),
        Column('ionic_strength', Double, nullable=False),
        Column('tds_mass', Double, nullable=False),
        Column('solution_mass', Double, nullable=False),
        Column('charge_imbalance', Double, nullable=False),
        Column('extended_alkalinity', Double),
        Column('initial_affinity', Double),
        Column('log_xi', Double),
    )

    def __init__(
        self,
        temperature: float,
        pressure: float,
        pH: float,
        log_fO2: float,
        log_activity_water: float,
        ionic_strength: float,
        tds_mass: float,
        solution_mass: float,
        charge_imbalance: float,
        elements: list[Element],
        aqueous_species: list[AqueousSpecies],
        solid_phases: list[SolidPhase],
        gases: list[Gas],
        id: Optional[int] = None,
        vs_id: Optional[int] = None,
        extended_alkalinity: Optional[float] = None,
        initial_affinity: Optional[float] = None,
        log_xi: Optional[float] = None,
    ):
        self.temperature = temperature
        self.pressure = pressure
        self.pH = pH
        self.log_fO2 = log_fO2
        self.log_activity_water = log_activity_water
        self.ionic_strength = ionic_strength
        self.tds_mass = tds_mass
        self.solution_mass = solution_mass
        self.charge_imbalance = charge_imbalance
        self.elements = elements
        self.aqueous_species = aqueous_species
        self.solid_phases = solid_phases
        self.gases = gases
        self.extended_alkalinity = extended_alkalinity
        self.initial_affinity = initial_affinity
        self.log_xi = log_xi
