from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import final

from sqlalchemy import CheckConstraint, Column, DateTime, Double, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import SchemaItem

from ....typing import Callable, ClassVar, cast
from .registry import postgres_registry
from .types import Binary, JSONDict

Column = cast(Callable[..., SchemaItem], Column)


@final
@postgres_registry.mapped
@dataclass
class VSSuppressionExceptionModel(object):
    __table__ = Table(
        'suppression_exceptions',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('name', String, nullable=False),
        Column('suppression_id', Integer, ForeignKey('suppressions.id', ondelete='CASCADE'), nullable=False),
    )

    name: str
    id: int | None = None
    suppression_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSSuppressionModel(object):
    __table__ = Table(
        'suppressions',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String),
        Column('type', String),
        CheckConstraint('name is not null or type is not null', name='suppressions_well_defined'),
    )

    __mapper_args__ = {
        'properties': {
            'exceptions': relationship(VSSuppressionExceptionModel, cascade='all, delete'),
        }
    }

    name: str | None
    type: str | None
    exceptions: list[VSSuppressionExceptionModel]
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSMineralReactantModel(object):
    __table__ = Table(
        'mineral_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSAqueousReactantModel(object):
    __table__ = Table(
        'aqueous_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSGasReactantModel(object):
    __table__ = Table(
        'gas_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSElementReactantModel(object):
    __table__ = Table(
        'element_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    name: str
    log_moles: float
    titration_rate: float
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSSpecialReactantCompositionModel(object):
    __table__ = Table(
        'special_reactant_compositions',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('special_reactant_id', Integer, ForeignKey('special_reactants.id', ondelete='CASCADE'), nullable=False),
        Column('element', String, nullable=False),
        Column('count', Integer, nullable=False),
    )

    element: str
    count: int
    id: int | None = None
    special_reactant_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSSpecialReactantModel(object):
    __table__ = Table(
        'special_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'composition': relationship(VSSpecialReactantCompositionModel, cascade='all, delete'),
        }
    }

    name: str
    log_moles: float
    titration_rate: float
    composition: list[VSSpecialReactantCompositionModel]
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSGlassReactantOxideCompositionModel(object):
    __table__ = Table(
        'glass_reactant_oxide_compositions',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('glass_reactant_oxide_id', Integer, ForeignKey('glass_reactant_oxides.id', ondelete='CASCADE'), nullable=False),
        Column('element', String, nullable=False),
        Column('count', Integer, nullable=False),
    )

    element: str
    count: int
    id: int | None = None
    glass_reactant_oxide_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSGlassReactantOxideModel(object):
    __table__ = Table(
        'glass_reactant_oxides',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('glass_reactant_id', Integer, ForeignKey('glass_reactants.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('fraction', Double, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'composition': relationship(VSGlassReactantOxideCompositionModel, cascade='all, delete'),
        }
    }

    name: str
    fraction: float
    log_moles: float
    titration_rate: float
    composition: list[VSGlassReactantOxideCompositionModel]
    id: int | None = None
    glass_reactant_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSGlassReactantModel(object):
    __table__ = Table(
        'glass_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'oxides': relationship(VSGlassReactantOxideModel, cascade='all, delete'),
        }
    }

    name: str
    log_moles: float
    titration_rate: float
    oxides: list[VSGlassReactantOxideModel]
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSFixedGasReactantModel(object):
    __table__ = Table(
        'fixed_gas_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_moles: float
    log_fugacity: float
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSSolidSolutionReactantEndMembersModel(object):
    __table__ = Table(
        'solid_solution_reactant_end_members',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('solid_solution_reactant_id', Integer, ForeignKey('solid_solution_reactants.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('fraction', Double, nullable=False),
        CheckConstraint('0.0 <= fraction AND fraction <= 1.0', name='fraction_in_range'),
    )

    name: str
    fraction: float
    id: int | None = None
    solid_solution_reactant_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSSolidSolutionReactantModel(object):
    __table__ = Table(
        'solid_solution_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_moles', Double, nullable=False),
        Column('titration_rate', Double, nullable=False),
    )

    __mapper_args__ = {
        'properties': {
            'end_members': relationship(VSSolidSolutionReactantEndMembersModel, cascade='all, delete'),
        }
    }

    name: str
    log_moles: float
    titration_rate: float
    end_members: list[VSSolidSolutionReactantEndMembersModel]
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSElementModel(object):
    __table__ = Table(
        'elements',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
    )

    name: str
    log_molality: float
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSSpeciesModel(object):
    __table__ = Table(
        'species',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('value', Double, nullable=False),
    )

    name: str
    value: float
    id: int | None = None
    variable_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSScratchModel(object):
    __table__ = Table(
        'scratch',
        postgres_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), primary_key=True),
        Column('zip', Binary, nullable=False),
    )

    zip: bytes
    id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class KernelConfigModel(object):
    __table__ = Table(
        'kernel',
        postgres_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE'), primary_key=True),
        Column('type', String, nullable=False),
        Column('settings', JSONDict, nullable=False),
    )

    type: str
    settings: dict[str, object]
    id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class VSPointModel(object):
    __table__ = Table(
        'variable_space',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('order_id', Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        Column('water_mass', Double, nullable=False),
        Column('temperature', Double, nullable=False),
        Column('pressure', Double, nullable=False),
        Column('exit_code', Integer, nullable=False),
        Column('create_date', DateTime, nullable=False),
        Column('start_date', DateTime, nullable=False),
        Column('complete_date', DateTime, nullable=False),
    )

    __mapper_args__: ClassVar[dict[str, object]] = {
        'properties': {
            'kernel': relationship('KernelConfigModel', cascade='all, delete', uselist=False),
            'elements': relationship('VSElementModel', cascade='all, delete'),
            'species': relationship('VSSpeciesModel', cascade='all, delete'),
            'suppressions': relationship('VSSuppressionModel', cascade='all, delete'),
            'mineral_reactants': relationship('VSMineralReactantModel', cascade='all, delete'),
            'aqueous_reactants': relationship('VSAqueousReactantModel', cascade='all, delete'),
            'gas_reactants': relationship('VSGasReactantModel', cascade='all, delete'),
            'element_reactants': relationship('VSElementReactantModel', cascade='all, delete'),
            'special_reactants': relationship('VSSpecialReactantModel', cascade='all, delete'),
            'fixed_gas_reactants': relationship('VSFixedGasReactantModel', cascade='all, delete'),
            'solid_solution_reactants': relationship('VSSolidSolutionReactantModel', cascade='all, delete'),
            'glass_reactants': relationship('VSGlassReactantModel', cascade='all, delete'),
            'es_points': relationship('ESPointModel', cascade='all, delete'),
            'scratch': relationship('VSScratchModel', cascade='all, delete', uselist=False),
        }
    }

    kernel: KernelConfigModel
    water_mass: float
    temperature: float
    pressure: float
    elements: list[VSElementModel]
    species: list[VSSpeciesModel]
    suppressions: list[VSSuppressionModel]
    mineral_reactants: list[VSMineralReactantModel]
    aqueous_reactants: list[VSAqueousReactantModel]
    gas_reactants: list[VSGasReactantModel]
    element_reactants: list[VSElementReactantModel]
    special_reactants: list[VSSpecialReactantModel]
    fixed_gas_reactants: list[VSFixedGasReactantModel]
    solid_solution_reactants: list[VSSolidSolutionReactantModel]
    glass_reactants: list[VSGlassReactantModel]
    id: int | None = None
    order_id: int | None = None
    es_points: list[object] = field(default_factory=list)
    scratch: VSScratchModel | None = None
    exit_code: int = 0
    create_date: datetime = field(default_factory=datetime.now)
    start_date: datetime | None = None
    complete_date: datetime | None = None


@final
@postgres_registry.mapped
@dataclass
class ESElementModel(object):
    __table__ = Table(
        'equilibrium_elements',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
        Column('mass_fraction', Double, nullable=False),
    )

    name: str
    log_molality: float
    mass_fraction: float
    id: int | None = None
    equilibrium_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESAqueousSpeciesModel(object):
    __table__ = Table(
        'equilibrium_aqueous_species',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
        Column('log_activity', Double, nullable=False),
        Column('log_gamma', Double, nullable=False),
    )

    name: str
    log_molality: float
    log_activity: float
    log_gamma: float
    id: int | None = None
    equilibrium_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESPureSolidModel(object):
    __table__ = Table(
        'equilibrium_pure_solids',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_qk', Double, nullable=False),
        Column('affinity', Double, nullable=False),
        Column('log_moles', Double, nullable=False, default=-math.inf),
        Column('log_mass', Double, nullable=False, default=-math.inf),
        Column('log_volume', Double, nullable=False, default=-math.inf),
    )

    name: str
    log_qk: float
    affinity: float
    log_moles: float | None = None
    log_mass: float | None = None
    log_volume: float | None = None
    id: int | None = None
    equilibrium_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESEndMemberModel(object):
    __table__ = Table(
        'equilibrium_end_members',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_solid_solution_id', Integer, ForeignKey('equilibrium_solid_solutions.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_qk', Double, nullable=False),
        Column('affinity', Double, nullable=False),
        Column('log_moles', Double, nullable=False, default=-math.inf),
        Column('log_mass', Double, nullable=False, default=-math.inf),
        Column('log_volume', Double, nullable=False, default=-math.inf),
    )

    name: str
    log_qk: float
    affinity: float
    log_moles: float | None = None
    log_mass: float | None = None
    log_volume: float | None = None
    id: int | None = None
    equilibrium_solid_solution_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESSolidSolutionModel(object):
    __table__ = Table(
        'equilibrium_solid_solutions',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_qk', Double, nullable=False),
        Column('affinity', Double, nullable=False),
        Column('log_moles', Double, nullable=False, default=-math.inf),
        Column('log_mass', Double, nullable=False, default=-math.inf),
        Column('log_volume', Double, nullable=False, default=-math.inf),
    )

    __mapper_args__: ClassVar[dict[str, object]] = {
        'properties': {
            'end_members': relationship(ESEndMemberModel, cascade='all, delete'),
        }
    }

    name: str
    log_qk: float
    affinity: float
    end_members: list[ESEndMemberModel]
    log_moles: float | None = None
    log_mass: float | None = None
    log_volume: float | None = None
    id: int | None = None
    equilibrium_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESGasModel(object):
    __table__ = Table(
        'equilibrium_gases',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_fugacity: float
    id: int | None = None
    equilibrium_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESReactantModel(object):
    __table__ = Table(
        'equilibrium_reactants',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete='CASCADE'), nullable=False),
        Column('name', String, nullable=False),
        Column('affinity', Double, nullable=False),
        Column('relative_rate', Double, nullable=False),
        Column('log_moles_reacted', Double, nullable=False),
        Column('log_moles_remaining', Double, nullable=False),
        Column('log_mass_reacted', Double, nullable=False),
        Column('log_mass_remaining', Double, nullable=False),
    )

    name: str
    affinity: float
    relative_rate: float
    log_moles_reacted: float
    log_moles_remaining: float
    log_mass_reacted: float
    log_mass_remaining: float
    id: int | None = None
    equilibrium_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESRedoxReactionModel(object):
    __table__ = Table(
        'equilibrium_redox_reactions',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete='CASCADE'), nullable=False),
        Column('couple', String, nullable=False),
        Column('Eh', Double, nullable=False),
        Column('pe', Double, nullable=False),
        Column('log_fO2', Double, nullable=False),
        Column('Ah', Double, nullable=False),
    )

    couple: str
    Eh: float
    pe: float
    log_fO2: float
    Ah: float
    id: int | None = None
    equilibrium_space_id: int | None = None


@final
@postgres_registry.mapped
@dataclass
class ESPointModel(object):
    __table__ = Table(
        'equilibrium_space',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete='CASCADE')),
        Column('stage', String, nullable=False),
        Column('log_xi', Double),
        Column('temperature', Double, nullable=False),
        Column('pressure', Double, nullable=False),
        Column('pH', Double, nullable=False),
        Column('log_fO2', Double, nullable=False),
        Column('log_activity_water', Double, nullable=False),
        Column('mole_fraction_water', Double, nullable=False),
        Column('log_gamma_water', Double, nullable=False),
        Column('Eh', Double, nullable=False),
        Column('pe', Double, nullable=False),
        Column('Ah', Double, nullable=False),
        Column('pcH', Double),
        Column('pHCl', Double),
        Column('log_ionic_strength', Double, nullable=False),
        Column('log_stoichiometric_ionic_strength', Double, nullable=False),
        Column('log_ionic_asymmetry', Double, nullable=False),
        Column('log_stoichiometric_ionic_asymmetry', Double, nullable=False),
        Column('osmotic_coefficient', Double, nullable=False),
        Column('stoichiometric_osmotic_coefficient', Double, nullable=False),
        Column('log_sum_molalities', Double, nullable=False),
        Column('log_sum_stoichiometric_molalities', Double, nullable=False),
        Column('charge_imbalance', Double, nullable=False),
        Column('expected_charge_imbalance', Double),
        Column('sigma', Double),
        Column('charge_discrepancy', Double),
        Column('anions', Double),
        Column('cations', Double),
        Column('total_charge', Double),
        Column('mean_charge', Double),
        Column('solute_mass', Double, nullable=False),
        Column('solvent_mass', Double, nullable=False),
        Column('solution_mass', Double, nullable=False),
        Column('solution_volume', Double),
        Column('tds', Double, nullable=False),
        Column('solute_fraction', Double, nullable=False),
        Column('solvent_fraction', Double, nullable=False),
        Column('extended_alkalinity', Double),
        Column('overall_affinity', Double),
        Column('reactant_mass_reacted', Double),
        Column('reactant_mass_remaining', Double),
        Column('solid_mass_change', Double),
        Column('solid_mass_created', Double),
        Column('solid_mass_destroyed', Double),
        Column('solid_volume_change', Double),
        Column('solid_volume_created', Double),
        Column('solid_volume_destroyed', Double),
        Column('start_date', DateTime, nullable=False),
        Column('complete_date', DateTime, nullable=False),
        Column('custom_properties', JSONDict, nullable=False),
    )

    __mapper_args__: ClassVar[dict[str, object]] = {
        'properties': {
            'elements': relationship(ESElementModel, cascade='all, delete'),
            'aqueous_species': relationship(ESAqueousSpeciesModel, cascade='all, delete'),
            'pure_solids': relationship(ESPureSolidModel, cascade='all, delete'),
            'solid_solutions': relationship(ESSolidSolutionModel, cascade='all, delete'),
            'gases': relationship(ESGasModel, cascade='all, delete'),
            'reactants': relationship(ESReactantModel, cascade='all, delete'),
            'redox_reactions': relationship(ESRedoxReactionModel, cascade='all, delete'),
        }
    }

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
    elements: list[ESElementModel]
    aqueous_species: list[ESAqueousSpeciesModel]
    pure_solids: list[ESPureSolidModel]
    solid_solutions: list[ESSolidSolutionModel]
    gases: list[ESGasModel]
    redox_reactions: list[ESRedoxReactionModel]
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
    reactants: list[ESReactantModel] = field(default_factory=list)
    id: int | None = None
    variable_space_id: int | None = None
    start_date: datetime | None = None
    complete_date: datetime | None = None
    custom_properties: dict[str, object] = field(default_factory=dict)


@final
@postgres_registry.mapped
@dataclass
class OrderModel(object):
    __table__ = Table(
        'orders',
        postgres_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String, nullable=False, index=True),
        Column('tag', String, nullable=False, default='', server_default='', index=True),
        Column('eleanor_version', String, nullable=False, index=True),
        Column('raw', JSONDict, nullable=False),
        Column('create_date', DateTime, nullable=False),
    )

    __mapper_args__: ClassVar[dict[str, object]] = {
        'properties': {
            'vs_points': relationship('VSPointModel', cascade='all, delete'),
        }
    }

    name: str
    eleanor_version: str
    raw: dict[str, object]
    id: int | None = None
    tag: str = ''
    create_date: datetime = field(default_factory=datetime.now)
    vs_points: list[VSPointModel] = field(default_factory=list)
