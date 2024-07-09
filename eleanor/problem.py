import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .config import Config, Parameter, Reactant, Suppression
from .exceptions import EleanorException
from .kernel.config import Config as KernelConfig
from .typing import Number, Self


class AbstractConstraint(ABC):

    @property
    @abstractmethod
    def independent_parameters(self) -> list[Parameter]:
        pass

    @property
    @abstractmethod
    def dependent_parameters(self) -> list[Parameter]:
        pass

    def depends_on(self, parameter: Parameter) -> bool:
        return any(p is parameter for p in self.independent_parameters)

    def constrains(self, parameter: Parameter) -> bool:
        return any(p is parameter for p in self.dependent_parameters)

    @property
    @abstractmethod
    def is_resolved(self) -> bool:
        pass

    @abstractmethod
    def resolve(self) -> list[Parameter]:
        for parameter, domain in self.apply():
            if isinstance(domain, list):
                parameter.constrain_by_list(domain)
            elif isinstance(domain, tuple):
                parameter.constrain_by_range(*domain)
            else:
                parameter.constrain_by_value(domain)

        return self.dependent_parameters

    @abstractmethod
    def apply(self) -> list[tuple[Parameter, Number | tuple[Number, Number] | list[Number]]]:
        pass


@dataclass
class Problem(object):
    kernel: KernelConfig
    temperature: Parameter
    pressure: Parameter
    elements: dict[str, Parameter]
    species: dict[str, Parameter]
    suppressions: list[Suppression]
    reactants: list[Reactant]
    constraints: list[AbstractConstraint]

    independent_parameters: list[Parameter]

    def __init__(self, kernel: KernelConfig, temperature: Parameter, pressure: Parameter,
                 elements: dict[str, Parameter], species: dict[str, Parameter], suppressions: list[Suppression],
                 reactants: list[Reactant], constraints: list[AbstractConstraint]):

        self.kernel = kernel
        self.temperature = temperature
        self.pressure = pressure
        self.elements = elements
        self.species = species
        self.suppressions = suppressions
        self.reactants = reactants
        self.constraints = []

        self.independent_parameters = [self.temperature, self.pressure]
        self.independent_parameters.extend(self.kernel.parameters)
        self.independent_parameters.extend(list(self.elements.values()))
        self.independent_parameters.extend(list(self.species.values()))
        for reactant in self.reactants:
            self.independent_parameters.extend(reactant.parameters)

        self.add_constraints(constraints)

    @property
    def is_fully_specified(self) -> bool:
        if len(self.independent_parameters) != 0:
            return False
        elif not self.temperature.is_fully_specified:
            return False
        elif not self.pressure.is_fully_specified:
            return False
        elif not self.kernel.is_fully_specified:
            return False
        elif any(not element.is_fully_specified for element in self.elements.values()):
            return False
        elif any(not species.is_fully_specified for species in self.species.values()):
            return False
        elif any(not reactant.is_fully_specified for reactant in self.reactants):
            return False

        return True

    @property
    def is_resolved(self) -> bool:
        return all(constraint.is_resolved for constraint in self.constraints)

    def add_constraint(self, constraint: AbstractConstraint) -> Self:
        self.constraints.append(constraint)
        for dependent_parameter in constraint.dependent_parameters:
            self.independent_parameters = [p for p in self.independent_parameters if p is not dependent_parameter]

        return self

    def add_constraints(self, constraints: list[AbstractConstraint]) -> Self:
        for constraint in constraints:
            self.add_constraint(constraint)

        return self

    def resolve(self) -> list[Parameter]:
        for constraint in self.constraints:
            if constraint.is_resolved:
                continue

            for constrained in constraint.resolve():
                fully_constrained = all(c.is_resolved or not c.constrains(constrained) for c in self.constraints)
                if fully_constrained and not any(p is constrained for p in self.independent_parameters):
                    self.independent_parameters.append(constrained)

        self.prune_independent_parameters()

        return self.independent_parameters

    def prune_independent_parameters(self):
        self.independent_parameters = [p for p in self.independent_parameters if not p.is_fully_specified]

    def has_species_constraint(self, species: str) -> bool:
        return species in self.species and self.species[species].name == species

    def to_row(self) -> dict[str, Number | str | bytes]:
        if not self.is_fully_specified:
            raise EleanorException('cannot convert underspecified problem to dict')

        d: dict[str, Number | str | bytes] = {}
        d[f'kernel'] = bytes(json.dumps(self.kernel.to_dict()), 'utf-8')
        d.update(self.temperature.to_row())
        d.update(self.pressure.to_row())
        for param in self.elements.values():
            d.update(param.to_row())
        for reactant in self.reactants:
            d.update(reactant.to_row())

        return d

    @staticmethod
    def from_config(config: Config):
        return Problem(kernel=config.kernel,
                       temperature=config.temperature,
                       pressure=config.pressure,
                       elements=config.elements,
                       species=config.species,
                       suppressions=config.suppressions,
                       reactants=config.reactants,
                       constraints=[])
