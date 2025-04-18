import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

import eleanor.equilibrium_space as es
from eleanor.equilibrium_space import *
from eleanor.typing import Any, Optional
from eleanor.yeoman import yeoman_registry
from sqlalchemy import BLOB, CheckConstraint, Column, DateTime, Double, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import declared_attr, relationship


class Point(es.Point):
    __mapper_args__: dict[str, Any] = {
        'polymorphic_abstract': True,
    }


@yeoman_registry.mapped_as_dataclass(init=False)
class Eq3Point(Point):

    @declared_attr
    def __mapper_args__(cls):
        return {
            'polymorphic_identity': 'eq3',
        }

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
        variable_space_id: Optional[int] = None,
        extended_alkalinity: Optional[float] = None,
        initial_affinity: Optional[float] = None,
        log_xi: Optional[float] = None,
        start_date: Optional[datetime] = None,
        complete_date: Optional[datetime] = None,
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
        self.start_date = start_date
        self.complete_date = complete_date


@yeoman_registry.mapped_as_dataclass(init=False)
class Eq6Point(Point):

    @declared_attr
    def __mapper_args__(cls):
        return {
            'polymorphic_identity': 'eq6',
        }

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
        variable_space_id: Optional[int] = None,
        extended_alkalinity: Optional[float] = None,
        initial_affinity: Optional[float] = None,
        log_xi: Optional[float] = None,
        start_date: Optional[datetime] = None,
        complete_date: Optional[datetime] = None,
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
        self.start_date = start_date
        self.complete_date = complete_date
