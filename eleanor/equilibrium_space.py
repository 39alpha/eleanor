import math
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Column, DateTime, Double, ForeignKey, Integer, String, Table
from sqlalchemy.orm import declared_attr, relationship

from .typing import Any, Optional
from .yeoman import JSONDict, yeoman_registry


@yeoman_registry.mapped_as_dataclass
class Element(object):
    __table__ = Table(
        'equilibrium_elements',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
        Column('mass_fraction', Double, nullable=False),
    )

    name: str
    log_molality: float
    mass_fraction: float
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class AqueousSpecies(object):
    __table__ = Table(
        'equilibrium_aqueous_species',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_molality', Double, nullable=False),
        Column('log_activity', Double, nullable=False),
        Column('log_gamma', Double, nullable=False),
    )

    name: str
    log_molality: float
    log_activity: float
    log_gamma: float
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass(init=False)
class PureSolid(object):
    __table__ = Table(
        'equilibrium_pure_solid',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete="CASCADE"), nullable=False),
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
    log_moles: Optional[float] = None
    log_mass: Optional[float] = None
    log_volume: Optional[float] = None
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class EndMember(object):
    __table__ = Table(
        'equilibrium_end_member',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_solid_solution_id',
               Integer,
               ForeignKey('equilibrium_solid_solution.id', ondelete="CASCADE"),
               nullable=False),
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
    log_moles: Optional[float] = None
    log_mass: Optional[float] = None
    log_volume: Optional[float] = None
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class SolidSolution(object):
    __table__ = Table(
        'equilibrium_solid_solution',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_qk', Double, nullable=False),
        Column('affinity', Double, nullable=False),
        Column('log_moles', Double, nullable=False, default=-math.inf),
        Column('log_mass', Double, nullable=False, default=-math.inf),
        Column('log_volume', Double, nullable=False, default=-math.inf),
    )

    __mapper_args__: dict[str, Any] = {
        'properties': {
            'end_members': relationship(EndMember, cascade="all, delete"),
        }
    }

    name: str
    log_qk: float
    affinity: float
    end_members: list[EndMember]
    log_moles: Optional[float] = None
    log_mass: Optional[float] = None
    log_volume: Optional[float] = None
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class Gas(object):
    __table__ = Table(
        'equilibrium_gas',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete="CASCADE"), nullable=False),
        Column('name', String, nullable=False),
        Column('log_fugacity', Double, nullable=False),
    )

    name: str
    log_fugacity: float
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class Reactant(object):
    __table__ = Table(
        'equilibrium_reactants',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete="CASCADE"), nullable=False),
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
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass
class RedoxReaction(object):
    __table__ = Table(
        'equilibrium_redox_reactions',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('equilibrium_space_id', Integer, ForeignKey('equilibrium_space.id', ondelete="CASCADE"), nullable=False),
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
    equilibrium_space_id: Optional[int] = None
    id: Optional[int] = None


@yeoman_registry.mapped_as_dataclass(kw_only=True)
class Point(object):
    __table__ = Table(
        'equilibrium_space',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE")),
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
        Column('tds_mass', Double, nullable=False),
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

    __mapper_args__: dict[str, Any] = {
        'properties': {
            'elements': relationship(Element, cascade="all, delete"),
            'aqueous_species': relationship(AqueousSpecies, cascade="all, delete"),
            'pure_solids': relationship(PureSolid, cascade="all, delete"),
            'solid_solutions': relationship(SolidSolution, cascade="all, delete"),
            'gases': relationship(Gas, cascade="all, delete"),
            'reactants': relationship(Reactant, cascade="all, delete"),
            'redox_reactions': relationship(RedoxReaction, cascade="all, delete"),
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
    pHCl: float
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
    tds_mass: float
    solute_fraction: float
    solvent_fraction: float

    elements: list[Element]
    aqueous_species: list[AqueousSpecies]
    pure_solids: list[PureSolid]
    solid_solutions: list[SolidSolution]
    gases: list[Gas]
    redox_reactions: list[RedoxReaction]

    log_xi: Optional[float] = None
    pcH: Optional[float] = None
    solution_volume: Optional[float] = None
    expected_charge_imbalance: Optional[float] = None
    sigma: Optional[float] = None
    charge_discrepancy: Optional[float] = None
    anions: Optional[float] = None
    cations: Optional[float] = None
    total_charge: Optional[float] = None
    mean_charge: Optional[float] = None
    extended_alkalinity: Optional[float] = None
    overall_affinity: Optional[float] = None
    reactant_mass_reacted: Optional[float] = None
    reactant_mass_remaining: Optional[float] = None
    solid_mass_change: Optional[float] = None
    solid_mass_created: Optional[float] = None
    solid_mass_destroyed: Optional[float] = None
    solid_volume_change: Optional[float] = None
    solid_volume_created: Optional[float] = None
    solid_volume_destroyed: Optional[float] = None

    reactants: list[Reactant] = field(default_factory=list)

    id: Optional[int] = None
    variable_space_id: Optional[int] = None
    start_date: Optional[datetime] = None
    complete_date: Optional[datetime] = None

    custom_properties: dict = field(default_factory=dict)
