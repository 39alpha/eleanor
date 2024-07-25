from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import BLOB, CheckConstraint, Column, Double, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

import eleanor.equilibrium_space as es

from .kernel.config import Config as KernelConfig
from .reactants import ReactantType
from .typing import Any, Optional
from .yeoman import yeoman_registry


@yeoman_registry.mapped
@dataclass
class SuppressionException(object):
    __table__ = Table(
        'suppression_exceptions',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String, nullable=False),
        Column('suppression_id', ForeignKey('suppressions.id'), primary_key=True),
    )

    name: str
    id: Optional[int] = None
    suppression_id: Optional[int] = None


@yeoman_registry.mapped
@dataclass
class Suppression(object):
    __table__ = Table(
        'suppressions',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id'), nullable=False),
        Column('name', String),
        Column('type', String),
        CheckConstraint('name is not null or type is not null', name='suppressions_well_defined'),
    )

    __mapper_args__ = {
        'properties': {
            'exceptions': relationship(SuppressionException),
        }
    }

    name: Optional[str]
    type: Optional[str]
    exceptions: list[SuppressionException]
    id: Optional[int] = None
    variable_space_id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class Reactant(object):
    __table__ = Table(
        'reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id'), nullable=False),
        Column('type', String, nullable=False),
    )

    __mapper_args__: dict[str, Any] = {
        'polymorphic_identity': 'reactant',
        'polymorphic_on': 'type',
    }

    id: Optional[int]
    variable_space_id: Optional[int]
    name: str
    type: ReactantType


@yeoman_registry.mapped_as_dataclass
class MineralReactant(Reactant):
    __table__ = Table(
        'mineral_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('reactants.id'), primary_key=True),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'polymorphic_identity': ReactantType.MINERAL,
    }

    log_moles: float
    log_titration_rate: float


@yeoman_registry.mapped_as_dataclass
class GasReactant(Reactant):
    __table__ = Table(
        'gas_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('reactants.id'), primary_key=True),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'polymorphic_identity': ReactantType.GAS,
    }

    log_moles: float
    log_titration_rate: float


@yeoman_registry.mapped_as_dataclass
class ElementReactant(Reactant):
    __table__ = Table(
        'element_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('reactants.id'), primary_key=True),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'polymorphic_identity': ReactantType.ELEMENT,
    }

    log_moles: float
    log_titration_rate: float


@yeoman_registry.mapped_as_dataclass
class SpecialReactantComposition(object):
    __table__ = Table(
        'special_reactant_composition',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('special_reactant_id', Integer, ForeignKey('special_reactants.id'), nullable=False),
        Column('element', String, nullable=False),
        Column('count', Integer, nullable=False),
    )

    element: str
    count: int
    id: Optional[int] = None
    special_reactant_id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class SpecialReactant(Reactant):
    __table__ = Table(
        'special_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('reactants.id'), primary_key=True),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'polymorphic_identity': ReactantType.SPECIAL,
        'properties': {
            'composition': relationship(SpecialReactantComposition),
        }
    }

    log_moles: float
    log_titration_rate: float
    composition: list[SpecialReactantComposition]


@yeoman_registry.mapped_as_dataclass
class FixedGasReactant(Reactant):
    __table__ = Table(
        'fixed_gas_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('reactants.id'), primary_key=True),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    __mapper_args__ = {
        'polymorphic_identity': ReactantType.FIXED_GAS,
    }

    log_moles: float
    log_fugacity: float


@yeoman_registry.mapped
@dataclass
class Element(object):
    __table__ = Table(
        'elements',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
    )

    name: str
    log_molality: float
    id: Optional[int] = None
    variable_space_id: Optional[int] = None


@yeoman_registry.mapped
@dataclass
class Species(object):
    __table__ = Table(
        'species',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('unit', String, nullable=False),
        Column('value', Double, nullable=False),
    )

    name: str
    unit: str
    value: float
    id: Optional[int] = None
    variable_space_id: Optional[int] = None


@yeoman_registry.mapped
@dataclass
class Scratch(object):
    __table__ = Table(
        'scratch',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id'), primary_key=True),
        Column('zip', BLOB, nullable=False),
    )

    id: Optional[int]
    zip: bytes


@yeoman_registry.mapped
@dataclass
class Point(object):
    __table__ = Table(
        'variable_space',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('order_id', Integer, ForeignKey('orders.id'), nullable=False),
        Column('temperature', Double, nullable=False),
        Column('pressure', Double, nullable=False),
        Column('exit_code', Integer, nullable=False),
        Column('create_date', String, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'kernel': relationship(KernelConfig, uselist=False),
            'elements': relationship(Element),
            'species': relationship(Species),
            'suppressions': relationship(Suppression),
            'reactants': relationship(Reactant),
            'es_points': relationship(es.Point),
            'scratch': relationship(Scratch, uselist=False)
        }
    }

    kernel: KernelConfig
    temperature: float
    pressure: float
    elements: list[Element]
    species: list[Species]
    suppressions: list[Suppression]
    reactants: list[Reactant]
    id: Optional[int] = None
    order_id: Optional[int] = None
    es_points: list[es.Point] = field(default_factory=list)
    scratch: Optional[Scratch] = None
    exit_code: int = 0
    create_date: datetime = field(default_factory=datetime.now)

    def has_species_constraint(self, name: str) -> bool:
        return any(s.name == name for s in self.species)

    def get_species(self, name: str) -> Optional[Species]:
        for species in self.species:
            if species.name == name:
                return species
        return None
