import datetime
import json
from dataclasses import asdict, dataclass, field

from sqlalchemy import BLOB, CheckConstraint, Column, DateTime, Double, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, registry, relationship

import eleanor.config.reactant as reactant
import eleanor.config.suppression as suppression
from eleanor.problem import Problem

from .exceptions import EleanorException
from .typing import Float, Optional

mapper_registry = registry()


@mapper_registry.mapped
@dataclass
class Element(object):
    __table__ = Table(
        'elements',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('es_id', Integer, ForeignKey('es.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
    )

    name: str
    log_molality: Float
    es_id: Optional[int] = None
    id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class AqueousSpecies(object):
    __table__ = Table(
        'aqueous_species',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('es_id', Integer, ForeignKey('es.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
        Column('log_activity', Double, nullable=False),
    )

    name: str
    log_molality: Float
    log_activity: Float
    es_id: int | None = None
    id: int | None = None


@mapper_registry.mapped
@dataclass
class SolidPhase(object):
    __table__ = Table(
        'solid_phase',
        mapper_registry.metadata,
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
    log_qk: Float
    log_moles: Float | None = None
    end_member: str | None = None
    es_id: int | None = None
    id: int | None = None


@mapper_registry.mapped
@dataclass
class Gas(object):
    __table__ = Table(
        'gas',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('es_id', Integer, ForeignKey('es.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_fugacity: Float
    es_id: int | None = None
    id: int | None = None


@mapper_registry.mapped
@dataclass
class ESPoint(object):
    __table__ = Table(
        'es',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('vs_id', Integer, ForeignKey('vs.id'), nullable=False),
        Column('stage', String, nullable=False),
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

    __mapper_args__ = {
        'properties': {
            'elements': relationship('Element'),
            'aqueous_species': relationship('AqueousSpecies'),
            'solid_phases': relationship('SolidPhase'),
            'gases': relationship('Gas'),
        }
    }

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
    extended_alkalinity: Optional[Float] = None
    initial_affinity: Optional[Float] = None
    log_xi: Optional[Float] = None
    vs_id: Optional[int] = None
    id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class Kernel(object):
    __table__ = Table(
        'kernel',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('vs_id', Integer, ForeignKey('vs.id'), nullable=False),
        Column('type', String, nullable=False),
        Column('config_json', BLOB, nullable=False),
    )

    type: str
    config_json: Optional[bytes] = None
    id: Optional[int] = None
    vs_id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class SuppressionException(object):
    __table__ = Table(
        'suppression_exceptions',
        mapper_registry.metadata,
        Column('name', String, primary_key=True),
        Column('suppression_id', ForeignKey('suppressions.id'), primary_key=True),
    )

    name: str
    suppression_id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class Suppression(object):
    __table__ = Table(
        'suppressions',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('vs_id', Integer, ForeignKey('vs.id'), nullable=False),
        Column('name', String),
        Column('type', String),
        CheckConstraint('name is not null or type is not null', name='suppressions_well_defined'),
    )

    __mapper_args__ = {
        'properties': {
            'exceptions': relationship('SuppressionException'),
        }
    }

    name: Optional[str] = None
    type: Optional[str] = None
    exceptions: list[SuppressionException] = field(default_factory=list)
    id: Optional[int] = None
    vs_id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class ReactantComposition(object):
    __table__ = Table(
        'reactant_composition',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('titrated_reactant_id', Integer, ForeignKey('titrated_reactant.id'), nullable=False),
        Column('element', String, nullable=False),
        Column('count', Integer, nullable=False),
    )

    element: str
    count: int
    id: Optional[int] = None
    titrated_reactant_id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class TitratedReactant(object):
    __table__ = Table(
        'titrated_reactant',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('vs_id', Integer, ForeignKey('vs.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('type', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'composition': relationship('ReactantComposition'),
        }
    }

    type: str
    name: str
    log_moles: Float
    log_titration_rate: Float
    composition: list[ReactantComposition] = field(default_factory=list)
    id: Optional[int] = None
    vs_id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class FixedGasReactant(object):
    __table__ = Table(
        'fixed_gas_reactant',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('vs_id', Integer, ForeignKey('vs.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_moles: Float
    log_fugacity: Float
    id: Optional[int] = None
    vs_id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class VSElement(object):
    __table__ = Table(
        'vs_elements',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('vs_id', Integer, ForeignKey('vs.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
    )

    name: str
    log_molality: Float
    vs_id: Optional[int] = None
    id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class VSSpecies(object):
    __table__ = Table(
        'vs_species',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('vs_id', Integer, ForeignKey('vs.id'), nullable=False),
        Column('name', String, nullable=False),
        Column('unit', String, nullable=False),
        Column('value', Double, nullable=False),
    )

    name: str
    unit: str
    value: Float
    vs_id: Optional[int] = None
    id: Optional[int] = None


@mapper_registry.mapped
@dataclass
class VSPoint(object):
    __table__ = Table(
        'vs',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('temperature', Double, nullable=False),
        Column('pressure', Double, nullable=False),
        Column('exit_code', Integer, nullable=False),
        Column('create_date', String, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'kernel': relationship('Kernel', uselist=False),
            'elements': relationship('VSElement'),
            'species': relationship('VSSpecies'),
            'suppressions': relationship('Suppression'),
            'titrated_reactants': relationship('TitratedReactant'),
            'fixed_gas_reactants': relationship('FixedGasReactant'),
            'es_points': relationship('ESPoint'),
        }
    }

    temperature: Float
    pressure: Float
    kernel: Kernel
    elements: list[VSElement]
    species: list[VSSpecies]
    suppressions: list[Suppression]
    titrated_reactants: list[TitratedReactant]
    fixed_gas_reactants: list[FixedGasReactant]
    es_points: list[ESPoint] = field(default_factory=list)
    exit_code: Optional[int] = None
    id: Optional[int] = None
    create_date: datetime.datetime = field(default_factory=datetime.datetime.now)

    @classmethod
    def from_problem(cls, problem: Problem):
        if not problem.is_fully_specified:
            raise EleanorException('cannot convert underspecified Problem to VSPoint')

        return cls(
            temperature=problem.temperature.value,  # type: ignore
            pressure=problem.pressure.value,  # type: ignore
            kernel=Kernel(type=problem.kernel.type, config_json=bytes(json.dumps(problem.kernel.to_dict()), 'utf-8')),
            elements=[VSElement(name=e.name, log_molality=e.value) for e in problem.elements.values()],  # type: ignore
            species=[
                VSSpecies(name=s.name, unit=s.unit, value=s.value)  # type: ignore
                for s in problem.species.values()
            ],
            suppressions=[
                Suppression(name=s.name, type=s.type, exceptions=[SuppressionException(e) for e in s.exceptions])
                for s in problem.suppressions
            ],
            titrated_reactants=[
                TitratedReactant(
                    type=r.type,
                    name=r.name,
                    log_moles=r.amount.value,  # type: ignore
                    log_titration_rate=r.titration_rate.value,  # type: ignore
                    composition=[] if not isinstance(r, reactant.SpecialReactant) else
                    [ReactantComposition(*c) for c in r.composition.items()],
                ) for r in problem.reactants if isinstance(r, reactant.TitratedReactant)
            ],
            fixed_gas_reactants=[
                FixedGasReactant(
                    name=r.name,
                    log_moles=r.amount.value,  # type: ignore
                    log_fugacity=r.fugacity.value,  # type: ignore
                ) for r in problem.reactants if isinstance(r, reactant.FixedGasReactant)
            ],
        )
