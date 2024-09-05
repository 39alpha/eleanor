from dataclasses import dataclass

from sqlalchemy import Column, Double, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from .typing import Any, Optional
from .yeoman import yeoman_registry


@yeoman_registry.mapped_as_dataclass
class Element(object):
    __table__ = Table(
        'equilibrium_elements',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
    )

    name: str
    log_molality: float
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class AqueousSpecies(object):
    __table__ = Table(
        'equilibrium_aqueous_species',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
        Column('log_activity', Double, nullable=False),
    )

    name: str
    log_molality: float
    log_activity: float
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class SolidPhase(object):
    __table__ = Table(
        'equilibrium_solid_phase',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id'), nullable=False),
        Column('type', String, nullable=False),
        Column('name', String, nullable=False),
        Column('end_member', String, nullable=True),
        Column('log_qk', Double, nullable=False),
        Column('affinity', Double, nullable=False),
        Column('log_moles', Double),
    )

    type: str
    name: str
    log_qk: float
    affinity: float
    log_moles: Optional[float] = None
    end_member: Optional[str] = None
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class Gas(object):
    __table__ = Table(
        'equilibrium_gas',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_fugacity: float
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class Point(object):
    __table__ = Table(
        'equilibrium_space',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id')),
        Column('kernel', String, nullable=False),
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

    __mapper_args__: dict[str, Any] = {
        'polymorphic_identity': 'eleanor',
        'polymorphic_on': 'kernel',
        'properties': {
            'elements': relationship(Element),
            'aqueous_species': relationship(AqueousSpecies),
            'solid_phases': relationship(SolidPhase),
            'gases': relationship(Gas),
        }
    }

    id: Optional[int]
    variable_space_id: Optional[int]
    kernel: str
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
