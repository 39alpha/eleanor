from dataclasses import dataclass, field
from datetime import datetime
from typing import final

import numpy as np

import eleanor.equilibrium_space as es

from .kernel.config import Config as KernelConfig


@final
@dataclass
class SuppressionException(object):
    name: str


@final
@dataclass
class Suppression(object):
    name: str | None
    type: str | None
    exceptions: list[SuppressionException]


@final
@dataclass
class MineralReactant(object):
    name: str
    log_moles: np.float64
    titration_rate: np.float64


@final
@dataclass
class AqueousReactant(object):
    name: str
    log_moles: np.float64
    titration_rate: np.float64


@final
@dataclass
class GasReactant(object):
    name: str
    log_moles: np.float64
    titration_rate: np.float64


@final
@dataclass
class ElementReactant(object):
    name: str
    log_moles: np.float64
    titration_rate: np.float64


@final
@dataclass
class SpecialReactantComposition(object):
    element: str
    count: int


@final
@dataclass
class SpecialReactant(object):
    name: str
    log_moles: np.float64
    titration_rate: np.float64
    composition: list[SpecialReactantComposition]


@final
@dataclass
class FixedGasReactant(object):
    name: str
    log_moles: np.float64
    log_fugacity: np.float64


@final
@dataclass
class SolidSolutionReactantEndMembers(object):
    name: str
    fraction: np.float64


@final
@dataclass
class SolidSolutionReactant(object):
    name: str
    log_moles: np.float64
    titration_rate: np.float64
    end_members: list[SolidSolutionReactantEndMembers]


@final
@dataclass
class Element(object):
    name: str
    log_molality: np.float64


@final
@dataclass
class Species(object):
    name: str
    value: np.float64


@final
@dataclass
class Scratch(object):
    zip: bytes


@final
@dataclass
class Point(object):
    kernel: KernelConfig
    water_mass: np.float64
    temperature: np.float64
    pressure: np.float64
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
    order_id: int | None = None
    es_points: list[es.Point] = field(default_factory=list)
    scratch: Scratch | None = None
    exit_code: int = 0
    create_date: datetime = field(default_factory=datetime.now)
    exception: Exception | None = None
    start_date: datetime | None = None
    complete_date: datetime | None = None

    def has_species_constraint(self, name: str) -> bool:
        return any(s.name == name for s in self.species)

    def get_species(self, name: str) -> Species | None:
        for species in self.species:
            if species.name == name:
                return species
        return None

    def reactant_count(self) -> int:
        return sum(
            map(
                len,
                [
                    self.mineral_reactants,
                    self.aqueous_reactants,
                    self.gas_reactants,
                    self.element_reactants,
                    self.special_reactants,
                    self.fixed_gas_reactants,
                    self.solid_solution_reactants,
                ],
            )
        )

    def has_reactants(self) -> bool:
        return self.reactant_count() != 0
