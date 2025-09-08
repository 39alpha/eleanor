from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Double, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

import eleanor.equilibrium_space as es

from .kernel.config import Config as KernelConfig
from .reactants import ReactantType
from .typing import Any, Optional
from .yeoman import Binary, yeoman_registry


@yeoman_registry.mapped
@dataclass
class SuppressionException(object):
    __table__ = Table(
        'suppression_exceptions',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('name', String, nullable=False),
        Column('suppression_id', Integer, ForeignKey('suppressions.id', ondelete="CASCADE"), nullable=False),
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
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String),
        Column('type', String),
        CheckConstraint('name is not null or type is not null', name='suppressions_well_defined'),
    )

    __mapper_args__ = {
        'properties': {
            'exceptions': relationship(SuppressionException, cascade="all, delete"),
        }
    }

    name: Optional[str]
    type: Optional[str]
    exceptions: list[SuppressionException]
    id: Optional[int] = None
    variable_space_id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class MineralReactant(object):
    __table__ = Table(
        'mineral_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: Optional[int]
    variable_space_id: Optional[int]


@yeoman_registry.mapped_as_dataclass
class AqueousReactant(object):
    __table__ = Table(
        'aqueous_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: Optional[int]
    variable_space_id: Optional[int]


@yeoman_registry.mapped_as_dataclass
class GasReactant(object):
    __table__ = Table(
        'gas_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: Optional[int]
    variable_space_id: Optional[int]


@yeoman_registry.mapped_as_dataclass
class ElementReactant(object):
    __table__ = Table(
        'element_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: Optional[int]
    variable_space_id: Optional[int]


@yeoman_registry.mapped_as_dataclass
class SpecialReactantComposition(object):
    __table__ = Table(
        'special_reactant_compositions',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('special_reactant_id', Integer, ForeignKey('special_reactants.id', ondelete="CASCADE"), nullable=False),
        Column('element', String, nullable=False),
        Column('count', Integer, nullable=False),
    )

    element: str
    count: int
    id: Optional[int] = None
    special_reactant_id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class SpecialReactant(object):
    __table__ = Table(
        'special_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'composition': relationship(SpecialReactantComposition, cascade="all, delete"),
        }
    }

    name: str
    log_moles: float
    titration_rate: float
    composition: list[SpecialReactantComposition]
    id: Optional[int]
    variable_space_id: Optional[int]


@yeoman_registry.mapped_as_dataclass
class FixedGasReactant(object):
    __table__ = Table(
        'fixed_gas_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_moles: float
    log_fugacity: float
    id: Optional[int]
    variable_space_id: Optional[int]


@yeoman_registry.mapped_as_dataclass
class SolidSolutionReactantEndMembers(object):
    __table__ = Table(
        'solid_solution_reactant_end_members',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('solid_solution_reactant_id',
               Integer,
               ForeignKey('solid_solution_reactants.id', ondelete="CASCADE"),
               nullable=False),
        Column('name', String, nullable=False),
        Column('fraction', Double, nullable=False),
        CheckConstraint('0.0 <= fraction AND fraction <= 1.0', name='fraction_in_range'),
    )

    name: str
    fraction: float
    id: Optional[int] = None
    solid_solution_reactant_id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class SolidSolutionReactant(object):
    __table__ = Table(
        'solid_solution_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'end_members': relationship(SolidSolutionReactantEndMembers, cascade="all, delete"),
        }
    }

    name: str
    log_moles: float
    titration_rate: float
    end_members: list[SolidSolutionReactantEndMembers]
    id: Optional[int]
    variable_space_id: Optional[int]


@yeoman_registry.mapped
@dataclass
class Element(object):
    __table__ = Table(
        'elements',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
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
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('value', Double, nullable=False),
    )

    name: str
    value: float
    id: Optional[int] = None
    variable_space_id: Optional[int] = None


@yeoman_registry.mapped
@dataclass
class Scratch(object):
    __table__ = Table(
        'scratch',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), primary_key=True),
        Column('zip', Binary, nullable=False),
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
        Column('order_id', Integer, ForeignKey('orders.id', ondelete="CASCADE"), nullable=False),
        Column('temperature', Double, nullable=False),
        Column('pressure', Double, nullable=False),
        Column('exit_code', Integer, nullable=False),
        Column('create_date', DateTime, nullable=False),
        Column('start_date', DateTime, nullable=False),
        Column('complete_date', DateTime, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'kernel': relationship(KernelConfig, cascade="all, delete", uselist=False),
            'elements': relationship(Element, cascade="all, delete"),
            'species': relationship(Species, cascade="all, delete"),
            'suppressions': relationship(Suppression, cascade="all, delete"),
            'mineral_reactants': relationship(MineralReactant, cascade="all, delete"),
            'aqueous_reactants': relationship(AqueousReactant, cascade="all, delete"),
            'gas_reactants': relationship(GasReactant, cascade="all, delete"),
            'element_reactants': relationship(ElementReactant, cascade="all, delete"),
            'special_reactants': relationship(SpecialReactant, cascade="all, delete"),
            'fixed_gas_reactants': relationship(FixedGasReactant, cascade="all, delete"),
            'solid_solution_reactants': relationship(SolidSolutionReactant, cascade="all, delete"),
            'es_points': relationship(es.Point, cascade="all, delete"),
            'scratch': relationship(Scratch, cascade="all, delete", uselist=False)
        }
    }

    kernel: KernelConfig
    temperature: float
    pressure: float
    elements: list[Element]
    species: list[Species]
    suppressions: list[Suppression]
    mineral_reactants: list[MineralReactant]
    aqueous_reactants: list[AqueousReactant]
    gas_reactants: list[GasReactant]
    element_reactants: list[ElementReactant]
    special_reactants: list[SpecialReactant]
    fixed_gas_reactants: list[FixedGasReactant]
    solid_solution_reactants: list[SolidSolutionReactant]
    id: Optional[int] = None
    order_id: Optional[int] = None
    es_points: list[es.Point] = field(default_factory=list)
    scratch: Optional[Scratch] = None
    exit_code: int = 0
    create_date: datetime = field(default_factory=datetime.now)
    exception: Optional[Exception] = None
    start_date: Optional[datetime] = None
    complete_date: Optional[datetime] = None

    def has_species_constraint(self, name: str) -> bool:
        return any(s.name == name for s in self.species)

    def get_species(self, name: str) -> Optional[Species]:
        for species in self.species:
            if species.name == name:
                return species
        return None

    def reactant_count(self) -> int:
        return sum(
            map(lambda rs: len(rs), [
                self.mineral_reactants,
                self.aqueous_reactants,
                self.gas_reactants,
                self.element_reactants,
                self.special_reactants,
                self.fixed_gas_reactants,
                self.solid_solution_reactants,
            ]))

    def has_reactants(self) -> bool:
        return self.reactant_count() != 0
